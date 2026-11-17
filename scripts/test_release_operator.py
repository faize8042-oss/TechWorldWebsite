"""Operator input/secret tests. Run as root inside a disposable Linux container."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT / 'deploy/release/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'deploy/release/config.example.json').read_text())
        self.config.update(smtp_host='smtp.mail.test', smtp_user='user', backup_recipient='age1' + 'a' * 58)

    def test_valid_public_config(self):
        release.validate(self.config)

    def test_injection_and_invalid_hostnames_rejected(self):
        for host in ('good.test;touch /tmp/proof', 'good.test\nserver {}', '*.test', '-bad.test', 'www.good.test', 'https://good.test', 'bad..test'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                release.validate({**self.config, 'domain': host})

    def test_port_boolean_and_unknown_secret_keys_rejected(self):
        for override in ({'smtp_port': True}, {'smtp_port': 0}, {'smtp_port': 65536}, {'smtp_ssl': 'false'}, {'smtp_password': 'do-not-store-in-public-config'}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                release.validate({**self.config, **override})

    def test_configure_owns_secrets_for_actual_container_users(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            config = base / 'input.json'
            config.write_text(json.dumps(self.config))
            with patch.object(release, 'STATE', base / 'state'), patch('getpass.getpass', return_value='synthetic-hidden-secret'), patch('builtins.print') as output:
                release.configure(config)
                runtime = base / 'state/secrets/runtime.json'
                self.assertEqual(runtime.stat().st_uid, 10001)
                self.assertEqual(runtime.stat().st_mode & 0o777, 0o400)
                self.assertEqual((base / 'state').stat().st_mode & 0o777, 0o700)
                self.assertEqual((base / 'state/secrets/redis.conf').stat().st_uid, 999)
                values = json.loads(runtime.read_text())
                self.assertIn('cv_runtime:', values['DATABASE_URL'])
                self.assertNotIn('cv_migrate', runtime.read_text())
                self.assertNotIn('synthetic-hidden-secret', str(output.call_args_list))
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    release.configure(config)

    def test_generated_proxy_has_private_socket_and_canonical_redirect(self):
        config = release.nginx_config('site.test', True)
        self.assertIn('unix:/run/codeventra/gunicorn.sock', config)
        self.assertIn('server_name www.site.test;', config)
        self.assertIn('return 301 https://site.test$request_uri', config)
        self.assertIn('ssl_reject_handshake on', config)
        self.assertIn('location ^~ /.well-known/acme-challenge/', config)
        self.assertNotIn('techbullionhub.net', config)
        self.assertNotIn('ssl_certificate', release.nginx_config('site.test', False))

    def test_failed_command_does_not_echo_secret_stderr(self):
        import subprocess
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'password=synthetic-hidden-secret')):
            with self.assertRaises(RuntimeError) as error:
                release.run(['smtp-tool', '--check'])
        self.assertNotIn('synthetic-hidden-secret', str(error.exception))

    def test_failed_launch_restores_previous_config_and_restarts_web(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for name in ('installed', 'first-backup', 'smtp-verified'):
                (state / name).touch()
            previous = {'services': {'web': {'environment': {'SEO_INDEXING_ENABLED': 'False'}}}}
            config = state / 'compose.json'
            config.write_text(json.dumps(previous))
            with patch.object(release, 'STATE', state), patch.object(release, 'verify_https', side_effect=[None, ValueError('Synthetic HTTPS failure')]), patch.object(release, 'compose') as compose, patch('time.sleep'):
                with self.assertRaisesRegex(ValueError, 'HTTPS failure'):
                    release.launch()
            self.assertEqual(json.loads(config.read_text()), previous)
            self.assertEqual(compose.call_count, 2)
            self.assertFalse((state / 'launched').exists())


if __name__ == '__main__':
    unittest.main()
