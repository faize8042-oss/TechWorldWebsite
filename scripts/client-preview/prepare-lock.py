"""Generate a REVIEW CANDIDATE from selected wheels, never resolve or download."""
import hashlib
from email.parser import BytesParser
from pathlib import Path
import re
import sys
import zipfile

def generate(wheelhouse, output):
    rows = {}
    inventory = []
    for wheel in sorted(Path(wheelhouse).iterdir()):
        if wheel.suffix != '.whl' or wheel.is_symlink(): raise ValueError('Only regular reviewed wheels allowed')
        with zipfile.ZipFile(wheel) as z:
            names = [n for n in z.namelist() if n.endswith('.dist-info/METADATA')]
            if len(names)!=1: raise ValueError('Ambiguous wheel metadata')
            meta=BytesParser().parsebytes(z.read(names[0]))
        name=re.sub(r'[-_.]+','-',meta['Name']).lower(); version=meta['Version']
        if not re.fullmatch(r'[a-z0-9-]+',name) or not re.fullmatch(r'[A-Za-z0-9.!+_-]+',version) or name in rows: raise ValueError('Invalid/duplicate package')
        digest=hashlib.sha256(wheel.read_bytes()).hexdigest()
        rows[name]=f"{name+'[binary]' if name=='psycopg' else name}=={version} --hash=sha256:{digest}"
        inventory.append(f'{digest}  {wheel.name}')
    if not rows: raise ValueError('No wheels')
    with Path(output).open('x',encoding='utf-8') as f:f.write('\n'.join(rows[n] for n in sorted(rows))+'\n')
    with Path(str(output)+'.inventory').open('x',encoding='utf-8') as f:f.write('\n'.join(inventory)+'\n')
if __name__=='__main__':generate(sys.argv[1],sys.argv[2])
