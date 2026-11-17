"""Disposable Linux deployment rehearsal; run inside docker:cli with Python/age/openssl.

Needs the Docker socket and this checkout at /workspace. Uses only a unique QA
project and labeled QA volume. Never connects to the development database.
"""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/workspace')
spec = importlib.util.spec_from_file_location('release', ROOT / 'deploy/release/release.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
token = os.environ['TBH_QA_TOKEN']
if not __import__('re').fullmatch('[a-f0-9]{32}', token):
    raise ValueError('Invalid QA token.')
project = 'tbh-release-qa-' + token[:12]
volume = project + '-operator'
created = False


def docker(*args, capture=False, data=None):
    return r.run(['docker', *args], capture=capture, data=data)


try:
    info = json.loads(docker('volume', 'inspect', volume, capture=True))[0]
    if info['Labels'].get('techbullionhub.qa') != token:
        raise RuntimeError('QA volume ownership mismatch.')
    created = True
    mount = info['Mountpoint']
    # The outer controller mounts this QA volume at the daemon's own mount path.
    # This permits real Linux file-backed secrets with real ownership/mode checks.
    if not Path(mount).is_dir():
        raise RuntimeError('QA volume must be mounted at its daemon Mountpoint in the controller.')
    r.STATE = Path(mount) / 'state'
    r.PROJECT = project
    r.ROOT = ROOT
    config = json.loads((ROOT / 'deploy/release/config.example.json').read_text())
    keys = Path(mount) / 'test-age-key'
    subprocess.run(['age-keygen', '-o', str(keys)], check=True, capture_output=True)
    recipient = subprocess.run(['age-keygen', '-y', str(keys)], check=True, capture_output=True, text=True).stdout.strip()
    config.update(domain='preview.techbullionhub.test', smtp_host='smtp.mail.test', smtp_user='synthetic-user', backup_recipient=recipient, backup_directory=mount + '/backups')
    config_path = Path(mount) / 'input.json'
    config_path.write_text(json.dumps(config))
    r.getpass.getpass = lambda prompt: 'synthetic-smtp-password'
    r.configure(config_path)
    original_run = subprocess.run
    def diagnostic_run(*args, **kwargs):
        result = original_run(*args, **kwargs)
        if result.returncode and isinstance(result.stderr, str):
            message = result.stderr
            sensitive = ['synthetic-smtp-password']
            sensitive.extend(json.loads((r.STATE / 'secrets/roles.json').read_text()).values())
            sensitive.extend((r.STATE / 'secrets' / name).read_text().strip() for name in ('admin', 'redis-password'))
            for value in sensitive:
                message = message.replace(value, '[redacted]')
            print(message[-8000:], file=sys.stderr)
        return result
    subprocess.run = diagnostic_run
    r.build()
    compose_path = r.STATE / 'compose.json'
    data = json.loads(compose_path.read_text())
    for resource in ('volumes', 'networks'):
        if any(not item.get('name', '').startswith(project + '_') for item in data[resource].values()):
            raise RuntimeError('Generated resources are not isolated to the QA project.')
    data['services']['nginx']['ports'] = [{'target': 443, 'published': '0', 'host_ip': '127.0.0.1', 'protocol': 'tcp'}, {'target': 80, 'published': '0', 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]
    data['services']['nginx']['extra_hosts'] = [config['domain'] + ':127.0.0.1', 'www.' + config['domain'] + ':127.0.0.1']
    # Certificates are test-only self-signed files, never accepted by live checks.
    certroot = Path(mount) / 'certificates'
    cert = certroot / 'live' / config['domain']
    cert.mkdir(parents=True)
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=' + config['domain'], '-keyout', str(cert / 'privkey.pem'), '-out', str(cert / 'fullchain.pem')], check=True, capture_output=True)
    for entry in data['services']['nginx']['volumes']:
        if entry['target'] == '/etc/letsencrypt':
            entry['source'] = str(certroot)
    compose_path.write_text(json.dumps(data))
    r.install()
    (r.STATE / 'nginx.conf').write_text(r.nginx_config(config['domain'], True))
    r.compose('up', '-d', '--no-deps', 'nginx')
    # Curl runs inside the proxy network; checks real TLS+private socket routing.
    def request(path='/', host=None):
        domain = host or config['domain']
        return r.compose('exec', '-T', 'nginx', 'wget', '-S', '-O', '-', '--no-check-certificate', 'https://' + domain + path, capture=True)
    for attempt in range(25):
        try:
            page = request()
            if 'TechBullion Hub' in page:
                break
        except RuntimeError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Proxy did not become ready.')
    assert 'noindex' in page
    for path in ('/services/', '/projects/', '/contact/', '/blog/', '/news/', '/privacy/', '/terms/', '/robots.txt', '/sitemap.xml'):
        request(path)
    r.compose('run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'audit_public_seo')
    r.compose('run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'shell', '-c', "from django.db import connection, DatabaseError; from pathlib import Path; assert not Path('/run/secrets/django_migration').exists(); assert not Path('/run/secrets/postgres_admin_password').exists(); cursor=connection.cursor(); cursor.execute('SELECT current_user'); assert cursor.fetchone()[0]=='cv_runtime';\ntry:\n cursor.execute('CREATE TABLE runtime_must_not_create(id int)')\nexcept DatabaseError as error:\n assert error.__cause__.sqlstate=='42501'\nelse:\n raise AssertionError('Runtime DDL was allowed')")
    r.compose('run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'shell', '-c', "from blog.models import Category; before=Category.objects.order_by('-pk').first().pk; item=Category.objects.create(name='QA sequence check',slug='qa-sequence'); assert item.pk>before")
    for path in ('/blog/ai-and-its-impact-on-jobs/image/', '/news/ai-and-its-impact-on-jobs/image/'):
        r.compose('exec', '-T', 'nginx', 'wget', '--no-check-certificate', '-O', '/dev/null', 'https://' + config['domain'] + path, capture=True)
    r.maintenance()
    r.compose('run', '--rm', '--no-deps', 'web', 'python', '-c', "from pathlib import Path; Path('/app/private_uploads/qa-attachment.txt').write_bytes(b'synthetic private attachment')")
    r.compose('run', '--rm', '--no-deps', '-T', 'backup', r.BACKUP_COMMAND + ' >/dev/null', capture=True)
    r.backup()
    archive = next(Path(config['backup_directory']).glob('*.tar.age'))
    plaintext = Path(mount) / 'restore.tar'
    subprocess.run(['age', '-d', '-i', str(keys), '-o', str(plaintext), str(archive)], check=True, capture_output=True)
    restore = Path(mount) / 'restored'
    restore.mkdir()
    # This tar was produced here from fixed paths; never extracts user uploads as paths.
    subprocess.run(['tar', '-xf', str(plaintext), '-C', str(restore)], check=True)
    assert (restore / 'tmp/database.dump').stat().st_size > 0
    assert (restore / 'files/private_publishing').is_dir()
    assert (restore / 'files/private_uploads/qa-attachment.txt').read_bytes() == b'synthetic private attachment'
    bundle = json.loads((ROOT / 'deploy/release/public-content.json').read_text())
    for image in bundle['images']:
        folder = 'public_media' if image['model'] == 'projects.project' else 'private_publishing'
        assert hashlib.sha256((restore / 'files' / folder / image['name']).read_bytes()).hexdigest() == image['sha256']
    # Restore only into a freshly-created QA database in this same disposable stack.
    r.compose('exec', '-T', 'db', 'createdb', '-U', 'cv_init', 'qa_restore')
    dump_bytes = (restore / 'tmp/database.dump').read_bytes()
    result = subprocess.run(['docker', 'compose', '--project-name', project, '-f', str(compose_path), 'exec', '-T', 'db', 'pg_restore', '-U', 'cv_init', '-d', 'qa_restore', '--exit-on-error'], input=dump_bytes, capture_output=True)
    if result.returncode:
        raise RuntimeError('Restoring the encrypted QA database archive failed.')
    counts = r.compose('exec', '-T', 'db', 'psql', '-X', '-U', 'cv_init', '-d', 'qa_restore', '-Atc', 'SELECT (SELECT count(*) FROM blog_blogpost), (SELECT count(*) FROM news_newsitem);', capture=True).strip()
    assert counts == '1|1', 'Published content was not recovered.'
    # Invalid encryption recipient exercises real failure after web is stopped.
    # The prior valid archive must remain and the partial archive must disappear.
    time.sleep(1)
    config['backup_recipient'] = 'age1' + 'a' * 58
    (r.STATE / 'config.json').write_text(json.dumps(config))
    try:
        r.backup()
    except RuntimeError:
        pass
    else:
        raise AssertionError('Broken encryption unexpectedly succeeded.')
    assert len(list(Path(config['backup_directory']).glob('*.tar.age'))) == 1
    config['backup_recipient'] = recipient
    (r.STATE / 'config.json').write_text(json.dumps(config))
    time.sleep(5)
    assert 'TechBullion Hub' in request()
    # Exercise enabled indexing/HSTS with the same application and production checks.
    data['services']['web']['environment'].update(PRODUCTION_LAUNCH_VERIFIED='True', SEO_INDEXING_ENABLED='True', HSTS_SECONDS='300')
    compose_path.write_text(json.dumps(data))
    r.compose('up', '-d', '--no-deps', 'web')
    time.sleep(5)
    assert 'noindex' not in request()
    assert 'https://' + config['domain'] in request('/sitemap.xml')
    print('PASS: fresh install, restricted runtime role, sequence recovery, Redis, Unix socket TLS proxy, public content/images, cleanup, encrypted backup/database/file recovery, failed-backup restart, indexed launch.')
finally:
    if created:
        if 'compose_path' in globals() and compose_path.exists():
            r.compose('down', '--volumes', '--remove-orphans')
        labels = json.loads(docker('volume', 'inspect', volume, capture=True))[0]['Labels']
        if labels.get('techbullionhub.qa') != token:
            raise RuntimeError('Refusing to delete an unowned QA volume.')
        # Outer runner deletes this volume after the controller unmounts it.
