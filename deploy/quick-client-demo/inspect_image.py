import sys
def audit_python_supported(version):
    return version[0] == 3 and version[:2] >= (3, 6)
import ast, collections, gzip, hashlib, io, json, pathlib, re, sys, tarfile, tempfile
stage = 'metadata'
detail = None

def reject(category):
    global detail
    detail = category
    raise ValueError()
def sanitized_exception(kind, value, traceback):
    category = ('resource-limit' if issubclass(kind, MemoryError) else
                'spool-io' if issubclass(kind, OSError) else
                'invalid-data-or-integrity' if issubclass(kind, (ValueError, KeyError, TypeError, tarfile.TarError)) else
                'helper-runtime')
    print('Failure stage: helper-' + stage)
    print('Error category: ' + category)
    if detail: print('Failure detail: ' + detail)
sys.excepthook = sanitized_exception
if len(sys.argv) != 3: raise ValueError()
root = pathlib.Path(sys.argv[1])
expected = sys.argv[2]
if not re.fullmatch(r'sha256:[a-f0-9]{64}', expected): raise ValueError()
if not audit_python_supported(sys.version_info): raise RuntimeError()

issues = collections.Counter()
counts = collections.Counter()
def fail(reason): issues[reason] += 1
def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError()
        result[key] = value
    return result

def reject_constant(value): raise ValueError()

def decode_json(data):
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)

