"""Isolated source preview on loopback; memory DB/mail/cache, no dotenv or secrets."""
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
    'DEPLOYMENT_MODE': 'development', 'DEBUG': 'True',
    'SECRET_KEY': 'synthetic-source-preview-' + 'aB3!' * 20,
    'DATABASE_URL': 'sqlite://:memory:', 'CONTACT_EMAIL': 'test@example.invalid',
    'DEFAULT_FROM_EMAIL': 'test@example.invalid', 'REDIS_URL': 'redis://localhost:1/0',
    'EMAIL_HOST': 'smtp.example.invalid',
})
import django
django.setup()
from django.conf import settings
from django.core.management import call_command

settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
settings.ANALYTICS_HMAC_SECRET = ''
settings.STORAGES['staticfiles'] = {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}
call_command('migrate', interactive=False, verbosity=0)
# One thread preserves the in-memory SQLite connection. No existing DB is used.
call_command('runserver', '127.0.0.1:8091', use_reloader=False, use_threading=False)
