"""Offline image audit regressions; synthetic bytes only, never contacts Docker."""
import ast
import copy
import hashlib
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'deploy/quick-client-demo'
HELPER = AUDIT / 'inspect_image.py'
BASE = json.loads((AUDIT / 'verified-images.json').read_text(encoding='utf-8-sig'))[0]
REQUIRED = ['django','psycopg','psycopg-binary','django-environ','pillow','whitenoise','django-ratelimit','gunicorn','redis','asgiref','sqlparse','packaging','typing-extensions']
MODULES = ['django','psycopg','psycopg_binary','environ','PIL','whitenoise','django_ratelimit','gunicorn','redis','asgiref','sqlparse','packaging']
MANUAL = {'independent-startup-code-and-public-asset-review-required','dependency-integrity-native-compatibility-and-provenance-review-required'}

def tar_bytes(files):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return out.getvalue()

def files():
    f = {x:b'# synthetic fixture\n' for x in ('app/manage.py','app/config/settings.py','app/config/wsgi.py','app/config/urls.py','app/requirements.txt','app/core/views.py','app/templates/index.html','app/static/style.css','app/staticfiles/style.css','usr/local/bin/gunicorn')}
    for name in REQUIRED:
        f['usr/local/lib/python3.12/site-packages/'+name+'.dist-info/METADATA'] = ('Name: '+name+'\n').encode()
    for name in MODULES:
        f['usr/local/lib/python3.12/site-packages/'+name+'/__init__.py'] = b'# fixture\n'
    return f

class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='audit fixture ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture()

    def fixture(self, layers=None, extra=None):
        layers = layers or [files()]
        blobs = [tar_bytes(f) for f in layers]
        self.observed = copy.deepcopy(BASE)
        self.observed['RootFS']['Layers'] = ['sha256:'+hashlib.sha256(b).hexdigest() for b in blobs]
        config = json.dumps({'config':self.observed['Config'], 'rootfs':{'type':'layers','diff_ids':self.observed['RootFS']['Layers']}}).encode()
        self.config_name = hashlib.sha256(config).hexdigest()+'.json'
        self.observed['Id'] = 'sha256:' + self.config_name[:-5]
        self.expected = self.observed['Id']
        self.archive = {self.config_name:config, 'manifest.json':json.dumps([{'Config':self.config_name,'Layers':['layer%d.tar'%i for i in range(len(blobs))]}]).encode()}
        self.archive.update({'layer%d.tar'%i:b for i,b in enumerate(blobs)})
        self.archive.update(extra or {})
        self.write_json('observed.json',[self.observed],bom=True)
        self.write_json('baseline.json',self.observed)
        (self.root/'history.jsonl').write_text('\ufeff'+json.dumps({'CreatedBy':'synthetic build'})+'\n\n',encoding='utf-8')
        self.save()

    def write_json(self,name,value,bom=False):
        (self.root/name).write_text(json.dumps(value),encoding='utf-8-sig' if bom else 'utf-8')
    def save(self): (self.root/'image.tar').write_bytes(tar_bytes(self.archive))
    def run_helper(self):
        r = subprocess.run([sys.executable,'-I','-S','-B',str(HELPER),str(self.root),self.expected],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.stderr,'')
        self.assertEqual(r.returncode,1) # manual review requirements remain mandatory
        return r.stdout
    def complete(self):
        out=self.run_helper(); self.assertIn('Inspection: COMPLETE',out); return out
    def failure(self,stage):
        out=self.run_helper(); self.assertIn('Failure stage: helper-'+stage+'\n',out); self.assertNotIn('Inspection: COMPLETE',out); return out

