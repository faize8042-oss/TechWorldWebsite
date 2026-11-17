"""Launch and clean up the disposable release rehearsal on Windows or Linux."""
import json
from pathlib import Path
import subprocess
import uuid

root = Path(__file__).resolve().parents[1]
token = uuid.uuid4().hex
volume = 'tbh-release-qa-' + token[:12] + '-operator'
controller = 'docker:cli@sha256:34507eb5069d8be82c95dd3b6987d4250fd5fee49b82e2509b7d7a7030740d6d'
created = False
try:
    subprocess.run(['docker', 'volume', 'create', '--label', 'techbullionhub.qa=' + token, volume], check=True, capture_output=True)
    created = True
    info = json.loads(subprocess.check_output(['docker', 'volume', 'inspect', volume]))[0]
    mount = info['Mountpoint']
    subprocess.run(['docker', 'run', '--rm', '--network', 'bridge', '--user', '0:0', '--env', 'TBH_QA_TOKEN=' + token,
                    '--mount', f'type=volume,source={volume},target={mount}',
                    '--mount', f'type=bind,source={root},target=/workspace,readonly',
                    '--mount', 'type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock',
                    controller, 'sh', '-ec', 'apk add --no-cache python3 age openssl >/dev/null; python3 /workspace/scripts/rehearse_release.py'], check=True)
finally:
    if created:
        info = json.loads(subprocess.check_output(['docker', 'volume', 'inspect', volume]))[0]
        if info['Labels'].get('techbullionhub.qa') != token:
            raise RuntimeError('Refusing to remove an unowned volume.')
        subprocess.run(['docker', 'volume', 'rm', volume], check=True, capture_output=True)
