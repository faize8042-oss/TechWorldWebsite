#!/usr/bin/env python3
"""Linux single-host release operator. Secrets never enter command arguments.

Run from an immutable checkout on Ubuntu 24.04 amd64, as root. No service is
changed merely by importing this module or asking for --help.
"""
import argparse
import fcntl
import getpass
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import secrets
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('/etc/techbullionhub')
PROJECT = 'techbullionhub'
BACKUP_COMMAND = 'pg_dump -h db -U cv_backup -d codeventra -Fc -f /tmp/database.dump; tar -C / -cf - tmp/database.dump files/private_uploads files/private_publishing files/public_media'
HEALTH_USER_AGENT = 'TechBullionHub-Health/1.0'


def run(args, *, capture=False, data=None, env=None):
    result = subprocess.run([str(a) for a in args], input=data, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE, env=env, check=False)
    if result.returncode:
        # Database/SMTP tools can include secrets in exceptions. Never echo stderr.
        raise RuntimeError('Command failed: ' + str(args[0]) + ' (details withheld; inspect host logs privately)')
    return result.stdout if capture else None


def validate(config):
    expected = {'domain', 'contact_email', 'certificate_email', 'smtp_host',
                'smtp_port', 'smtp_user', 'from_email', 'smtp_ssl',
                'backup_recipient', 'backup_directory'}
    if not isinstance(config, dict) or set(config) != expected:
        raise ValueError('Configuration keys must match config.example.json.')
    host = r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}'
    for key in ('domain', 'smtp_host'):
        if not isinstance(config[key], str) or not re.fullmatch(host, config[key]):
            raise ValueError(key + ' must be a plain lowercase hostname.')
    if config['domain'].startswith('www.') or config['domain'].endswith(('.example', '.invalid')):
        raise ValueError('Use your purchased apex domain.')
    for key in ('contact_email', 'certificate_email', 'from_email'):
        if not isinstance(config[key], str) or not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', config[key]):
            raise ValueError(key + ' must be a single email address.')
    if type(config['smtp_port']) is not int or not 1 <= config['smtp_port'] <= 65535:
        raise ValueError('smtp_port must be between 1 and 65535.')
    if type(config['smtp_ssl']) is not bool or not isinstance(config['smtp_user'], str) or not config['smtp_user'] or any(c in config['smtp_user'] for c in '\r\n\x00'):
        raise ValueError('Set smtp_ssl and a valid SMTP username.')
    if not re.fullmatch(r'age1[0-9a-z]{58}', config['backup_recipient']):
        raise ValueError('Set an age public encryption recipient, keeping the private key off this server.')
    if not isinstance(config['backup_directory'], str):
        raise ValueError('backup_directory must be a path string.')
    backup = Path(config['backup_directory'])
    if not backup.is_absolute() or '..' in backup.parts or str(backup) in ('/', '/etc', '/var', '/var/backups'):
        raise ValueError('Choose a dedicated absolute backup directory.')
    if any('replace-' in str(v) or 'your-provider' in str(v) for v in config.values()):
        raise ValueError('Replace every configuration placeholder.')
    return config


def write(path, value, uid=0, gid=0, mode=0o600):
    """New files only; never silently rotate production credentials."""
    with path.open('x', encoding='utf-8') as stream:
        stream.write(value)
    os.chmod(path, mode)
    os.chown(path, uid, gid)


