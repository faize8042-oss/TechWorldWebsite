"""Offline-first isolated validation controller. No Docker calls before explicit gate."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
LABEL = 'labs.codeventra.c621.run'
APPROVAL = 'APPROVE DISPOSABLE C6.2.1 VALIDATION'
APPS = ('config', 'core', 'projects', 'contact', 'analytics')


def clean_environment():
    # No inherited Compose, Docker context, libpq, dotenv or application variables.
    return {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')
            if key in os.environ}


def plan(run, postgres, python, source):
    if not re.fullmatch(r'[0-9a-f]{32}', run):
        raise ValueError('Invalid run identity')
    project = 'cv-c621-' + run
    labels = {LABEL: run}  # Compose adds its reserved project label itself.
    common = dict(labels=labels, networks=['isolated'], restart='no',
                  mem_limit='768m', cpus=1.0, pids_limit=256,
                  read_only=True, cap_drop=['ALL'], security_opt=['no-new-privileges:true'])
    services = {
        'db': dict(labels=labels, networks=['isolated'], restart='no', image=postgres,
                   container_name=project + '-db', mem_limit='1536m', cpus=2.0, pids_limit=256,
                   environment={'POSTGRES_USER': 'cv_init', 'POSTGRES_DB': 'codeventra',
                                'POSTGRES_PASSWORD_FILE': '/run/secrets/admin',
                                'POSTGRES_INITDB_ARGS': '--auth-host=scram-sha-256'},
                   entrypoint=['sh', '-c', 'while [ ! -f /run/secrets/ready ]; do sleep 1; done; exec docker-entrypoint.sh postgres -c log_statement=none -c log_min_error_statement=panic -c log_min_messages=panic'],
                   tmpfs=['/var/lib/postgresql/data:rw,noexec,nosuid,size=512m,uid=999,gid=999,mode=0700',
                          '/var/run/postgresql:rw,nosuid,size=16m', '/run/secrets:rw,noexec,nosuid,size=1m,mode=0700', '/tmp:rw,noexec,nosuid,size=128m'])
    }
    for service in ('web', 'migrate', 'audit'):
        services[service] = dict(common, image=python, container_name=project + '-' + service,
            user='10001:10002', working_dir='/work',
            entrypoint=['python', '-c', 'import time; time.sleep(3600)'],
            environment={'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '/work',
                         'CODEVENTRA_SKIP_DOTENV': '1'},
            volumes=[{'type': 'bind', 'source': str(source), 'target': '/work', 'read_only': True}],
            tmpfs=['/run/secrets:rw,noexec,nosuid,size=1m,uid=10001,gid=10002,mode=0700',
                   '/tmp:rw,noexec,nosuid,size=128m,uid=10001,gid=10002,mode=0700'])
    return {'name': project, 'services': services,
            'networks': {'isolated': {'name': project + '-net', 'internal': True, 'labels': labels}}}


def validate_plan(value, run, source):
    expected = plan(run, value['services']['db']['image'], value['services']['web']['image'], source)
    if value != expected:
        raise ValueError('Isolation manifest mismatch')
    encoded = json.dumps(value)
    for forbidden in ('env_file', 'external', 'ports', 'network_mode', 'privileged', 'devices', 'docker.sock'):
        if '"' + forbidden + '"' in encoded or forbidden == 'docker.sock' and forbidden in encoded:
            raise ValueError('Unsafe manifest')
    if set(value['services']) != {'db', 'web', 'migrate', 'audit'} or 'volumes' in value:
        raise ValueError('Unexpected resources')


def source_files():
    # Deliberate allowlist. Never walk uploads, validation-results, secrets or .env.
    files = [ROOT / 'manage.py', ROOT / 'deploy/postgres/fresh.sql', ROOT / 'deploy/postgres/grants.sql',
             ROOT / 'scripts/c621/probe.py']
    for app in APPS:
        directory = ROOT / app
        if directory.is_symlink() or (directory / 'migrations').is_symlink():
            raise ValueError('Source directory symlink forbidden')
        files.extend(directory.glob('*.py'))
        files.extend((directory / 'migrations').glob('*.py'))
    return sorted(set(files))


def preflight(postgres='postgres:17', python='python:3.12'):
    files = source_files()
    required = ('config/migration_settings.py', 'config/production_database.py', 'scripts/c621/probe.py',
                'deploy/postgres/fresh.sql', 'deploy/postgres/grants.sql', 'manage.py')
    for name in required:
        if ROOT / name not in files or not (ROOT / name).is_file():
            raise ValueError('Required source missing')
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('Source escape')
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=path.name)
    ast.parse(Path(__file__).read_text(encoding='utf-8-sig'))
    run = uuid.uuid4().hex
    candidate = plan(run, postgres, python, ROOT / 'synthetic-source-placeholder')
    validate_plan(candidate, run, ROOT / 'synthetic-source-placeholder')
    return files


class Docker:
    def __init__(self, deadline, directory):
        self.deadline, self.directory = deadline, directory
        self.cleanup_deadline = None
        self.env = clean_environment()
        # Prevent Docker/Compose reading user contexts/configuration or dotenv.
        self.env['DOCKER_CONFIG'] = str(directory / 'docker-config')
        (directory / 'docker-config').mkdir()
        self.env['DOCKER_HOST'] = 'npipe:////./pipe/docker_engine' if os.name == 'nt' else 'unix:///var/run/docker.sock'

    def call(self, args, stdin=None, check=True, cleanup=False):
        remaining = (self.cleanup_deadline - time.monotonic()) if cleanup else self.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('Validation deadline exceeded')
        result = subprocess.run(['docker', *args], input=stdin, text=True, capture_output=True,
                                env=self.env, cwd=self.directory, timeout=min(remaining, 20 if cleanup else 60))
        # Never display Docker output: errors/logs may contain secret-bearing values.
        if check and result.returncode:
            raise RuntimeError('Isolated Docker operation failed')
        return result



def verified_resource(docker, kind, identity, run, project):
    if not re.fullmatch(r'[0-9a-f]{64}', identity):
        raise ValueError('Invalid immutable resource ID')
    result = docker.call([kind, 'inspect', identity], cleanup=True)
    items = json.loads(result.stdout)
    if not isinstance(items, list) or len(items) != 1:
        raise ValueError('Ambiguous resource identity')
    item = items[0]
    labels = item.get('Config', {}).get('Labels', {}) if kind == 'container' else item.get('Labels', {})
    if (item.get('Id') != identity or labels.get(LABEL) != run or
            labels.get('com.docker.compose.project') != project):
        raise ValueError('Resource identity or ownership changed')
    return item


def reconcile(docker, run, project, creation, diagnostics):
    # A successful Compose CLI return is the only supported creation completion
    # boundary. Silence in discovery is never evidence of daemon quiescence.
    attempted = set()
    clean_rounds = 0
    failed = False
    diagnostics.update(creation=creation, rounds=0, observed=[], removal_errors=0)
    for round_number in range(6):
        remaining = False
        for kind in ('container', 'network', 'volume'):
            try:
                result = docker.call([kind, 'ls', *(['-a'] if kind == 'container' else []),
                    '--filter', 'label=' + LABEL + '=' + run,
                    '--filter', 'label=com.docker.compose.project=' + project,
                    '--no-trunc', '-q'] if kind != 'volume' else
                    [kind, 'ls', '--filter', 'label=' + LABEL + '=' + run, '-q'], cleanup=True)
                identities = result.stdout.splitlines()
                if len(identities) != len(set(identities)):
                    raise ValueError('Ambiguous discovery')
                for identity in identities:
                    remaining = True
                    if kind == 'volume':
                        failed = True  # Never delete volumes, including unexpected ones.
                        continue
                    item = verified_resource(docker, kind, identity, run, project)
                    if [kind, identity] not in diagnostics['observed']:
                        diagnostics['observed'].append([kind, identity])
                    key = (kind, identity)
                    if key in attempted:
                        continue
                    verified_resource(docker, kind, identity, run, project)
                    attempted.add(key)  # Never retry a possibly accepted deletion.
                    docker.call([kind, 'rm', *(['-f'] if kind == 'container' else []), identity], cleanup=True)
            except Exception:
                failed = True
                diagnostics['removal_errors'] += 1
        diagnostics['rounds'] = round_number + 1
        clean_rounds = clean_rounds + 1 if not remaining else 0
        if clean_rounds >= 3 and creation == 'COMPLETED' and not failed:
            return 'PASS'
        if round_number < 5:
            time.sleep(1)
    if creation != 'COMPLETED':
        return 'INDETERMINATE'
    return 'FAIL_OPERATOR_ACTION_REQUIRED'

def execute(args, files):
    if args.approval != APPROVAL:
        raise ValueError('Operator approval required')
    for image in (args.postgres_image, args.python_image):
        if not re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}', image):
            raise ValueError('Reviewed digest-pinned images required')
    if not args.postgres_image.startswith('postgres:17@sha256:'):
        raise ValueError('PostgreSQL 17 image required')
    run = uuid.uuid4().hex
    project = 'cv-c621-' + run
    directory = Path(tempfile.mkdtemp(prefix=project + '-'))
    source = directory / 'source'
    source.mkdir()
    manifest = plan(run, args.postgres_image, args.python_image, source)
    validate_plan(manifest, run, source)
    docker = Docker(time.monotonic() + args.timeout, directory)
    names = [v['container_name'] for v in manifest['services'].values()]
    network = project + '-net'
    owned_created = False
    status = {'run': run, 'project': project, 'validation': 'FAIL', 'cleanup': 'NOT_STARTED',
              'source_sha256': {}, 'creation': 'NOT_STARTED'}
    print('Isolated run: ' + run + '; sanitized status: ' + str(directory / 'status.json'), flush=True)

    def inspect(kind, name, cleanup=False):
        result = docker.call([kind, 'inspect', name], check=False, cleanup=cleanup)
        if result.returncode:
            # Absence must be verified by exact-name enumeration, not inferred from arbitrary errors.
            listing = docker.call([kind, 'ls', *(['-a'] if kind == 'container' else []),
                                   '--filter', 'name=' + name, '--format', '{{.Name}}' if kind == 'network' else '{{.Names}}'], cleanup=cleanup)
            if name in listing.stdout.splitlines():
                raise RuntimeError('Cannot verify resource ownership')
            return None
        items = json.loads(result.stdout)
        if not isinstance(items, list) or len(items) != 1:
            raise ValueError('Ambiguous resource inspection')
        item = items[0]
        if not re.fullmatch(r'[0-9a-f]{64}', item.get('Id', '')):
            raise ValueError('Missing immutable resource ID')
        labels = item.get('Config', {}).get('Labels', {}) if kind == 'container' else item.get('Labels', {})
        if labels.get(LABEL) != run or labels.get('com.docker.compose.project') != project:
            raise RuntimeError('Resource ownership mismatch')
        return item

    try:
        status['phase'] = 'stage_and_collision_checks'
        for path in files:
            destination = source / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            contents = path.read_bytes()
            destination.write_bytes(contents)
            status['source_sha256'][str(path.relative_to(ROOT))] = hashlib.sha256(contents).hexdigest()
        (directory / 'compose.json').write_text(json.dumps(manifest), encoding='utf-8')
        (directory / 'empty.env').write_text('', encoding='utf-8')
        # Check exact names before creating anything. A collision stops execution.
        for name in names:
            if inspect('container', name):
                raise RuntimeError('Container name collision')
        if inspect('network', network):
            raise RuntimeError('Network name collision')
        # Require reviewed local images; never pull, build, or execute registry-supplied fallback.
        for image in (args.postgres_image, args.python_image):
            metadata = json.loads(docker.call(['image', 'inspect', image]).stdout)[0]
            declared = set((metadata.get('Config', {}).get('Volumes') or {}).keys())
            allowed = {'/var/lib/postgresql/data'} if image == args.postgres_image else set()
            if declared - allowed:
                raise RuntimeError('Image declares an unexpected persistent volume')
            if image == args.postgres_image:
                image_env = metadata.get('Config', {}).get('Env') or []
                pgdata = [v for v in image_env if v.startswith('PGDATA=')]
                if pgdata != ['PGDATA=/var/lib/postgresql/data']:
                    raise RuntimeError('Image PGDATA does not match disposable tmpfs')
        status['phase'] = 'create_and_verify_isolation'
        owned_created = True  # partial Compose creation must also be cleaned up
        status['creation'] = 'UNRESOLVED'
        docker.call(['compose', '--env-file', str(directory / 'empty.env'), '-p', project,
                     '-f', str(directory / 'compose.json'), 'up', '-d', '--no-build', '--pull', 'never'])
        status['creation'] = 'COMPLETED'
        for name in names:
            item = inspect('container', name)
            if item is None or item['HostConfig'].get('PortBindings') or item['HostConfig'].get('NetworkMode') == 'host':
                raise RuntimeError('Container isolation verification failed')
            if set(item['NetworkSettings']['Networks']) != {network}:
                raise RuntimeError('Unexpected network attachment')
            if any(m.get('Type') == 'volume' for m in item.get('Mounts', [])):
                raise RuntimeError('Unexpected persistent volume')
        net = inspect('network', network)
        if not net or not net.get('Internal'):
            raise RuntimeError('Network isolation verification failed')
        status['phase'] = 'bootstrap_and_provision'
        passwords = {role: secrets.token_hex(32) for role in ('cv_init', 'cv_migrate', 'cv_runtime', 'cv_backup')}
        # Synthetic secrets travel over stdin only; no argv, manifest, host secret files or diagnostics.
        docker.call(['exec', '-i', project + '-db', 'sh', '-c',
                     'set -eu; umask 077; cat > /run/secrets/admin; chown 999:999 /run/secrets/admin; chmod 600 /run/secrets/admin; chown 999:999 /run/secrets; chmod 700 /run/secrets; test "$(stat -c %a /run/secrets/admin)" = 600; test "$(stat -c %u /run/secrets/admin)" = 999; touch /run/secrets/ready'], passwords['cv_init'])
        # Readiness retries are read-only; no mutation is automatically retried.
        while True:
            result = docker.call(['exec', project + '-db', 'pg_isready', '-h', '127.0.0.1', '-U', 'cv_init', '-d', 'codeventra'], check=False)
            if result.returncode == 0:
                break
            time.sleep(1)
        def sql(text, check=True):
            return docker.call(['exec', '-i', project + '-db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                                '-U', 'cv_init', '-d', 'codeventra'], text, check=check)
        sql((source / 'deploy/postgres/fresh.sql').read_text())
        sql((source / 'deploy/postgres/grants.sql').read_text())
        if sql((source / 'deploy/postgres/fresh.sql').read_text(), False).returncode == 0:
            raise RuntimeError('Repeated fresh provisioning unexpectedly succeeded')
        # Generated hex-only passwords are synthetic and never logged by server configuration.
        sql('\n'.join("ALTER ROLE %s PASSWORD '%s';" % (r, p) for r, p in passwords.items() if r != 'cv_init'))
        # Deliberately fail a transaction and verify that its preceding DDL is rolled back.
        if sql('BEGIN; SET ROLE cv_owner; CREATE TABLE public.c621_rollback(id int); SELECT 1/0; COMMIT;', False).returncode == 0:
            raise RuntimeError('Expected transaction failure missing')
        sql("DO $$ BEGIN IF to_regclass('public.c621_rollback') IS NOT NULL THEN RAISE EXCEPTION 'Rollback failed'; END IF; END $$;")
        for service in ('web', 'migrate', 'audit'):
            payload = {'runtime': passwords['cv_runtime']}
            if service == 'migrate':
                payload['migration'] = passwords['cv_migrate']
            if service == 'audit':
                payload = passwords
            docker.call(['exec', '-i', project + '-' + service, 'python', 'scripts/c621/probe.py', 'seed', service], json.dumps(payload))
        for service, mode in (('audit', 'sql'), ('migrate', 'migrate'), ('web', 'web'), ('audit', 'ownership')):
            status['phase'] = mode
            docker.call(['exec', project + '-' + service, 'python', 'scripts/c621/probe.py', mode])
            status[mode] = 'PASS'
        status['validation'] = 'PASS'
        status['phase'] = 'complete'
    except Exception:
        status['validation'] = 'FAIL'
    finally:
        docker.cleanup_deadline = time.monotonic() + 120
        status['cleanup_diagnostics'] = {}
        status['cleanup'] = (reconcile(docker, run, project, status['creation'],
                                      status['cleanup_diagnostics'])
                             if owned_created else 'PASS')
        (directory / 'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
        print('Sanitized status: ' + str(directory / 'status.json'))
        # Retain manifest/source hashes for review; no captured process output is persisted.
    return 0 if status['validation'] == status['cleanup'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--approval', default='')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--postgres-image', default='postgres:17')
    parser.add_argument('--python-image', default='python:3.12')
    args = parser.parse_args()
    try:
        if not 60 <= args.timeout <= 3600:
            raise ValueError('Invalid timeout')
        files = preflight(args.postgres_image, args.python_image)
        if not args.execute:
            print('PASS: offline preflight; Docker was not invoked.')
            return 0
        return execute(args, files)
    except Exception:
        print('FAIL: safety precondition or isolated validation failed; values suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
