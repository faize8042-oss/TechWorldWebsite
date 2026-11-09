"""Offline executable health and inspect-policy regression tests."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('policy', ROOT/'scripts/client-preview/inspect-policy.py')
policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
P=policy.PROJECT

def fixture():
    labels={'com.docker.compose.project':P,'com.codeventra.preview':'public-only-v1','com.codeventra.preview.run':'test-run'}
    vol={'Name':P+'_socket','CreatedAt':'synthetic-time','Mountpoint':'/var/lib/docker/volumes/test/_data','Driver':'local','Options':None,'Labels':labels.copy()}
    net={'Name':P+'_ingress','Id':'network-id','Internal':True,'Driver':'bridge','EnableIPv6':False,'Labels':labels.copy(),'Containers':{'ingress-id':{}}}
    net['Labels']['com.docker.compose.network']='ingress'
    vol['Labels']['com.docker.compose.volume']='socket'
    state={'Project':P,'RunId':'test-run','NoneNetwork':'none-network-id','AppImage':'sha256:'+'a'*64,'NginxImage':'sha256:'+'b'*64,'Resources':[]}
    containers=[]
    for service in ('web','ingress'):
        web=service=='web'; ports={} if web else {'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'8765'}]}
        mounts=[{'Type':'volume','Name':vol['Name'],'Driver':'local','Source':vol['Mountpoint'],'Destination':'/run/preview','RW':web}]
        if not web:
            for filename,dest in [('nginx.conf','preview.conf'),('proxy.conf','preview-proxy.conf')]:
                mounts.append({'Type':'bind','Source':str(ROOT/'deploy/client-preview'/filename),'Destination':'/etc/nginx/'+dest,'RW':False})
        containers.append({'Name':'/'+P+'-'+service+'-1','Id':service+'-id','Image':state['AppImage' if web else 'NginxImage'], 'Config':{'User':'10001:10002','Labels':dict(labels,**{'com.docker.compose.service':service})},'State':{'Running':True,'Health':{'Status':'healthy'}},'HostConfig':{'ReadonlyRootfs':True,'Privileged':False,'CapAdd':None,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true'],'Devices':[],'DeviceRequests':None,'DeviceCgroupRules':None,'PidMode':'','IpcMode':'private','UTSMode':'','Tmpfs':{'/tmp':'rw,noexec,nosuid,size=32m,mode=1777'},'NetworkMode':'none' if web else P+'_ingress','PortBindings':ports},'NetworkSettings':{'Networks':{'none':{'NetworkID':'none-network-id','IPAddress':'','Gateway':''}} if web else {P+'_ingress':{'NetworkID':net['Id']}},'Ports':copy.deepcopy(ports)},'Mounts':mounts})
    data={'containers':containers,'networks':[net],'volumes':[vol]}
    for kind,group in [('container','containers'),('network','networks'),('volume','volumes')]:
        for obj in data[group]:
            name=obj['Name'].lstrip('/')
            identity=name+'|'+obj['CreatedAt']+'|'+obj['Mountpoint']+'|'+obj['Driver'] if kind=='volume' else obj['Id']
            state['Resources'].append({'Kind':kind,'Name':name,'Id':identity,'RunId':'test-run'})
    return data,state

class InspectTests(unittest.TestCase):
    def test_valid(self):
        d,s=fixture();self.assertTrue(policy.validate(d,s,ROOT).startswith('PASS'))
    def test_unsafe_metadata_rejected(self):
        mutations={
          'bind source':lambda d:d['containers'][1]['Mounts'][1].update(Source='D:/private/nginx.conf'),
          'writable bind':lambda d:d['containers'][1]['Mounts'][1].update(RW=True),
          'privileged':lambda d:d['containers'][0]['HostConfig'].update(Privileged=True),
          'cap add':lambda d:d['containers'][0]['HostConfig'].update(CapAdd=['SYS_ADMIN']),
          'cap drop':lambda d:d['containers'][0]['HostConfig'].update(CapDrop=[]),
          'no new privileges':lambda d:d['containers'][0]['HostConfig'].update(SecurityOpt=[]),
          'devices':lambda d:d['containers'][0]['HostConfig'].update(Devices=[{'PathOnHost':'/dev/sda'}]),
          'image':lambda d:d['containers'][0].update(Image='wrong'),
          'ports':lambda d:d['containers'][1]['HostConfig']['PortBindings'].update({'5432/tcp':[{'HostIp':'0.0.0.0','HostPort':'5432'}]}),
          'container replacement':lambda d:d['containers'][0].update(Id='replacement'),
          'network replacement':lambda d:d['networks'][0].update(Id='replacement'),
          'network attachment replacement':lambda d:d['containers'][1]['NetworkSettings']['Networks'][P+'_ingress'].update(NetworkID='wrong'),
          'volume replacement':lambda d:d['volumes'][0].update(CreatedAt='replacement'),
          'development volume':lambda d:d['containers'][0]['Mounts'][0].update(Name='techworldwebsite_data'),
          'unexpected container':lambda d:d['containers'].append(copy.deepcopy(d['containers'][0])),
          'unexpected network':lambda d:d['networks'].append(copy.deepcopy(d['networks'][0])),
          'unexpected mount':lambda d:d['containers'][0]['Mounts'].append({'Type':'bind','Destination':'/private'}),
          'host network':lambda d:d['containers'][0]['HostConfig'].update(NetworkMode='host'),
          'owner':lambda d:d['containers'][0]['Config']['Labels'].update({'com.docker.compose.project':'techworldwebsite'}),
          'run token':lambda d:d['volumes'][0]['Labels'].update({'com.codeventra.preview.run':'replacement'}),
        }
        for name,mutate in mutations.items():
            with self.subTest(name=name):
                d,s=fixture();mutate(d)
                with self.assertRaises(ValueError):policy.validate(d,s,ROOT)

class HealthTests(unittest.TestCase):
    def run_probe(self,code,response=b'HTTP/1.1 200 OK\r\n'):
        captured=[]
        class Socket:
            def settimeout(self,t):self.timeout=t;assert t==3
            def connect(self,p):assert p=='/run/preview/gunicorn.sock'
            def sendall(self,b):captured.append(b)
            def makefile(self,mode):return io.BytesIO(response)
            def close(self):pass
        fake=types.SimpleNamespace(AF_UNIX=1,socket=lambda family:Socket())
        with patch.dict(sys.modules,{'socket':fake}):
            with self.assertRaises(SystemExit) as result:exec(code,{})
        return captured,result.exception.code
    def code(self):return json.loads((ROOT/'deploy/client-preview/compose.yaml').read_text())['services']['web']['healthcheck']['test'][-1]
    def test_actual_emitted_bytes(self):
        emitted,status=self.run_probe(self.code())
        self.assertEqual(emitted,[b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n']);self.assertEqual(status,0)
    def test_malformed_healthcheck_detected(self):
        broken=self.code().replace('\\r\\n','\\\\r\\\\n')
        emitted,status=self.run_probe(broken)
        self.assertNotEqual(emitted,[b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n'])
        self.assertNotEqual(status,0)
    def test_bad_response_rejected(self):
        for response in (b'',b'HTTP/1.1 500 Error\r\n',b'garbage 200 OK\r\n',b'HTTP/1.1 200 OK'):
            with self.subTest(response=response):self.assertNotEqual(self.run_probe(self.code(),response)[1],0)
class LockTests(unittest.TestCase):
    def test_candidate_uses_real_wheel_metadata_and_hash(self):
        import hashlib
        import tempfile
        import zipfile
        spec=importlib.util.spec_from_file_location('lock',ROOT/'scripts/client-preview/prepare-lock.py')
        lock=importlib.util.module_from_spec(spec);spec.loader.exec_module(lock)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'wheels';folder.mkdir()
            wheel=folder/'psycopg-0.0-py3-none-any.whl'
            with zipfile.ZipFile(wheel,'w') as z:z.writestr('psycopg-0.0.dist-info/METADATA','Name: psycopg\nVersion: 0.0\n')
            output=Path(tmp)/'candidate'
            lock.generate(folder,output)
            self.assertEqual(output.read_text(), 'psycopg[binary]==0.0 --hash=sha256:'+hashlib.sha256(wheel.read_bytes()).hexdigest()+'\n')
            with self.assertRaises(FileExistsError):lock.generate(folder,output)
            (folder/'unreviewed.tar.gz').write_bytes(b'synthetic')
            with self.assertRaises(ValueError):lock.generate(folder,Path(tmp)/'second')

if __name__=='__main__':unittest.main(verbosity=2)