def configure(config_path):
    config = validate(json.loads(Path(config_path).read_text()))
    if STATE.exists():
        raise ValueError('State already exists. Preserve it; configuration never overwrites secrets.')
    password = getpass.getpass('SMTP password (hidden): ')
    if not password or any(c in password for c in '\r\n\x00'):
        raise ValueError('SMTP password is required.')
    STATE.mkdir(mode=0o700)
    secret_dir = STATE / 'secrets'
    secret_dir.mkdir(mode=0o700)
    generated = {key: secrets.token_urlsafe(48) for key in ('admin', 'runtime', 'migration', 'backup', 'redis')}
    domain = config['domain']
    runtime = {
        'DATABASE_URL': f"postgres://cv_runtime:{generated['runtime']}@db:5432/codeventra",
        'SECRET_KEY': secrets.token_urlsafe(64), 'ANALYTICS_HMAC_SECRET': secrets.token_urlsafe(64),
        'ALLOWED_HOSTS': domain + ',www.' + domain,
        'CSRF_TRUSTED_ORIGINS': f'https://{domain},https://www.{domain}',
        'SEO_SITE_URL': 'https://' + domain,
        'REDIS_URL': f"redis://:{generated['redis']}@redis:6379/0",
        'CONTACT_EMAIL': config['contact_email'], 'DEFAULT_FROM_EMAIL': config['from_email'],
        'EMAIL_HOST': config['smtp_host'], 'EMAIL_PORT': str(config['smtp_port']),
        'EMAIL_HOST_USER': config['smtp_user'], 'EMAIL_HOST_PASSWORD': password,
        'EMAIL_USE_SSL': str(config['smtp_ssl']), 'EMAIL_USE_TLS': str(not config['smtp_ssl'])}
    write(secret_dir / 'runtime.json', json.dumps(runtime), 10001, 10002, 0o400)
    write(secret_dir / 'migration.json', json.dumps({'DATABASE_URL': f"postgres://cv_migrate:{generated['migration']}@db:5432/codeventra"}), 10001, 10002, 0o400)
    write(secret_dir / 'admin', generated['admin'])
    write(secret_dir / 'roles.json', json.dumps({'cv_runtime': generated['runtime'], 'cv_migrate': generated['migration'], 'cv_backup': generated['backup']}))
    # File-backed Compose secrets retain host ownership. Redis's entrypoint
    # drops to uid 999; its authentication files must be readable by that uid.
    write(secret_dir / 'redis-password', generated['redis'], 999, 999, 0o400)
    write(secret_dir / 'redis.conf', 'bind 0.0.0.0\nprotected-mode yes\nsave ""\nappendonly no\nmaxmemory 192mb\nmaxmemory-policy allkeys-lru\nrequirepass ' + generated['redis'] + '\n', 999, 999, 0o400)
    write(secret_dir / 'pgpass', f"db:5432:codeventra:cv_backup:{generated['backup']}\n", mode=0o600)
    write(STATE / 'config.json', json.dumps(config, indent=2))
    (STATE / 'acme').mkdir(mode=0o755)
    print('Configuration saved. Credentials generated; no services started.')


def compose(*args, capture=False, data=None):
    return run(['docker', 'compose', '--project-name', PROJECT, '-f', STATE / 'compose.json', *args], capture=capture, data=data)


def image_id(tag):
    value = run(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], capture=True).strip()
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', value):
        raise ValueError('Image identity could not be verified.')
    return value


def nginx_config(domain, tls):
    acme = 'location ^~ /.well-known/acme-challenge/ { root /var/www/acme; }'
    base = 'server { listen 80 default_server; server_name _; return 444; }\n'
    base += f'server {{ listen 80; server_name {domain} www.{domain}; {acme} location / {{ return 301 https://{domain}$request_uri; }} }}\n'
    if not tls:
        return base
    source = (ROOT / 'deploy/nginx/production.conf.example').read_text()
    source = source[source.index('# Reject unrecognized TLS'):].replace('techbullionhub.net', domain)
    # Redirect www only after its TLS certificate has been validated.
    source = source.replace('server_name ' + domain + ' www.' + domain + ';', 'server_name ' + domain + ';')
    source += f'\nserver {{ listen 443 ssl; server_name www.{domain}; ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem; ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem; ssl_protocols TLSv1.2 TLSv1.3; return 301 https://{domain}$request_uri; }}\n'
    return 'upstream django_app { server unix:/run/codeventra/gunicorn.sock; keepalive 16; }\n' + base + source


