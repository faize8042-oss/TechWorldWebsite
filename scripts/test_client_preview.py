
"""Offline tests; no Docker, dotenv or external services."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.preview_settings'
import django
django.setup()
from django.conf import settings
from django.test import SimpleTestCase, Client
from django.core import mail
from config.preview import HOST

class BoundaryTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST='localhost')
    def test_public_pages_without_database(self):
        for path in ('/', '/services/', '/about/', '/projects/', '/contact/', '/privacy/', '/terms/', '/robots.txt'):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertIn('noindex', r['X-Robots-Tag'])
        self.assertContains(self.client.get('/projects/'), 'Synthetic examples')
    def test_sensitive_paths(self):
        for path in ('/admin/', '/admin/login/', '/accounts/', '/api/', '/media/x', '/private/', '/debug/', '/metrics', '/health/', '/pgadmin/', '/.env', '/config/settings.py', '/static/../config/settings.py', '/static/css/.env', '/static/css/x.css/extra'):
            self.assertEqual(self.client.get(path).status_code, 404, path)
    def test_host_validation_and_forwarded_spoof(self):
        for host in ('evil.invalid', 'trycloudflare.com', 'a.b.trycloudflare.com', '-a.trycloudflare.com', 'a.trycloudflare.com.evil', 'a.trycloudflare.com:443', 'a'*64+'.trycloudflare.com', 'LOCALHOST'):
            self.assertEqual(self.client.get('/', HTTP_HOST=host).status_code, 400, host)
        for host in ('localhost', '127.0.0.1:8765', 'abc-xyz.trycloudflare.com'):
            r = self.client.get('/', HTTP_HOST=host, HTTP_X_FORWARDED_HOST='evil.invalid', HTTP_X_FORWARDED_PROTO='https')
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.wsgi_request.is_secure())
    def test_no_writes_or_email(self):
        with patch('django.core.mail.send_mail', side_effect=AssertionError('email invoked')):
            for method in ('post', 'put', 'patch', 'delete', 'options'):
                self.assertEqual(getattr(self.client, method)('/contact/').status_code, 405)
        self.assertNotContains(self.client.get('/contact/'), '<form')
        self.assertEqual(settings.EMAIL_BACKEND, 'django.core.mail.backends.dummy.EmailBackend')
        self.assertEqual(settings.DATABASES['default']['ENGINE'], 'django.db.backends.dummy')
        self.assertFalse(settings.DEBUG)
    def test_collected_static_assets(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp, self.settings(STATIC_ROOT=tmp):
            call_command('collectstatic', interactive=False, verbosity=0)
            client = Client(HTTP_HOST='localhost')
            for path in ('/static/css/style.css', '/static/js/main.js'):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(b''.join(response.streaming_content))

    def test_generic_error(self):
        from django.urls import path
        def broken(request): raise RuntimeError('SECRET_SENTINEL')
        from config.preview_urls import urlpatterns
        with self.settings(ROOT_URLCONF=type('URLs', (), {'urlpatterns': [path('', broken, name='home')] + urlpatterns[1:]})):
            r = Client(HTTP_HOST='localhost', raise_request_exception=False).get('/')
            self.assertEqual(r.status_code, 500)
            self.assertNotIn(b'SECRET_SENTINEL', r.content)
            self.assertNotIn(b'Traceback', r.content)

class ConfigurationTests(unittest.TestCase):
    def test_isolation(self):
        c = json.loads((ROOT/'deploy/client-preview/compose.yaml').read_text())
        self.assertEqual(c['name'], 'codeventra-client-preview')
        self.assertEqual(set(c['services']), {'web','ingress'})
        self.assertEqual(c['services']['ingress']['ports'], ['127.0.0.1:8765:8080'])
        self.assertEqual(c['services']['web']['network_mode'], 'none')
        self.assertNotIn('ports', c['services']['web'])
        self.assertTrue(c['networks']['ingress']['internal'])
        self.assertEqual(set(c['volumes']), {'socket'})
        for service in c['services'].values():
            self.assertTrue(service['read_only'])
            self.assertEqual(service['pull_policy'], 'never')
            self.assertNotIn('env_file', service)
            self.assertNotIn('build', service)
            self.assertEqual(service['user'], '10001:10002')
        text = json.dumps(c)
        for forbidden in ('postgres','redis','private_uploads','external','DATABASE_URL','SMTP','SECRET_KEY'):
            self.assertNotIn(forbidden,text)
    def test_healthcheck_wire_format(self):
        import ast
        c = json.loads((ROOT/'deploy/client-preview/compose.yaml').read_text())
        code = c['services']['web']['healthcheck']['test'][-1]
        values = [n.value for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Constant) and isinstance(n.value, bytes)]
        self.assertIn(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n', values)

    def test_ingress_matches_application_boundary(self):
        n = (ROOT/'deploy/client-preview/nginx.conf').read_text()
        self.assertIn('location / { return 404; }', n)
        self.assertIn('return 405', n)
        self.assertIn('trycloudflare', n)
        proxy = (ROOT/'deploy/client-preview/proxy.conf').read_text()
        for header in ('X-Forwarded-Host', 'X-Forwarded-Proto','X-Forwarded-For','Forwarded'):
            self.assertIn('proxy_set_header '+header+' "";',proxy)
    def test_scripts_fail_closed(self):
        start=(ROOT/'scripts/client-preview/start-preview.ps1').read_text()
        self.assertLess(start.index("Confirm-Exact 'START"), start.index("@('create'"))
        self.assertIn("'--no-build','--pull','never'",start)
        self.assertIn("'--env-file',$emptyEnv",start)
        self.assertNotIn('cloudflared tunnel',start)
        stop=(ROOT/'scripts/client-preview/stop-preview.ps1').read_text()
        self.assertLess(stop.index('Assert-Recorded'),stop.index("'container','stop'"))
        self.assertIn("Confirm-Exact 'DELETE",stop)
        self.assertNotIn('prune',stop)
        common=(ROOT/'scripts/client-preview/common.ps1').read_text()
        self.assertNotIn('function Docker(', common)
        self.assertIn('function Invoke-PreviewDocker(', common)
        for marker in ('com.docker.compose.project','com.codeventra.preview','CreatedAt','identity changed','Service identity mismatch'):
            self.assertIn(marker,common)
    def test_curated_build_context(self):
        spec=importlib.util.spec_from_file_location('prepare',ROOT/'scripts/client-preview/prepare-context.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'context';module.prepare(out)
            self.assertFalse((out/'config/settings.py').exists())
            self.assertFalse((out/'.env').exists())
            self.assertFalse((out/'private_uploads').exists())
            self.assertFalse((out/'media').exists())
            self.assertTrue((out/'config/preview_settings.py').exists())
            self.assertTrue((out/'static/css/style.css').exists())
            with self.assertRaises(FileExistsError): module.prepare(out)

if __name__ == '__main__': unittest.main(verbosity=2)
