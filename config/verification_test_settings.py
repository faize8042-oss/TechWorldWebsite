"""Ephemeral PostgreSQL QA settings; used only by scripts/publishing_verify.py."""
import os
import re
from pathlib import Path
from .settings import *  # noqa: F403

if DEPLOYMENT_MODE != 'development':
    raise RuntimeError('Verification tests require the development deployment.')
if not re.fullmatch(r'test_publishing_qa_[0-9a-f]{32}', os.environ.get('PUBLISHING_QA_DATABASE', '')):
    raise RuntimeError('Use the verification runner to allocate an isolated database.')
DATABASES['default']['TEST'] = {'NAME': os.environ['PUBLISHING_QA_DATABASE']}
DATABASES['default']['CONN_MAX_AGE'] = 0
DATABASES['default']['CONN_HEALTH_CHECKS'] = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
PUBLISHING_IMAGE_ROOT = Path(os.environ['PUBLISHING_QA_TEMP']) / 'publishing'
MEDIA_ROOT = Path(os.environ['PUBLISHING_QA_TEMP']) / 'media'
STORAGES = {**STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