def build():
    load()
    if (STATE / 'installed').exists():
        raise ValueError('This command prepares a first release only. Use a new checkout and the upgrade runbook for later releases.')
    run(['docker', 'build', '--pull', '-f', ROOT / 'deploy/release/Dockerfile', '-t', 'techbullionhub:release', ROOT])
    run(['docker', 'build', '--pull', '-f', ROOT / 'deploy/release/nginx.Dockerfile', '-t', 'techbullionhub-nginx:release', ROOT / 'deploy/release'])
    paths = {'APP_IMAGE': image_id('techbullionhub:release'), 'NGINX_IMAGE': image_id('techbullionhub-nginx:release')}
    names = {'POSTGRES_ADMIN_PASSWORD_FILE': 'admin', 'DJANGO_RUNTIME_SECRET_FILE': 'runtime.json', 'DJANGO_MIGRATION_SECRET_FILE': 'migration.json', 'REDIS_PASSWORD_FILE': 'redis-password', 'REDIS_CONFIG_FILE': 'redis.conf'}
    paths.update({k: str(STATE / 'secrets' / v) for k, v in names.items()})
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'DOCKER_HOST', 'DOCKER_CONTEXT')}
    env.update(paths)
    spec = json.loads(run(['docker', 'compose', '--project-name', PROJECT, '--profile', 'operator', '--env-file', '/dev/null', '-f', ROOT / 'deploy/compose.production.yaml', 'config', '--format', 'json'], env=env, capture=True))
    services = spec['services']
    services['migrate']['volumes'] = [{'type': 'volume', 'source': name, 'target': path} for name, path in (('private_publishing', '/app/private_publishing'), ('public_media', '/app/media'))]
    pins = json.loads((ROOT / 'deploy/release/images.json').read_text())
    for name in ('db', 'redis'):
        tag = pins['postgres' if name == 'db' else 'redis']
        run(['docker', 'pull', tag])
        services[name]['image'] = image_id(tag)
    nginx = services['nginx']
    for volume in nginx['volumes']:
        if volume['target'] == '/etc/nginx/conf.d/default.conf':
            volume['source'] = str(STATE / 'nginx.conf')
    nginx['volumes'].append({'type': 'bind', 'source': str(STATE / 'acme'), 'target': '/var/www/acme', 'read_only': True})
    # Backup identity never reaches web or the migration service.
    spec['secrets']['backup_pgpass'] = {'file': str(STATE / 'secrets/pgpass')}
    services['backup'] = {'image': services['db']['image'], 'profiles': ['operator'],
        'user': '0:0', 'entrypoint': ['/bin/sh', '-ec'], 'command': ['exit 1'],
        'environment': {'PGPASSFILE': '/run/secrets/backup_pgpass'}, 'secrets': ['backup_pgpass'],
        'networks': ['data'], 'read_only': True, 'cap_drop': ['ALL'], 'cap_add': ['DAC_OVERRIDE'],
        'tmpfs': ['/tmp:rw,nosuid,noexec,size=512m'],
        'volumes': [{'type': 'volume', 'source': n, 'target': '/files/' + n, 'read_only': True} for n in ('private_uploads', 'private_publishing', 'public_media')]}
    (STATE / 'compose.json').write_text(json.dumps(spec, indent=2))
    os.chmod(STATE / 'compose.json', 0o600)
    (STATE / 'nginx.conf').write_text(nginx_config(load()['domain'], False))
    print('Release images built and frozen by local content ID.')


def load():
    return validate(json.loads((STATE / 'config.json').read_text()))


