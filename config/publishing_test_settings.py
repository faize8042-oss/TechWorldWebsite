"""Isolated offline checks and tests; never reads .env or connects to project databases."""
from .preview_settings import *
SECRET_KEY = 'offline-tests-only'
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'core', 'projects', 'contact', 'analytics', 'publishing', 'blog', 'news']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
ROOT_URLCONF = 'config.urls'
MIDDLEWARE = ['django.contrib.sessions.middleware.SessionMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware']
TEMPLATES[0]['APP_DIRS'] = True
TEMPLATES[0]['OPTIONS']['context_processors'] += ['django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']
STORAGES['staticfiles'] = {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'
ANALYTICS_HMAC_SECRET = ''
ANALYTICS_RETENTION_DAYS = 90
TRUSTED_PROXY_IPS = []
DEPLOYMENT_MODE = 'development'
ENABLE_HTTPS = False

TIME_ZONE = 'UTC'
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = False
PRODUCTION_PROXY_TRANSPORT = ''
MIDDLEWARE = ['config.middleware.TrustedProxyIPMiddleware', 'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'analytics.middleware.PrivacyAwareAnalyticsMiddleware']