def load(name):
    if (root / name).stat().st_size > 16*1024*1024: raise ValueError()
    value = decode_json((root / name).read_text(encoding='utf-8-sig'))
    if isinstance(value, list):
        if name == 'baseline.json':
            if any(not isinstance(item, dict) for item in value): raise ValueError()
            value = [item for item in value if isinstance(item.get('RepoTags'), list)
                     and 'techworld-django:local' in item['RepoTags']]
        if len(value) != 1: raise ValueError()
        value = value[0]
    if not isinstance(value, dict) or not isinstance(value.get('Config'), dict): raise ValueError()
    fs = value.get('RootFS')
    if not isinstance(fs, dict) or fs.get('Type') != 'layers': raise ValueError()
    layers = fs.get('Layers')
    if not isinstance(layers, list) or not layers: raise ValueError()
    if any(not isinstance(x, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}', x) for x in layers): raise ValueError()
    for key in ('Env', 'Cmd'):
        items = value['Config'].get(key)
        if not isinstance(items, list) or any(not isinstance(x, str) for x in items): raise ValueError()
    return value

def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'))
def scan(data):
    # Findings never include matched text, file paths, hashes of private data, or values.
    patterns = {
        'private-key-material': rb'-----BEGIN (?:[A-Z0-9 ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----',
        'cloud-or-service-token': rb'(?:AKIA|ASIA)[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk_(?:live|test)_[A-Za-z0-9]{16,}',
        'jwt-like-token': rb'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}',
        'credential-bearing-url': rb'[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:@]{1,128}:[^\s/@]{1,256}@',
        'literal-credential-assignment': rb'''(?im)(?:secret[_-]?key|password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[=:]\s*["'](?!["']|\s*\$|\s*\{)[^"'\r\n]{4,}["']''',
    }
    for reason, pattern in patterns.items():
        if re.search(pattern, data): fail(reason)

def scan_values(value):
    # JSON escaping must not conceal quoted assignments or tokens in strings.
    if isinstance(value, str): scan(value.encode('utf-8'))
    elif isinstance(value, dict):
        for key, item in value.items():
            scan_values(key)
            scan_values(item)
    elif isinstance(value, list):
        for item in value: scan_values(item)

observed, baseline = load('observed.json'), load('baseline.json')
if observed.get('Id') != expected or baseline.get('Id') != expected: raise ValueError()
if (observed.get('Os'), observed.get('Architecture')) != ('linux', 'amd64'): fail('unexpected-platform')
config = observed['Config']
scan(canonical(observed).encode())
scan_values(observed)
for key in ('User', 'WorkingDir', 'Entrypoint', 'Cmd', 'Env', 'Labels', 'Volumes', 'Healthcheck', 'Shell', 'OnBuild', 'ExposedPorts'):
    if canonical(config.get(key)) != canonical(baseline['Config'].get(key)): fail('configuration-differs-from-baseline')
    scan(canonical(config.get(key)).encode())
if canonical(observed.get('RootFS')) != canonical(baseline.get('RootFS')): fail('layer-list-differs-from-baseline')
if config.get('User') != 'appuser' or config.get('WorkingDir') != '/app': fail('unexpected-user-or-workdir')
if config.get('Entrypoint') or config.get('Volumes') or config.get('OnBuild') or config.get('Healthcheck'): fail('unexpected-execution-hook-or-mount')
expected_cmd = ['gunicorn','config.wsgi:application','--bind','0.0.0.0:8000','--workers','2','--access-logfile','-','--error-logfile','-']
if config.get('Cmd') != expected_cmd: fail('unexpected-command')
allowed_env = {'PATH','LANG','GPG_KEY','PYTHON_VERSION','PYTHON_SHA256','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED'}
for item in config.get('Env', []):
    name, separator, value = item.partition('=')
    if not separator or name not in allowed_env: fail('unreviewed-environment-name')
counts['environment-names-inspected'] = len(config.get('Env', []))
counts['labels-inspected'] = len(config.get('Labels') or {})
stage = 'history'
if (root / 'history.jsonl').stat().st_size > 64*1024*1024: raise ValueError()
history = (root / 'history.jsonl').read_text(encoding='utf-8-sig')
for line in history.splitlines():
    if not line.strip(): continue
    row = decode_json(line)
    if not isinstance(row, dict) or not isinstance(row.get('CreatedBy'), str): raise ValueError()
    scan(canonical(row).encode())
    scan_values(row)
    counts['history-entries-inspected'] += 1
if not counts['history-entries-inspected']: fail('history-missing')

def safe_name(name):
    if not isinstance(name, str): raise ValueError()
    while name.startswith('./'): name = name[2:]
    if name.startswith('/') or '\\' in name or '..' in name.split('/') or '\x00' in name or re.match(r'^[A-Za-z]:', name): reject('unsafe-archive-path')
    name = name.rstrip('/')
    if name in ('', '.'): return ''
    if any(part in ('', '.') for part in name.split('/')): raise ValueError()
    return name
def suspicious_path(name, size):
    low = name.lower()
    parts = low.split('/')
    base = parts[-1]
    if base == '.env' or base.startswith('.env.') or base.endswith('.env'): fail('embedded-environment-file')
    if any(p in {'.ssh','.aws','.azure','.kube','.config','private_uploads','uploads','media','backups','.git','.venv','venv','node_modules'} for p in parts[:-1]) and size:
        fail('private-state-or-unreviewed-tree')
    if re.search(r'(?:^|/)(?:id_rsa|id_ed25519|authorized_keys|known_hosts|credentials|\.netrc|\.npmrc|\.pypirc|\.pgpass|\.docker/config\.json)(?:$|\.)', low): fail('credential-file')
    if re.search(r'\.(?:sqlite3?|db|sql|dump|bak|pem|key|p12|pfx|jks|log|zip|tgz|gz|7z|rar)$', base) and size: fail('data-key-log-or-nested-archive')
    if any(word in base for word in ('credential','service-account','service_account','token','secret')) and low.startswith(('app/','root/','home/')) and size: fail('sensitive-filename')

inventory = {}
retained = {}
total = 0
expanded_total = 0
stage = 'saved-archive'
with tarfile.open(root / 'image.tar', 'r:') as outer:
    members = []
    for member in outer:
        members.append(member)
        if len(members) > 20000: raise ValueError()
    names = [safe_name(m.name) for m in members]
    if len(names) != len(set(names)): raise ValueError()
    by_name = dict(zip(names, members))
    def read_outer(name, limit):
        normalized = safe_name(name)
        if normalized not in by_name: reject('missing-archive-member')
        member = by_name[normalized]
        if not member.isfile() or member.size > limit: raise ValueError()
        data = outer.extractfile(member).read()
        if len(data) != member.size: raise ValueError()
        return data
    manifest = decode_json(read_outer('manifest.json', 4*1024*1024))
    if not isinstance(manifest, list) or len(manifest) != 1 or not isinstance(manifest[0], dict): raise ValueError()
    entry = manifest[0]
    saved_config_bytes = read_outer(entry['Config'], 16*1024*1024)
    saved_config = decode_json(saved_config_bytes)
    if not isinstance(saved_config, dict) or not isinstance(saved_config.get('rootfs'), dict): raise ValueError()
    scan(saved_config_bytes)
    scan_values(saved_config)
    if canonical(saved_config.get('config')) != canonical(config): fail('saved-configuration-mismatch')
    diffs = observed['RootFS']['Layers']
    if saved_config.get('rootfs', {}).get('diff_ids') != diffs: fail('saved-layer-identity-mismatch')
    if not isinstance(entry['Layers'], list) or len(entry['Layers']) != len(diffs): raise ValueError()
    # Config IDs and OCI manifest/index IDs are distinct. Bind either identity
    # cryptographically to this exact config and the ordered saved layer blobs.
    counts['saved-config-sha256-verified-against-name'] = 0
    config_digest = hashlib.sha256(saved_config_bytes).hexdigest()
    if entry['Config'] not in (config_digest + '.json', 'blobs/sha256/' + config_digest): fail('saved-config-digest-unverifiable')
    else: counts['saved-config-sha256-verified-against-name'] = 1
    def descriptor_bytes(desc):
        if not isinstance(desc, dict): reject('invalid-oci-descriptor')
        digest = desc.get('digest')
        if not isinstance(digest, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}', digest): reject('unsupported-oci-digest')
        data = read_outer('blobs/sha256/' + digest[7:], 16*1024*1024)
        if len(data) != desc.get('size') or hashlib.sha256(data).hexdigest() != digest[7:]: reject('oci-descriptor-integrity')
        return data
    if expected != 'sha256:' + config_digest:
        # Walk only hash-verified descriptors; never accept inspect's claimed ID
        # as proof of a config relationship.
        identity_path = 'blobs/sha256/' + expected[7:]
        identity_bytes = read_outer(identity_path, 16*1024*1024)
        if hashlib.sha256(identity_bytes).hexdigest() != expected[7:]: reject('image-identity-digest-mismatch')
        def binds(data, depth=0):
            if depth > 8: reject('oci-index-depth-limit')
            node = decode_json(data)
            if not isinstance(node, dict): reject('invalid-oci-document')
            if 'manifests' in node:
                children = node['manifests']
                if not isinstance(children, list) or len(children) > 100: reject('invalid-oci-index')
                return any(binds(descriptor_bytes(child), depth+1) for child in children)
            desc = node.get('config')
            if not isinstance(desc, dict): reject('invalid-oci-manifest')
            cfg = descriptor_bytes(desc)
            if cfg != saved_config_bytes: return False
            layers = node.get('layers')
            if not isinstance(layers, list) or len(layers) != len(entry['Layers']): return False
            for desc, name in zip(layers, entry['Layers']):
                if not isinstance(desc, dict) or name != 'blobs/sha256/' + str(desc.get('digest', ''))[7:]: return False
                if desc.get('size') != by_name[safe_name(name)].size: return False
            return True
        if not binds(identity_bytes): reject('image-identity-config-binding-mismatch')
    counts['saved-image-identity-verified'] = 1
    stage = 'layer-integrity-and-filesystem'
    for layer_name, digest in zip(entry['Layers'], diffs):
        if safe_name(layer_name) not in by_name: reject('missing-archive-member')
        layer = by_name[safe_name(layer_name)]
        if not layer.isfile(): raise ValueError()
        stream = outer.extractfile(layer)
        h = hashlib.sha256()
        while True:
            chunk = stream.read(1024*1024)
            if not chunk: break
            h.update(chunk)
        stored_digest = h.hexdigest()
        if layer_name.startswith('blobs/sha256/') and layer_name != 'blobs/sha256/' + stored_digest:
            reject('stored-layer-digest-mismatch')
        # Docker legacy saves contain raw tar; containerd/OCI saves can retain
        # gzip blobs. DiffIDs always hash the complete UNCOMPRESSED tar bytes,
        # including padding, rather than compressed bytes or reserialized tar.
        raw = outer.extractfile(layer)
        magic = raw.read(4)
        raw.seek(0)
        decoded = gzip.GzipFile(fileobj=raw) if magic[:2] == b'\x1f\x8b' else raw
        if magic == b'\x28\xb5\x2f\xfd':
            try:
                from compression import zstd
            except ImportError:
                reject('unsupported-zstd-layer-compression')
            decoded = zstd.ZstdFile(raw, 'rb')
        uncompressed = tempfile.SpooledTemporaryFile(max_size=8*1024*1024, dir=str(root))
        h = hashlib.sha256()
        size = 0
        try:
            while True:
                chunk = decoded.read(1024*1024)
                if not chunk: break
                size += len(chunk)
                expanded_total += len(chunk)
                if expanded_total > 8*1024**3: reject('layer-expansion-limit')
                h.update(chunk)
                uncompressed.write(chunk)
        except (OSError, EOFError):
            reject('layer-decompression-failed')
        if 'sha256:' + h.hexdigest() != digest: reject('uncompressed-layer-diffid-mismatch')
        uncompressed.seek(0)
        # Scan every historical regular file; no host extraction or execution.
        additions = {}
        layer_retained = {}
        layer_retained_size = 0
        deletions = []
        seen = set()
        with tarfile.open(fileobj=uncompressed, mode='r|') as archive:
            for member in archive:
                name = safe_name(member.name)
                if not name:
                    if not member.isdir(): raise ValueError()
                    continue
                if name in seen: raise ValueError()
                seen.add(name)
                counts['layer-entries-inspected'] += 1
                if counts['layer-entries-inspected'] > 1000000: raise ValueError()
                base = name.rsplit('/',1)[-1]
                parent = name.rsplit('/',1)[0] if '/' in name else ''
                if base.startswith('.wh.'):
                    if not member.isfile() or member.size or base == '.wh.': raise ValueError()
                    if base != '.wh..wh..opq' and base[4:] in ('.', '..'):
                        reject('unsafe-archive-path')
                    deletions.append((parent, base))
                    continue
                suspicious_path(name, member.size)
                if member.issym() or member.islnk():
                    # Never follow links. Relevant aliases would make verification ambiguous.
                    target = member.linkname
                    # Linux symlinks may legitimately be absolute or use '..'.
                    # They are never followed; hardlink names are archive paths.
                    if member.islnk(): safe_name(target)
                    if '\x00' in target: reject('unsafe-link-target')
                    if name.startswith('app/') or 'site-packages/' in name: fail('application-or-dependency-link-needs-review')
                    scan(target.encode('utf-8', 'replace'))
                elif member.isfile():
                    if member.size > 128*1024*1024: raise ValueError()
                    total += member.size
                    if total > 8*1024**3: raise ValueError()
                    data = archive.extractfile(member).read()
                    if len(data) != member.size: raise ValueError()
                    scan(data)
                    counts['historical-files-scanned'] += 1
                    hook = base in ('sitecustomize.py','usercustomize.py') or base.endswith('.pth')
                    startup = name.startswith('app/config/') and base.endswith('.py') or base in ('manage.py','gunicorn.conf.py','uwsgi.ini','supervisord.conf') or 'entrypoint' in base
                    if hook:
                        counts['python-startup-hooks'] += 1
                        fail('python-startup-hook-requires-independent-review')
                        if base.endswith('.pth') and re.search(rb'(?m)^\s*import[ \t]', data): fail('executable-pth-hook')
                    if startup:
                        counts['startup-files-inspected'] += 1
                        if base.endswith('.py'):
                            try: ast.parse(data)
                            except (SyntaxError, ValueError): fail('startup-python-parse-failed')
                        if re.search(rb'\b(?:exec|eval|subprocess|os\.system|Popen|requests|urllib)\b', data): fail('startup-dynamic-execution-or-network-reference')
                    if name.endswith('.dist-info/METADATA') or name == 'app/requirements.txt':
                        if len(data) > 4*1024*1024: raise ValueError()
                        layer_retained_size += len(data)
                        if layer_retained_size > 128*1024*1024: raise ValueError()
                        layer_retained[name] = data
                elif not member.isdir():
                    fail('special-files-require-review')
                additions[name] = 'file' if member.isfile() else 'dir' if member.isdir() else 'link'
        uncompressed.close()
        for parent, base in deletions:
            target = parent if base == '.wh..wh..opq' else (parent + '/' if parent else '') + base[4:]
            for name in list(inventory):
                opaque = base == '.wh..wh..opq'
                if not target or (not opaque and name == target) or name.startswith(target + '/'):
                    inventory.pop(name, None); retained.pop(name, None)
        # A non-directory replacement hides older descendants.
        # Index implicit parents once; ordinary file replacement must not scan
        # the complete inventory for every file in a large dependency layer.
        parents_with_descendants = set()
        for old in inventory:
            parts = old.split('/')
            parents_with_descendants.update('/'.join(parts[:i]) for i in range(1, len(parts)))
        for name, kind in additions.items():
            if kind != 'dir' and name in parents_with_descendants:
                for old in list(inventory):
                    if old.startswith(name + '/'):
                        inventory.pop(old, None); retained.pop(old, None)
            retained.pop(name, None)
            inventory[name] = kind
            parts = name.split('/')
            parents_with_descendants.update('/'.join(parts[:i]) for i in range(1, len(parts)))
        retained.update(layer_retained)
        if sum(len(data) for data in retained.values()) > 128*1024*1024: raise ValueError()
        counts['verified-layers'] += 1

stage = 'final-inventory'
for name in inventory:
    parts = name.split('/')
    for index in range(1, len(parts)):
        parent = '/'.join(parts[:index])
        if parent in inventory and inventory[parent] != 'dir': fail('ambiguous-filesystem-ancestor')
for name in ('app/manage.py','app/config/settings.py','app/config/wsgi.py','app/config/urls.py','app/requirements.txt','app/core/views.py'):
    if inventory.get(name) != 'file': fail('required-application-file-missing')
for prefix in ('app/templates/','app/static/','app/staticfiles/'):
    n = sum(kind == 'file' and name.startswith(prefix) for name,kind in inventory.items())
    counts[{'app/templates/':'template-files','app/static/':'static-source-files','app/staticfiles/':'collected-static-files'}[prefix]] = n
    if not n: fail('required-template-or-static-tree-missing')
required = {'django','psycopg','psycopg-binary','django-environ','pillow','whitenoise','django-ratelimit','gunicorn','redis','asgiref','sqlparse','packaging','typing-extensions'}
installed = set()
for name,data in retained.items():
    if name not in inventory or not name.endswith('.dist-info/METADATA'): continue
    match = re.search(rb'(?m)^Name: ([A-Za-z0-9_.-]+)\r?$', data)
    if match: installed.add(re.sub(r'[-_.]+','-',match[1].decode().lower()))
counts['required-distributions-present'] = len(required & installed)
if required - installed: fail('required-python-distribution-missing')
for module in ('django','psycopg','psycopg_binary','environ','PIL','whitenoise','django_ratelimit','gunicorn','redis','asgiref','sqlparse','packaging'):
    if not any('/site-packages/' + module + '/' in '/' + name and kind == 'file' for name,kind in inventory.items()): fail('required-python-module-files-missing')
if inventory.get('usr/local/bin/gunicorn') != 'file': fail('gunicorn-launcher-missing')
counts['final-inventory-entries'] = len(inventory)
# Static signatures cannot classify private client assets or approve arbitrary startup code.
# These are mandatory unresolved gates, not a pretend automated safety certification.
fail('independent-startup-code-and-public-asset-review-required')
fail('dependency-integrity-native-compatibility-and-provenance-review-required')
for name in sorted(counts): print('COUNT ' + name + ': ' + str(counts[name]))
for name in sorted(issues): print('FAIL ' + name + ': ' + str(issues[name]))
print('Inspection: COMPLETE (static checks only; manual gates remain unresolved)')
print('Verdict: FAIL' if issues else 'Verdict: PASS (static scope only; no public exposure approval)')
sys.exit(1 if issues else 0)