class AuditTests(FixtureCase):
    def test_gzip_layer_diffid_is_uncompressed_digest(self):
        self.archive['layer0.tar'] = gzip.compress(self.archive['layer0.tar'])
        self.save()
        self.assertIn('COUNT verified-layers: 1', self.complete())

    def test_zstd_layer(self):
        try:
            from compression import zstd
        except ImportError:
            self.skipTest('Host Python has no stdlib zstd')
        self.archive['layer0.tar'] = zstd.compress(self.archive['layer0.tar'])
        self.save()
        self.assertIn('COUNT verified-layers: 1', self.complete())

    def replace_layer(self, blob):
        self.observed['RootFS']['Layers'] = ['sha256:'+hashlib.sha256(blob).hexdigest()]
        config = json.dumps({'config':self.observed['Config'],'rootfs':{'type':'layers','diff_ids':self.observed['RootFS']['Layers']}}).encode()
        self.config_name = hashlib.sha256(config).hexdigest()+'.json'
        self.expected = 'sha256:'+self.config_name[:-5]
        self.observed['Id'] = self.expected
        self.archive = {self.config_name:config,'layer0.tar':blob,'manifest.json':json.dumps([{'Config':self.config_name,'Layers':['layer0.tar']}]).encode()}
        self.write_json('observed.json',self.observed)
        self.write_json('baseline.json',self.observed)
        self.save()

    def test_pax_gnu_metadata_symlink_and_hardlink(self):
        for fmt in (tarfile.PAX_FORMAT, tarfile.GNU_FORMAT):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf,mode='w',format=fmt) as archive:
                for name,data in files().items():
                    info=tarfile.TarInfo(name); info.size=len(data)
                    archive.addfile(info,io.BytesIO(data))
                info=tarfile.TarInfo('usr/'+'long/'*30+'file'); info.size=1
                archive.addfile(info,io.BytesIO(b'x'))
                for name,kind,target in (('bin',tarfile.SYMTYPE,'usr/bin'),('usr/link',tarfile.LNKTYPE,'usr/local/bin/gunicorn')):
                    info=tarfile.TarInfo(name); info.type=kind; info.linkname=target
                    archive.addfile(info)
            self.replace_layer(buf.getvalue())
            self.complete()

    def test_layer_order_is_bound_to_diffids(self):
        self.fixture([files(),{'other':b'x'}])
        manifest=json.loads(self.archive['manifest.json'])
        manifest[0]['Layers'].reverse()
        self.archive['manifest.json']=json.dumps(manifest).encode(); self.save()
        self.assertIn('uncompressed-layer-diffid-mismatch',self.failure('layer-integrity-and-filesystem'))

    def test_opaque_directory_preserves_same_layer_additions(self):
        self.fixture([files(),{'app/templates/new.html':b'new','app/templates/.wh..wh..opq':b''}])
        self.assertIn('COUNT template-files: 1',self.complete())

    def test_truncated_gzip_is_sanitized(self):
        self.archive['layer0.tar']=gzip.compress(self.archive['layer0.tar'])[:-5]
        self.save()
        self.assertIn('layer-decompression-failed',self.failure('layer-integrity-and-filesystem'))

    def test_wrong_config_identity_rejected(self):
        self.expected = BASE['Id']
        self.observed['Id'] = self.expected
        self.write_json('observed.json', self.observed)
        self.write_json('baseline.json', self.observed)
        self.failure('saved-archive')

    def test_oci_index_identity_and_compressed_blob(self):
        blob = gzip.compress(self.archive.pop('layer0.tar'))
        digest = hashlib.sha256(blob).hexdigest()
        config = self.archive.pop(self.config_name)
        cfg = 'blobs/sha256/' + self.config_name[:-5]
        layer = 'blobs/sha256/' + digest
        self.archive[cfg] = config
        self.archive[layer] = blob
        self.archive['manifest.json'] = json.dumps([{'Config':cfg, 'Layers':[layer]}]).encode()
        def store(value):
            data = json.dumps(value).encode()
            digest = 'sha256:' + hashlib.sha256(data).hexdigest()
            self.archive['blobs/sha256/' + digest[7:]] = data
            return {'digest':digest, 'size':len(data)}
        manifest = store({'schemaVersion':2,'config':{'digest':'sha256:'+self.config_name[:-5], 'size':len(config)},'layers':[{'digest':'sha256:'+digest,'size':len(blob)}]})
        index = store({'schemaVersion':2, 'manifests':[manifest]})
        self.expected = index['digest']
        self.observed['Id'] = self.expected
        self.write_json('observed.json',self.observed)
        self.write_json('baseline.json',self.observed)
        self.save()
        self.assertIn('COUNT saved-image-identity-verified: 1',self.complete())
        self.archive[layer] = blob + b'x'
        self.save()
        self.failure('saved-archive')

    def test_valid_metadata_archive_and_accurate_fail(self):
        out=self.complete()
        reasons={x.split()[1].rstrip(':') for x in out.splitlines() if x.startswith('FAIL ')}
        self.assertEqual(reasons,MANUAL)
        self.assertIn('COUNT verified-layers: 1',out)
    def test_malformed_metadata(self):
        for value in ([],[self.observed,self.observed],[[self.observed]],None,{'Config':[]}, {'Id':BASE['Id']}):
            with self.subTest(value=type(value)):
                self.write_json('observed.json',value); self.failure('metadata')
    def test_invalid_json_and_encoding(self):
        for data in (b'{',b'\xff',b'{"Config":{},"Config":{}}'):
            (self.root/'observed.json').write_bytes(data); self.failure('metadata')
    def test_identity_mismatch(self):
        self.observed['Id']='sha256:'+'0'*64; self.write_json('observed.json',self.observed); self.failure('metadata')
    def test_missing_spool(self):
        (self.root/'observed.json').unlink(); self.assertIn('spool-io',self.failure('metadata'))
    def test_missing_archive_member(self):
        del self.archive[self.config_name]; self.save(); self.failure('saved-archive')
    def test_corrupt_layer(self):
        self.archive['layer0.tar']=b'corrupt'; self.save(); self.failure('layer-integrity-and-filesystem')
    def test_bad_manifest(self):
        for data in (b'{}', b'[]', b'[null]', b'null'):
            self.archive['manifest.json']=data; self.save(); self.failure('saved-archive')
    def test_bad_config_digest_name(self):
        manifest=json.loads(self.archive['manifest.json']); name='prefix'+self.config_name
        self.archive[name]=self.archive.pop(self.config_name); manifest[0]['Config']=name
        self.archive['manifest.json']=json.dumps(manifest).encode(); self.save()
        self.assertIn('FAIL saved-config-digest-unverifiable:',self.complete())
    def test_empty_inventory(self):
        self.fixture([{}]); self.assertIn('FAIL required-application-file-missing:',self.complete())
    def test_missing_history(self):
        (self.root/'history.jsonl').write_text(''); self.assertIn('FAIL history-missing:',self.complete())
    def test_invalid_history(self):
        for data in ('{','[]','{"CreatedBy":null}'):
            (self.root/'history.jsonl').write_text(data); self.failure('history')
    def test_secret_patterns_and_redaction(self):
        secrets=[b'-----BEGIN PRIVATE KEY-----',b'AKIA' + b'A'*16,b'ghp_'+b'X'*25,b'https://user:password@example.test',b'password = "synthetic-password"',b'eyJabcdefgh.abcdefgh.abcdefgh']
        for secret in secrets:
            f=files(); f['app/sample.txt']=secret; self.fixture([f]); out=self.complete()
            self.assertTrue(any(x.startswith('FAIL ') and x.split()[1].rstrip(':') not in MANUAL for x in out.splitlines()))
            self.assertNotIn(secret.decode(),out); self.assertNotIn('sample.txt',out)
    def test_sensitive_files_and_deleted_secrets(self):
        f=files(); f['app/.env']=b'fixture'; self.fixture([f,{'app/.wh..env':b''}]); self.assertIn('FAIL embedded-environment-file:',self.complete())
    def test_opaque_whiteout_root(self):
        self.fixture([files(),{'.wh..wh..opq':b''}]); self.assertIn('COUNT final-inventory-entries: 0',self.complete())
    def test_whiteout_same_layer_retained_metadata(self):
        self.fixture([files(),dict(files(),**{'.wh..wh..opq':b''})]); out=self.complete()
        self.assertIn('COUNT required-distributions-present: 13',out)
    def test_replaced_metadata_cannot_remain(self):
        f=files(); key=next(x for x in f if x.endswith('django.dist-info/METADATA'))
        self.fixture([f,{key:b'no name'}]); self.assertIn('FAIL required-python-distribution-missing:',self.complete())
    def test_non_directory_replacement_hides_implicit_descendants(self):
        self.fixture([files(),{'app':b'file'}]); self.assertIn('FAIL required-application-file-missing:',self.complete())
    def test_unsafe_tar_paths(self):
        for name in ('../escape','/absolute','a/../b','a//b','a/./b','a\\b'):
            self.fixture([dict(files(),**{name:b'x'})]); self.failure('layer-integrity-and-filesystem')
    def test_invalid_whiteout(self):
        self.fixture([dict(files(),**{'app/.wh.x':b'not empty'})]); self.failure('layer-integrity-and-filesystem')
    def test_quoted_secrets_in_json_values(self):
        self.write_json('history.jsonl',{'CreatedBy':'password = "synthetic-history-secret"'})
        out=self.complete()
        self.assertIn('FAIL literal-credential-assignment:',out)
        self.assertNotIn('synthetic-history-secret',out)
    def test_truncated_outer_archive(self):
        (self.root/'image.tar').write_bytes((self.root/'image.tar').read_bytes()[:1024])
        self.failure('saved-archive')
    def test_missing_layer_member(self):
        del self.archive['layer0.tar']; self.save(); self.failure('layer-integrity-and-filesystem')
    def test_startup_hooks_require_review(self):
        f=files(); f['usr/local/lib/python3.12/site-packages/demo.pth']=b'import demo\n'
        self.fixture([f]); out=self.complete()
        self.assertIn('FAIL python-startup-hook-requires-independent-review:',out)
        self.assertIn('FAIL executable-pth-hook:',out)
    def test_private_data_path_categories(self):
        for name,reason in (('app/media/data.txt','private-state-or-unreviewed-tree'),('app/data.sqlite3','data-key-log-or-nested-archive'),('root/.aws/credentials','credential-file'),('app/secret.txt','sensitive-filename')):
            self.fixture([dict(files(),**{name:b'synthetic'})])
            self.assertIn('FAIL '+reason+':',self.complete())
    def test_python_314_syntax_and_policy(self):
        ast.parse(HELPER.read_text()); self.assertGreaterEqual(sys.version_info[:2],(3,6))
        policy=ast.parse(HELPER.read_text()).body[1]
        namespace={}
        exec(compile(ast.Module(body=[policy],type_ignores=[]),'policy','exec'),namespace)
        for version,expected in (((3,5),False),((3,6),True),((3,14),True),((4,0),False)):
            self.assertEqual(namespace['audit_python_supported'](version),expected)
    def test_powershell_baseline_and_probe(self):
        for args in ([str(AUDIT/'test-image-baseline.ps1')],[str(AUDIT/'audit-image.ps1'),'-Python',sys.executable,'-TestPythonOffline']):
            r=subprocess.run(['powershell.exe','-NoProfile','-File',*args],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)



