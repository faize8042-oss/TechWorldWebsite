"""Pure inspect-policy validation. No Docker invocation or service connections."""
import json
from pathlib import Path
import re
import sys
PROJECT = 'codeventra-client-preview'
def need(ok, message):
    if not ok: raise ValueError(message)
def source(path):
    path = path.replace('\\', '/').rstrip('/')
    if re.match(r'^[A-Za-z]:/', path): path = '/run/desktop/mnt/host/' + path[0].lower() + path[2:]
    return path

def validate(data, state, root):
    resources = state['Resources']
    def resource(kind, name):
        found = [r for r in resources if r['Kind']==kind and r['Name']==name]
        need(len(found)==1, 'Missing/duplicate recorded identity: '+name)
        return found[0]
    need(state['Project']==PROJECT and bool(state['RunId']), 'State ownership')
    need(len(data['containers'])==2 and len(data['networks'])==1 and len(data['volumes'])==1, 'Resource counts')
    for kind, group in [('container','containers'),('network','networks'),('volume','volumes')]:
        for obj in data[group]:
            name = obj['Name'].lstrip('/')
            record = resource(kind,name)
            labels = obj['Config']['Labels'] if kind=='container' else obj['Labels']
            need(labels.get('com.docker.compose.project')==PROJECT and labels.get('com.codeventra.preview')=='public-only-v1' and labels.get('com.codeventra.preview.run')==state['RunId'], 'Ownership labels')
            identity = name+'|'+obj['CreatedAt']+'|'+obj['Mountpoint']+'|'+obj['Driver'] if kind=='volume' else obj['Id']
            need(identity==record['Id'], 'Replaced '+kind+' identity')
    net=data['networks'][0]; vol=data['volumes'][0]
    need(net['Labels'].get('com.docker.compose.network')=='ingress', 'Compose network ownership')
    need(vol['Labels'].get('com.docker.compose.volume')=='socket', 'Compose volume ownership')
    need(net['Name']==PROJECT+'_ingress' and net['Internal'] and net['Driver']=='bridge' and not net.get('EnableIPv6'), 'Network policy')
    need(vol['Name']==PROJECT+'_socket' and vol['Driver']=='local' and not vol.get('Options'), 'Socket volume policy')
    ingress_id = None
    for obj in data['containers']:
        service=obj['Config']['Labels']['com.docker.compose.service']
        need(service in ('web','ingress') and obj['Name']=='/'+PROJECT+'-'+service+'-1', 'Service identity')
        hc=obj['HostConfig']; config=obj['Config']; ns=obj['NetworkSettings']
        need(obj['Image']==state['AppImage' if service=='web' else 'NginxImage'], 'Unexpected image identity')
        need(obj['State']['Running'] and hc['ReadonlyRootfs'] and config['User']=='10001:10002', 'Running/read-only/user policy')
        need(not hc['Privileged'] and not hc.get('CapAdd') and hc.get('CapDrop')==['ALL'], 'Capabilities/privileged policy')
        need(hc.get('SecurityOpt') in (['no-new-privileges'], ['no-new-privileges:true']), 'Security options / NoNewPrivileges')
        need(not hc.get('Devices') and not hc.get('DeviceRequests') and not hc.get('DeviceCgroupRules'), 'Unexpected devices')
        need(hc.get('PidMode','')=='' and hc.get('IpcMode') in ('private','') and hc.get('UTSMode','')=='', 'Host namespaces')
        need(set(hc.get('Tmpfs',{}))=={'/tmp'} and hc['Tmpfs']['/tmp']=='rw,noexec,nosuid,size=32m,mode=1777', 'Tmpfs policy')
        expected = {'/run/preview': ('volume', vol['Mountpoint'], service=='web')}
        if service=='ingress':
            expected.update({'/etc/nginx/preview.conf':('bind',str(Path(root)/'deploy/client-preview/nginx.conf'),False), '/etc/nginx/preview-proxy.conf':('bind',str(Path(root)/'deploy/client-preview/proxy.conf'),False)})
        need(all(m['Destination']=='/tmp' and m['RW'] for m in obj['Mounts'] if m['Type']=='tmpfs'), 'Unexpected tmpfs mount')
        mounts=[m for m in obj['Mounts'] if m['Type']!='tmpfs']
        need(len(mounts)==len(expected), 'Unexpected mount count')
        need(len({m['Destination'] for m in mounts})==len(mounts), 'Duplicate mounts')
        for m in mounts:
            need(m['Destination'] in expected, 'Unexpected mount destination')
            typ, src, rw = expected[m['Destination']]
            need(m['Type']==typ and source(m['Source'])==source(src) and m['RW']==rw, 'Unexpected bind source or writable mount')
            if typ=='volume': need(m['Name']==vol['Name'] and m['Driver']=='local', 'Socket mount identity')
        ports=hc.get('PortBindings') or {}; live=ns.get('Ports') or {}
        if service=='web':
            need(hc['NetworkMode']=='none' and set(ns['Networks'])=={'none'} and ns['Networks']['none']['NetworkID']==state['NoneNetwork'] and not ns['Networks']['none'].get('IPAddress') and not ns['Networks']['none'].get('Gateway') and not ports and not any(live.values()), 'Web network/exposure')
            need(obj['State']['Health']['Status']=='healthy', 'Web unhealthy')
        else:
            ingress_id=obj['Id']
            need(hc['NetworkMode']==PROJECT+'_ingress' and set(ns['Networks'])=={PROJECT+'_ingress'} and ns['Networks'][PROJECT+'_ingress']['NetworkID']==net['Id'], 'Unexpected network identity')
            expected_ports={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'8765'}]}
            need(ports==expected_ports and {k:v for k,v in live.items() if v}==expected_ports, 'Unexpected published ports')
    need(set((net.get('Containers') or {}))=={ingress_id}, 'Unexpected network endpoints')
    return 'PASS: inspected resource identities, ownership, images, namespaces, security options, mounts and port publication'
if __name__=='__main__':
    try:
        print(validate(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig')),json.loads(Path(sys.argv[2]).read_text(encoding='utf-8-sig')),sys.argv[3]))
    except Exception as exc:
        print('FAIL: inspect policy: '+str(exc)); sys.exit(1)