def sql_file(name):
    compose('exec', '-T', 'db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'cv_init', '-d', 'codeventra', data=(ROOT / 'deploy/postgres' / name).read_text(), capture=True)


def install():
    if (STATE / 'installed').exists():
        raise ValueError('Already installed. This command never reinitializes a database.')
    compose('up', '-d', '--wait', 'db', 'redis')
    # A successful fresh script is recorded before subsequent steps. Failures
    # can be retried without rerunning destructive or duplicate role creation.
    if not (STATE / 'roles-created').exists():
        sql_file('fresh.sql')
        (STATE / 'roles-created').touch()
    roles = json.loads((STATE / 'secrets/roles.json').read_text())
    # psql's password prompt creates SCRAM verifiers without password SQL or argv.
    for role, password in roles.items():
        if role not in ('cv_runtime', 'cv_migrate', 'cv_backup'):
            raise ValueError('Unexpected database role.')
        compose('exec', '-T', 'db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'cv_init', '-d', 'codeventra', '-c', '\\password ' + role, data=password + '\n' + password + '\n', capture=True)
    sql_file('grants.sql')
    compose('run', '--rm', '--no-deps', 'migrate', 'python', 'manage.py', 'migrate', '--settings=config.migration_settings', '--noinput', '--skip-checks')
    sql_file('grants.sql')
    compose('run', '--rm', '--no-deps', 'publishing-storage-init')
    if not (STATE / 'content-imported').exists():
        compose('run', '--rm', '--no-deps', 'migrate', 'python', 'manage.py', 'release_content', 'import', '--file', 'deploy/release/public-content.json', '--settings=config.migration_settings', '--skip-checks')
        (STATE / 'content-imported').touch()
    compose('up', '-d', '--no-deps', 'web')
    compose('run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'check', '--deploy', '--fail-level', 'ERROR')
    (STATE / 'installed').touch()
    print('Application installed with search indexing disabled. Next: certificate.')


def certificate():
    if not (STATE / 'installed').exists():
        raise ValueError('Install the application before requesting a certificate.')
    config = load()
    compose('up', '-d', '--no-deps', 'nginx')
    run(['certbot', 'certonly', '--non-interactive', '--agree-tos', '--webroot', '-w', STATE / 'acme', '--email', config['certificate_email'], '--cert-name', config['domain'], '-d', config['domain'], '-d', 'www.' + config['domain']])
    (STATE / 'nginx.conf').write_text(nginx_config(config['domain'], True))
    compose('exec', '-T', 'nginx', 'nginx', '-t')
    compose('exec', '-T', 'nginx', 'nginx', '-s', 'reload')
    verify_https()


def verify_https(indexed=False):
    domain = load()['domain']
    context = ssl.create_default_context()
    for path in ('/', '/services/', '/projects/', '/contact/', '/blog/', '/news/', '/robots.txt', '/sitemap.xml'):
        request = urllib.request.Request('https://' + domain + path, headers={'User-Agent': HEALTH_USER_AGENT})
        with urllib.request.urlopen(request, context=context, timeout=20) as response:
            if response.status != 200 or response.url != 'https://' + domain + path:
                raise ValueError('Public HTTPS check failed.')
            content = response.read().decode('utf-8')
            if path == '/':
                class Robots(HTMLParser):
                    value = None
                    def handle_starttag(self, tag, attrs):
                        attrs = dict(attrs)
                        if tag == 'meta' and attrs.get('name') == 'robots':
                            self.value = attrs.get('content', '')
                robots = Robots()
                robots.feed(content)
                if robots.value is None or (('noindex' not in robots.value.lower()) != indexed):
                    raise ValueError('Indexing metadata does not match release state.')
    request = urllib.request.Request('https://www.' + domain + '/', headers={'User-Agent': HEALTH_USER_AGENT})
    with urllib.request.urlopen(request, context=context, timeout=20) as response:
        if response.url != 'https://' + domain + '/':
            raise ValueError('The www canonical redirect failed.')
    print('Public HTTPS, canonical redirect, pages and sitemap passed.')


def launch():
    if (STATE / 'launched').exists():
        verify_https(indexed=True)
        return
    if any(not (STATE / name).exists() for name in ('installed', 'first-backup', 'smtp-verified')):
        raise ValueError('Install, verify SMTP authentication, and create the first encrypted backup before launch.')
    verify_https()
    spec = json.loads((STATE / 'compose.json').read_text())
    previous = json.dumps(spec, indent=2)
    env = spec['services']['web']['environment']
    env.update({'PRODUCTION_LAUNCH_VERIFIED': 'True', 'SEO_INDEXING_ENABLED': 'True', 'HSTS_SECONDS': '300'})
    try:
        (STATE / 'compose.json').write_text(json.dumps(spec, indent=2))
        compose('up', '-d', '--no-deps', 'web')
        time.sleep(4)
        verify_https(indexed=True)
    except Exception:
        (STATE / 'compose.json').write_text(previous)
        compose('up', '-d', '--no-deps', 'web')
        raise
    (STATE / 'launched').touch()
    print('Search indexing enabled after verified HTTPS. HSTS starts at five minutes.')


def smtp_check():
    (STATE / 'smtp-verified').unlink(missing_ok=True)
    config = load()
    values = json.loads((STATE / 'secrets/runtime.json').read_text())
    context = ssl.create_default_context()
    try:
        if config['smtp_ssl']:
            client = smtplib.SMTP_SSL(config['smtp_host'], config['smtp_port'], timeout=20, context=context)
        else:
            client = smtplib.SMTP(config['smtp_host'], config['smtp_port'], timeout=20)
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        with client:
            client.login(config['smtp_user'], values['EMAIL_HOST_PASSWORD'])
    except (OSError, smtplib.SMTPException):
        raise RuntimeError('SMTP authentication failed. Check the provider configuration privately.') from None
    (STATE / 'smtp-verified').touch()
    print('SMTP TLS and authentication passed. No message was sent.')


def backup():
    config = load()
    destination = Path(config['backup_directory'])
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = destination / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '.tar.age')
    if target.exists():
        raise ValueError('Backup filename already exists.')
    dump = encrypt = None
    try:
        compose('stop', '-t', '60', 'web')
        with target.open('xb') as output:
            os.chmod(target, 0o600)
            dump = subprocess.Popen(['docker', 'compose', '--project-name', PROJECT, '-f', str(STATE / 'compose.json'), 'run', '--rm', '--no-deps', '-T', 'backup', BACKUP_COMMAND], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            encrypt = subprocess.Popen(['age', '-r', config['backup_recipient']], stdin=dump.stdout, stdout=output, stderr=subprocess.DEVNULL)
            dump.stdout.close()
            encrypted_ok = encrypt.wait() == 0
            dumped_ok = dump.wait() == 0
            if not encrypted_ok or not dumped_ok:
                raise RuntimeError('Backup failed; partial archive discarded.')
        if target.stat().st_size < 128:
            raise RuntimeError('Backup archive unexpectedly small.')
        (STATE / 'first-backup').touch()
        print('Encrypted database and all uploaded files saved. Copy this archive off the server.')
    except Exception:
        if encrypt and encrypt.poll() is None:
            encrypt.terminate()
        if dump and dump.poll() is None:
            dump.terminate()
        target.unlink(missing_ok=True)
        raise
    finally:
        compose('up', '-d', '--no-deps', 'web')


def maintenance():
    compose('run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'cleanup_unanswered_enquiries', '--apply')
    compose('run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'cleanup_analytics')


def timers():
    # Copy the checkout to a stable path first; systemd invokes this exact release.
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(ROOT)):
        raise ValueError('Release path must not contain spaces or systemd substitutions.')
    for name, action, calendar in (('maintenance', 'maintenance', '*-*-* 02:00:00'), ('backup', 'backup', '*-*-* 03:00:00'), ('certificate', 'renew', '*-*-* 00,12:00:00'), ('health', 'check', '*-*-* *:0/5:00')):
        unit = 'techbullionhub-' + name
        Path('/etc/systemd/system/' + unit + '.service').write_text(f'[Unit]\nDescription=TechBullion Hub {name}\nAfter=docker.service\nRequires=docker.service\n[Service]\nType=oneshot\nUMask=0077\nExecStart=/usr/bin/python3 {ROOT}/deploy/release/release.py {action}\n')
        Path('/etc/systemd/system/' + unit + '.timer').write_text(f'[Unit]\nDescription=TechBullion Hub {name} schedule\n[Timer]\nOnCalendar={calendar}\nPersistent=true\nRandomizedDelaySec=300\n[Install]\nWantedBy=timers.target\n')
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', *['techbullionhub-' + n + '.timer' for n in ('maintenance', 'backup', 'certificate', 'health')]])
    print('Daily backup/cleanup, twice-daily certificate renewal and five-minute health checks scheduled.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('configure', 'build', 'install', 'certificate', 'check', 'launch', 'backup', 'maintenance', 'timers', 'renew', 'admin', 'smtp-check'))
    parser.add_argument('--config', default=str(ROOT / 'deploy/release/config.example.json'))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root on the Linux hosting server.')
    # One operator at a time, including timers and interactive runs.
    with open('/run/lock/techbullionhub-release.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'configure':
            configure(args.config)
        elif args.action == 'check':
            verify_https(indexed=(STATE / 'launched').exists())
        elif args.action == 'admin':
            compose('run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'createsuperuser')
        elif args.action == 'smtp-check':
            smtp_check()
        elif args.action == 'renew':
            run(['certbot', 'renew', '--quiet'])
            compose('exec', '-T', 'nginx', 'nginx', '-t')
            compose('exec', '-T', 'nginx', 'nginx', '-s', 'reload')
        else:
            globals()[args.action]()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print('Release stopped: ' + str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Release stopped: host operation failed.', file=sys.stderr)
        sys.exit(1)
