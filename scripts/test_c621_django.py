"""Run Django SimpleTestCases using only synthetic development settings.

Clear inherited application/libpq values before importing Django; never read dotenv.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
keep = {key: value for key, value in os.environ.items()
        if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
os.environ.clear()
os.environ.update(keep)
os.environ.update({
    'CODEVENTRA_SKIP_DOTENV': '1', 'DJANGO_SETTINGS_MODULE': 'config.settings',
    'DEPLOYMENT_MODE': 'development', 'DEBUG': 'False',
    'SECRET_KEY': 'synthetic-test-only-' + ('aB3!' * 20),
    'DATABASE_URL': 'sqlite://:memory:', 'CONTACT_EMAIL': 'test@example.invalid',
    'DEFAULT_FROM_EMAIL': 'test@example.invalid', 'EMAIL_HOST': 'smtp.example.invalid',
    'REDIS_URL': 'redis://localhost:1/0',
})
import django
from django.test.runner import DiscoverRunner

django.setup()
# config.tests contains only SimpleTestCase; no database setup or external services.
runner = DiscoverRunner(verbosity=1)
sys.exit(bool(runner.run_tests(['config.tests'])))
