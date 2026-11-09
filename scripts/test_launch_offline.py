"""Run the application suite with synthetic configuration and an in-memory DB.

No dotenv, PostgreSQL, Redis, SMTP, uploads or existing service is used.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
keep = {k: v for k, v in os.environ.items()
        if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
os.environ.clear()
os.environ.update(keep)
os.environ.update({
    'CODEVENTRA_SKIP_DOTENV': '1', 'DJANGO_SETTINGS_MODULE': 'config.settings',
    'DEPLOYMENT_MODE': 'development', 'DEBUG': 'False',
    'SECRET_KEY': 'synthetic-launch-test-' + ('aB3!' * 20),
    'DATABASE_URL': 'sqlite://:memory:', 'CONTACT_EMAIL': 'test@example.invalid',
    'DEFAULT_FROM_EMAIL': 'test@example.invalid', 'EMAIL_HOST': 'smtp.example.invalid',
    'REDIS_URL': 'redis://localhost:1/0',
})

import django
from django.conf import settings
from django.test.runner import DiscoverRunner

django.setup()
settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
settings.ANALYTICS_HMAC_SECRET = ''
settings.STORAGES['staticfiles'] = {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}
settings.DATABASES['default']['TEST']['NAME'] = ':memory:'
sys.exit(bool(DiscoverRunner(verbosity=1).run_tests(
    ['config', 'core', 'contact', 'projects', 'analytics', 'blog', 'news', 'publishing'])))