class WrapperTests(FixtureCase):
    def wrapper(self, helper=None, docker_fail=False, sabotage=False, expected_code=1):
        target=self.root/'wrapper/deploy/quick-client-demo'; target.mkdir(parents=True,exist_ok=True)
        source=(AUDIT/'audit-image.ps1').read_text(encoding='utf-8-sig')
        source=source.replace(BASE['Id'], self.expected)
        a=source.index('function Invoke-DockerPrivate('); b=source.index('function Invoke-NativePrivate(',a)
        fixture=str(self.root).replace("'","''")
        mock="""function Invoke-DockerPrivate([string[]]$Arguments) {
    if ($Arguments[0] -cne 'image') { throw 'Invalid Docker verb' }
    if ($Arguments[1] -eq 'inspect') { if ($Arguments.Count -ne 3) { throw 'Invalid inspect arguments' }; return [IO.File]::ReadAllText('FIXTURE/observed.json') }
    if ($Arguments[1] -eq 'history') { if ($Arguments.Count -ne 6 -or $Arguments[2] -cne '--no-trunc' -or $Arguments[3] -cne '--format' -or $Arguments[4] -cne '{{json .}}' -or $Arguments[5] -cne $expected) { throw 'Invalid history arguments' }; return [IO.File]::ReadAllText('FIXTURE/history.jsonl') }
    if ($Arguments[1] -eq 'save') { if ($Arguments.Count -ne 5 -or $Arguments[2] -cne '--output' -or $Arguments[4] -cne $expected) { throw 'Invalid save arguments' }; [IO.File]::Copy('FIXTURE/image.tar', $Arguments[3]); return '' }
    throw 'Unexpected Docker command'
}
""".replace('FIXTURE',fixture)
        if docker_fail: mock="function Invoke-DockerPrivate([string[]]$Arguments) { throw 'PRIVATE SENTINEL' }\n"
        source=source[:a]+mock+source[b:]
        source=source.replace("$dockerCommand = (Get-Command docker -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source", "$dockerCommand = 'offline-mock-no-engine'")
        if sabotage:
            source=source.replace("$helperCode = $reply.Code", "$helperCode = $reply.Code\n    [IO.File]::WriteAllText((Join-Path $temp 'unexpected'), 'synthetic')\n    [IO.File]::WriteAllText('FIXTURE/spool-location', $temp)".replace('FIXTURE',fixture))
        (target/'audit-image.ps1').write_text(source,encoding='utf-8-sig')
        (target/'image-baseline.ps1').write_bytes((AUDIT/'image-baseline.ps1').read_bytes())
        (target/'inspect_image.py').write_text(HELPER.read_text() if helper is None else helper,encoding='utf-8')
        self.write_json('wrapper/deploy/quick-client-demo/verified-images.json',[self.observed])
        r=subprocess.run(['powershell.exe','-NoProfile','-File',str(target/'audit-image.ps1'),'-Python',sys.executable],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,expected_code,r.stdout+r.stderr)
        self.assertEqual(r.stderr,'')
        report=(target/'image-audit-report.txt').read_text(encoding='utf-8-sig')
        self.assertNotIn('PRIVATE SENTINEL',report+r.stdout+r.stderr)
        self.assertIn('Final verdict: '+('FAIL' if expected_code else 'PASS'),report)
        return report
    def test_full_mocked_pipeline_and_cleanup(self):
        out=self.wrapper(); self.assertIn('Inspection: COMPLETE',out)
        self.assertIn('Temporary private spool: removed',out)
        self.assertIn('Failure stage: content-policy',out)
        self.assertNotIn('Failure stage: filesystem-inspection',out)
    def test_native_failure_pipeline(self):
        out=self.wrapper(docker_fail=True); self.assertIn('Failure stage: tag-inspection',out)
    def test_unexpected_helper_termination(self):
        out=self.wrapper(helper='import os; os._exit(7)'); self.assertIn('Failure stage: filesystem-inspection',out); self.assertIn('Temporary private spool: removed',out)
    def test_zero_exit_without_evidence(self):
        self.assertIn('Failure stage: filesystem-inspection',self.wrapper(helper='pass'))
    def test_partial_and_contradictory_helper_output(self):
        helper="print('Inspection: COMPLETE (static checks only; manual gates remain unresolved)'); print('Verdict: FAIL')"
        self.assertIn('Failure stage: filesystem-inspection',self.wrapper(helper=helper))
    def test_native_argument_streams_and_nonzero_exit(self):
        source=(AUDIT/'audit-image.ps1').read_text(encoding='utf-8-sig')
        function=source[source.index('function Invoke-NativePrivate('):source.index('\ntry {\n    # Replace any stale verdict')]
        script=self.root/'native runner.ps1'
        script.write_text("$ErrorActionPreference='Stop'\n"+function+"\n"+r'''
$code = 'import json,sys; print(json.dumps(sys.argv[1:],ensure_ascii=True)); sys.stderr.write("private diagnostics"); sys.exit(9)'
$reply = Invoke-NativePrivate 'PYTHON' @('-I','-S','-B','-c',$code,'path with spaces','quote"here','C:\trailing\',('unicode-'+[char]0x00e9))
if ($reply.Code -ne 9 -or -not $reply.ErrorPresent) { throw 'Exit or stderr capture failed' }
$parsed = ConvertFrom-Json $reply.Output
if ($parsed.Count -ne 4 -or $parsed[0] -cne 'path with spaces' -or $parsed[1] -cne 'quote"here' -or $parsed[2] -cne 'C:\trailing\') { throw 'Argument roundtrip failed' }
$reply = Invoke-NativePrivate 'PYTHON' @('-I','-S','-B','-c','import sys; sys.stdout.write("a"*2000000); sys.stderr.write("b"*500000)')
if ($reply.Output.Length -ne 2000000 -or -not $reply.ErrorPresent) { throw 'Large stream failure' }
$rejected = $false
try { $null = Invoke-NativePrivate 'PYTHON' @('-I','-S','-B','-c','import sys; sys.stderr.write("b"*2000000)') } catch { $rejected = $true }
if (-not $rejected) { throw 'Output limit bypass' }
$rejected = $false
try { $null = Invoke-NativePrivate 'PYTHON' @('-I','-S','-B','-c','import sys; sys.stdout.buffer.write(bytes([255])+b"x"*2000000)') } catch { $rejected = $true }
if (-not $rejected) { throw 'Invalid encoding bypass' }
'''.replace('PYTHON',sys.executable.replace("'","''")),encoding='utf-8-sig')
        r=subprocess.run(['powershell.exe','-NoProfile','-File',str(script)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_missing_count_evidence_rejected(self):
        helper="print('Inspection: COMPLETE (static checks only; manual gates remain unresolved)'); print('Verdict: FAIL'); raise SystemExit(1)"
        self.assertIn('Failure stage: filesystem-inspection',self.wrapper(helper=helper))
    def test_unexpected_stdout_and_stderr_rejected(self):
        for helper in ("print('PRIVATE SENTINEL')", "import sys; sys.stderr.write('PRIVATE SENTINEL')"):
            self.assertIn('Failure stage: filesystem-inspection',self.wrapper(helper=helper))
    def passing_protocol_fixture(self):
        # Exercises orchestration's PASS branch only. Production review gates remain intact.
        helper=HELPER.read_text()
        for reason in MANUAL:
            helper=helper.replace("fail('"+reason+"')",'pass # synthetic protocol fixture only')
        return helper
    def test_final_verdict_calculation_synthetic_pass(self):
        self.assertIn('Final verdict: PASS',self.wrapper(helper=self.passing_protocol_fixture(),expected_code=0))
    def test_cleanup_failure_overrides_synthetic_pass(self):
        try:
            out=self.wrapper(helper=self.passing_protocol_fixture(),sabotage=True)
            self.assertIn('Failure stage: temporary-spool-cleanup',out)
        finally:
            location=self.root/'spool-location'
            if location.exists():
                spool=Path(location.read_text())
                self.assertEqual(spool.parent,Path(tempfile.gettempdir()))
                self.assertRegex(spool.name,r'^codeventra-image-audit-[a-f0-9]{32}$')
                for child in spool.iterdir():
                    self.assertTrue(child.is_file() and not child.is_symlink())
                    child.unlink()
                spool.rmdir()

if __name__=='__main__': unittest.main()
