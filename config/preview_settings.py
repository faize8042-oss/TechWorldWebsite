"""Standalone, database-free client preview. Never imports normal settings/dotenv."""
import secrets
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = secrets.token_urlsafe(64)  # process-local; no sessions or forms
DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.trycloudflare.com']
CSRF_TRUSTED_ORIGINS = []
USE_X_FORWARDED_HOST = False
SECURE_PROXY_SSL_HEADER = None  # forwarded protocol is deliberately ignored
SECURE_SSL_REDIRECT = False  # Cloudflare terminates HTTPS; local ingress is HTTP
SECURE_HSTS_SECONDS = 0
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'no-referrer'
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
INSTALLED_APPS = ['django.contrib.staticfiles']
MIDDLEWARE = ['config.preview.PreviewBoundary', 'django.middleware.security.SecurityMiddleware',
              'whitenoise.middleware.WhiteNoiseMiddleware',
              'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.preview_urls'
DATABASES = {'default': {'ENGINE': 'django.db.backends.dummy'}}
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
EMAIL_HOST = ''
EMAIL_HOST_USER = EMAIL_HOST_PASSWORD = ''
DEFAULT_FROM_EMAIL = CONTACT_EMAIL = 'preview@example.invalid'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates',
 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': False,
 'OPTIONS': {'context_processors': ['django.template.context_processors.request',
                                  'core.context_processors.seo_context']}}]
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
 'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'}}
WHITENOISE_AUTOREFRESH = False
WHITENOISE_USE_FINDERS = False
SEO_SITE_URL = ''
SEO_INDEXING_ENABLED = False
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
