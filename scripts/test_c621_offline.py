"""Offline contracts only: no dotenv, sockets, database creation or subprocess services."""
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from config.production_database import (
    RUNTIME_KEYS, load_runtime_environment, runtime_database_errors, validate_database_url,
)

ROOT = Path(__file__).resolve().parents[1]


class CredentialContractTests(unittest.TestCase):
    def test_valid_url_and_rejected_urls(self):
        validate_database_url('postgres://cv_runtime:synthetic@db/codeventra')
        for value in (None, '', 'sqlite:///db',
                      'postgres://cv_init:synthetic@db/codeventra',
                      'postgres://cv_migrate:synthetic@db/codeventra',
                      'postgres://cv_runtime@db/codeventra',
                      'postgres://cv_runtime:synthetic@external/codeventra',
                      'postgres://cv_runtime:synthetic@db/codeventra?options=-c%20role=cv_owner',
                      'postgres://cv_runtime:synthetic@db:bad/codeventra'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_database_url(value)

    def load(self, values, extra=None):
        ambient = {'PRODUCTION_RUNTIME_FILE': '/run/secrets/django_runtime', **(extra or {})}
        with patch.object(Path, 'read_text', return_value=json.dumps(values)):
            load_runtime_environment(ambient)
        return ambient

    def test_only_runtime_values_loaded(self):
        values = {'DATABASE_URL': 'postgres://cv_runtime:synthetic@db/codeventra'}
        self.assertEqual(self.load(values)['DATABASE_URL'], values['DATABASE_URL'])
        self.assertFalse(any(k.startswith(('POSTGRES_', 'MIGRATION_', 'BACKUP_')) for k in RUNTIME_KEYS))

    def test_ambient_privileged_and_libpq_overrides_rejected(self):
        for key in ('POSTGRES_PASSWORD', 'POSTGRES_PASSWORD_FILE', 'PGOPTIONS', 'PGSERVICE',
                    'DATABASE_URL', 'MIGRATION_URL', 'BACKUP_PASSWORD', 'SECRET_KEY'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load({'DATABASE_URL': 'postgres://cv_runtime:synthetic@db/codeventra'}, {key: 'synthetic-marker'})

    def test_shared_file_and_malformed_inputs_rejected_without_values(self):
        for values in ({'POSTGRES_PASSWORD': 'sensitive-marker'}, {'DATABASE_URL': 123}, [],
                       {'DATABASE_URL': 'postgres://cv_init:sensitive-marker@db/codeventra'}):
            with self.assertRaises(ValueError) as raised:
                self.load(values)
            self.assertNotIn('sensitive-marker', str(raised.exception))
        with patch.object(Path, 'read_text', side_effect=OSError('sensitive-marker')):
            with self.assertRaisesRegex(ValueError, '^Invalid production runtime secret file.$'):
                load_runtime_environment({'PRODUCTION_RUNTIME_FILE': '/run/secrets/django_runtime'})
        with self.assertRaises(ValueError):
            load_runtime_environment({'PRODUCTION_RUNTIME_FILE': '/shared/file'})

    def test_actual_production_settings_and_migration_settings_offline(self):
        import os
        import subprocess
        import sys
        synthetic = {
            "DATABASE_URL": "postgres://cv_runtime:synthetic@db/codeventra",
            "SECRET_KEY": "synthetic-only-" + "aB3!" * 20,
            "ALLOWED_HOSTS": "site.example", "CSRF_TRUSTED_ORIGINS": "https://site.example",
            "REDIS_URL": "redis://:synthetic@redis:6379/0",
            "CONTACT_EMAIL": "test@example.invalid", "DEFAULT_FROM_EMAIL": "test@example.invalid",
            "EMAIL_HOST": "smtp.example", "EMAIL_HOST_USER": "synthetic",
            "EMAIL_HOST_PASSWORD": "synthetic",
        }
        code = """
import json
from pathlib import Path
from unittest.mock import patch
import environ
values = SYNTHETIC
runtime = json.dumps(values)
migration = json.dumps({'DATABASE_URL': 'postgres://cv_migrate:synthetic@db/codeventra'})
def read(path, *args, **kwargs):
    if path.as_posix() == '/run/secrets/django_runtime': return runtime
    if path.as_posix() == '/run/secrets/django_migration': return migration
    raise AssertionError('Unexpected file access')
with patch.object(Path, 'read_text', read), patch.object(environ.Env, 'read_env', side_effect=AssertionError('dotenv forbidden')):
    import os, runpy, traceback
    original_environment = dict(os.environ)
    for name, invalid in (("EMAIL_PORT", "synthetic-secret-marker"),
                          ("HSTS_SECONDS", "synthetic-secret-marker"),
                          ("ANALYTICS_RETENTION_DAYS", "synthetic-secret-marker"),
                          ("EMAIL_USE_TLS", "synthetic-secret-marker"),
                          ("EMAIL_USE_TLS", "false"),
                          ("EMAIL_USE_SSL", "true"),
                          ("REDIS_URL", "redis://:synthetic-secret-marker@outside:6379/0"),
                          ("REDIS_URL", None)):
        candidate = dict(values)
        if name in {"HSTS_SECONDS", "ANALYTICS_RETENTION_DAYS"}:
            os.environ[name] = invalid
        elif invalid is None:
            candidate.pop(name, None)
        else:
            candidate[name] = invalid
        runtime = json.dumps(candidate)
        try:
            runpy.run_module('config.settings')
        except ValueError as error:
            assert name in str(error)
            assert 'synthetic-secret-marker' not in ''.join(traceback.format_exception(error))
            assert error.__suppress_context__
        else:
            raise AssertionError('Invalid production settings accepted')
        os.environ.clear()
        os.environ.update(original_environment)
    runtime = json.dumps(values)
    import config.settings
    from config.checks import check_production_configuration
    assert check_production_configuration(None) == []
    import config.migration_settings as migration_settings
    assert migration_settings.DATABASES['default']['USER'] == 'cv_migrate'
    assert migration_settings.DATABASES['default']['OPTIONS']['assume_role'] == 'cv_owner'
    from django.test import override_settings
    with override_settings(DATABASES=migration_settings.DATABASES):
        assert check_production_configuration(None), 'Web must reject migration settings'
""".replace('SYNTHETIC', repr(synthetic))
        clean = {k: v for k, v in os.environ.items() if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
        clean.update(DEPLOYMENT_MODE='production', DEBUG='False', ENABLE_HTTPS='True',
                     PRODUCTION_PROXY_TRANSPORT='unix',
                     PRODUCTION_RUNTIME_FILE='/run/secrets/django_runtime',
                     DJANGO_SETTINGS_MODULE='config.settings')
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=clean,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_database_identity_and_options_contract(self):
        valid = dict(USER='cv_runtime', PASSWORD='synthetic', HOST='db', NAME='codeventra',
                     OPTIONS={'options': '-c search_path=public'})
        self.assertEqual(runtime_database_errors(valid, 'cv_init', 'runtime-secret-v1'), [])
        for change in ({'USER': 'cv_init'}, {'USER': 'cv_migrate'}, {'PASSWORD': ''},
                       {'OPTIONS': {'options': '-c role=cv_owner'}}, {'HOST': 'other'}):
            self.assertTrue(runtime_database_errors({**valid, **change}, 'cv_init', 'runtime-secret-v1'))
        self.assertTrue(runtime_database_errors(valid, '', ''))


class RepositoryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = (ROOT / 'deploy/compose.production.yaml').read_text()
        cls.services = dict(re.findall(r'^  (\w+):\n(.*?)(?=^  \w+:|^\w+:|\Z)',
                                      cls.compose.split('volumes:\n  gunicorn_socket:')[0], re.M | re.S))

    def test_no_shared_env_or_secret_interpolation(self):
        self.assertNotIn('env_file:', self.compose)
        self.assertNotRegex(self.compose, r'\$\{(?:DATABASE_URL|POSTGRES_PASSWORD|REDIS_PASSWORD)[:}]')
        web = self.services['web']
        self.assertIn('- django_runtime', web)
        for value in ('postgres_admin_password', 'cv_init', 'cv_migrate', 'django_migration', 'POSTGRES_', 'DATABASE_URL:'):
            self.assertNotIn(value, web)
        self.assertIn('POSTGRES_PASSWORD_FILE: /run/secrets/postgres_admin_password', self.services['db'])
        self.assertNotIn('postgres_admin_password', self.services['redis'])
        self.assertNotIn('--requirepass', self.services['redis'])

    def test_private_database_and_socket_invariants(self):
        for service in ('db', 'redis', 'web'):
            block = self.services[service]
            self.assertNotRegex(block, r'(?m)^    (ports|expose|network_mode):', service)
            self.assertIn('    networks:\n      - data', block)
            self.assertNotIn('      - proxy', block)
        self.assertIn('  data:\n    internal: true', self.compose)
        self.assertIn('gunicorn_socket:/run/codeventra:ro', self.services['nginx'])
        self.assertIn('gunicorn_socket:/run/codeventra', self.services['web'])
        for service in ('db', 'redis'):
            self.assertNotIn('gunicorn_socket', self.services[service])
        for text in ('user: "10001:10002"', 'cap_drop: [ALL]', 'read_only: true', 'PRODUCTION_PROXY_TRANSPORT: unix'):
            self.assertIn(text, self.services['web'])

    def test_fresh_sql_and_repeatable_grants(self):
        fresh = (ROOT / 'deploy/postgres/fresh.sql').read_text()
        grants = (ROOT / 'deploy/postgres/grants.sql').read_text()
        for role in ('cv_runtime', 'cv_migrate', 'cv_backup'):
            self.assertRegex(fresh, rf'CREATE ROLE {role} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL')
        self.assertIn('CREATE ROLE cv_owner NOLOGIN', fresh)
        self.assertIn('WITH INHERIT FALSE, SET TRUE, ADMIN FALSE', fresh)
        self.assertNotIn('GRANT cv_owner TO cv_runtime', fresh)
        self.assertIn('Fresh provisioning requires an empty database', fresh)
        for statement in ('REVOKE ALL ON DATABASE codeventra FROM PUBLIC;',
                          'GRANT CONNECT ON DATABASE codeventra TO cv_runtime, cv_migrate, cv_backup;',
                          'GRANT USAGE ON SCHEMA public TO cv_runtime, cv_backup;',
                          'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cv_runtime;',
                          'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cv_runtime;',
                          'GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO cv_backup;'):
            self.assertIn(statement, grants)
        for kind in ('TABLES', 'SEQUENCES'):
            self.assertIn(f'ALTER DEFAULT PRIVILEGES FOR ROLE cv_owner IN SCHEMA public GRANT SELECT ON {kind} TO cv_backup;', grants)
        self.assertIn('IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cv_runtime', grants)
        self.assertIn('IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO cv_runtime', grants)
        self.assertIn('FOR ROLE cv_owner REVOKE EXECUTE ON ROUTINES FROM PUBLIC', grants)
        for kind in ('TABLES', 'SEQUENCES', 'ROUTINES', 'TYPES'):
            self.assertIn(f'FOR ROLE cv_owner REVOKE ALL ON {kind} FROM cv_runtime, cv_migrate, cv_backup;', grants)
            self.assertIn(f'IN SCHEMA public REVOKE ALL ON {kind} FROM PUBLIC, cv_runtime, cv_migrate, cv_backup;', grants)
        self.assertIn("format('REVOKE ALL ON TYPE %I.%I", grants)
        self.assertIn('Role flags or memberships violate the approved contract', grants)
        self.assertNotRegex(grants, r'(?im)^.*(?:DROP |REASSIGN OWNED|ALTER .* OWNER TO)')
        self.assertNotRegex(fresh + grants, r'\$\{|:\"|:\x27')
        migration = (ROOT / 'config/migration_settings.py').read_text()
        self.assertIn('"assume_role": "cv_owner"', migration)
        self.assertIn('login="cv_migrate"', migration)

    def test_development_dotenv_gate_and_compose_unchanged_contract(self):
        source = (ROOT / 'config/settings.py').read_text()
        self.assertIn('elif not os.environ.get("CODEVENTRA_SKIP_DOTENV"):', source)
        self.assertLess(source.index('load_runtime_environment(os.environ)'), source.index('environ.Env.read_env'))
        development = (ROOT / 'compose.yaml').read_text()
        self.assertIn('127.0.0.1:5433:5432', development)
        self.assertIn('DEBUG: "True"', development)


class RemediationTests(unittest.TestCase):
    def valid(self):
        return {"REDIS_URL": "redis://:synthetic@redis:6379/0"}

    def assert_safe_failure(self, values, setting):
        import traceback
        from config.production_database import validate_production_settings
        try:
            validate_production_settings(values)
        except ValueError as error:
            rendered = "".join(traceback.format_exception(error))
            self.assertIn(setting, str(error))
            self.assertNotIn("synthetic-secret-marker", rendered)
            self.assertTrue(error.__suppress_context__)
        else:
            self.fail("Invalid configuration accepted")

    def test_numeric_raw_values_and_boundaries(self):
        from config.production_database import NUMERIC_SETTINGS, validate_production_settings
        for name, (low, high) in NUMERIC_SETTINGS.items():
            for value in ("synthetic-secret-marker", "1.0", " 1", "+1", "-1", "1e2", "", "??", str(high + 1), "9" * 5000):
                self.assert_safe_failure({**self.valid(), name: value}, name)
            for value in (str(low), str(high)):
                validate_production_settings({**self.valid(), name: value})

    def test_smtp_secure_alternatives_and_unknown_booleans(self):
        from config.production_database import validate_production_settings
        for tls, ssl in (("true", "false"), ("0", "1"), ("TRUE", "FALSE")):
            validate_production_settings({**self.valid(), "EMAIL_USE_TLS": tls, "EMAIL_USE_SSL": ssl})
        for name in ("EMAIL_USE_TLS", "EMAIL_USE_SSL"):
            for value in ("yes", "no", "on", "off", "", " true ", "synthetic-secret-marker"):
                self.assert_safe_failure({**self.valid(), name: value}, name)
        for value in ("true", "false"):
            self.assert_safe_failure({**self.valid(), "EMAIL_USE_TLS": value, "EMAIL_USE_SSL": value}, "EMAIL_USE_TLS")

    def test_redis_contract_and_redaction(self):
        from config.production_database import validate_production_settings
        validate_production_settings({"REDIS_URL": "redis://default:synthetic%40password@redis:6379/0"})
        for value in (None, "", "redis://redis:6379/0", "redis://:@redis:6379/0",
                      "redis://:synthetic-secret-marker@outside:6379/0",
                      "redis://:synthetic-secret-marker@redis:bad/0",
                      "redis://:synthetic-secret-marker@redis:6379/1",
                      "redis://:synthetic-secret-marker@redis:6379/0?x=y",
                      "redis://:synthetic-secret-marker@redis:6379/0#x",
                      "redis://user:synthetic-secret-marker@redis:6379/0",
                      "redis://:bad%XX@redis:6379/0", "redis://:bad%0a@redis:6379/0",
                      "redis://[invalid", "redis://:password@redis/0"):
            self.assert_safe_failure({} if value is None else {"REDIS_URL": value}, "REDIS_URL")

    def test_routine_type_inventory_and_defaults(self):
        grants = (ROOT / "deploy/postgres/grants.sql").read_text()
        inventory = (ROOT / "deploy/postgres/inventory.sql").read_text()
        self.assertIn("REVOKE ALL ON ALL ROUTINES IN SCHEMA public", grants)
        self.assertNotIn("ALL FUNCTIONS IN SCHEMA", grants)
        self.assertNotRegex(grants, r"GRANT EXECUTE")
        for marker in ("aclexplode(p.proacl)", "a.grantee <> p.proowner", "pg_get_userbyid(item.grantee)",
                       "t.typtype='c' AND c.relkind='c'", "aclexplode(item.typacl)",
                       "cv_migrate, cv_backup CASCADE", "Unapproved routine/type default grantee",
                       "FOR ROLE cv_owner REVOKE EXECUTE ON ROUTINES FROM PUBLIC"):
            self.assertIn(marker, grants)
        for marker in ("p.prokind", "pg_get_function_identity_arguments", "t.typacl", "t.typowner",
                       "standalone composite", "relation row type", "pg_default_acl"):
            self.assertIn(marker, inventory)
        source = (ROOT / "config/settings.py").read_text()
        self.assertLess(source.index("validate_production_settings(os.environ)"), source.index('env.int("EMAIL_PORT"'))


if __name__ == '__main__':
    unittest.main()
