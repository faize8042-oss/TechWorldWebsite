"""Deployment configuration checks that do not contact external services."""

from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import Error, register


@register()
def check_production_configuration(app_configs, **kwargs):
    if settings.DEPLOYMENT_MODE != "production":
        return []

    errors = []

    def error(message, setting):
        errors.append(
            Error(
                message,
                hint=f"Configure {setting} in the deployment environment.",
                id="deployment.E001",
            )
        )

    if len(settings.SECRET_KEY) < 50 or settings.SECRET_KEY.startswith("django-insecure-"):
        error("SECRET_KEY must be a strong, unique production secret.", "SECRET_KEY")

    if settings.DEBUG:
        error("DEBUG must be False in production.", "DEBUG")

    hosts = [host.strip().lower() for host in settings.ALLOWED_HOSTS]
    if not hosts or "*" in hosts or any(
        host in {"localhost", "127.0.0.1", "::1"} for host in hosts
    ):
        error(
            "ALLOWED_HOSTS must contain only confirmed public hostnames.",
            "ALLOWED_HOSTS",
        )

    for origin in settings.CSRF_TRUSTED_ORIGINS:
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            error(
                "CSRF_TRUSTED_ORIGINS entries must be valid HTTPS origins.",
                "CSRF_TRUSTED_ORIGINS",
            )
            break
        if parsed.hostname.lower() not in hosts:
            error(
                "Each CSRF trusted origin must also be listed in ALLOWED_HOSTS.",
                "CSRF_TRUSTED_ORIGINS and ALLOWED_HOSTS",
            )
            break

    if not settings.DATABASES["default"]["ENGINE"].endswith("postgresql"):
        error("Production must use PostgreSQL.", "DATABASE_URL")

    from config.production_database import runtime_database_errors
    for message in runtime_database_errors(
        settings.DATABASES["default"],
        getattr(settings, "POSTGRES_INITIALIZATION_USER", ""),
        getattr(settings, "PRODUCTION_CREDENTIAL_CONTRACT", ""),
    ):
        error(message, "DATABASE_URL / PRODUCTION_CREDENTIAL_CONTRACT")

    if not settings.EMAIL_HOST or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        error(
            "SMTP host, username, and password are required in production.",
            "EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD",
        )

    if not settings.ENABLE_HTTPS:
        error(
            "HTTPS must be explicitly enabled after TLS termination is verified.",
            "ENABLE_HTTPS",
        )

    if settings.PRODUCTION_PROXY_TRANSPORT != "unix" or settings.SECURE_PROXY_SSL_HEADER != ("HTTP_X_FORWARDED_PROTO", "https"):
        error("Production requires the private socket proxy configuration.", "PRODUCTION_PROXY_TRANSPORT")
    if settings.MIDDLEWARE[0] != "config.middleware.TrustedProxyIPMiddleware":
        error("Transport validation must precede all other middleware.", "MIDDLEWARE")
    if settings.SECURE_HSTS_SECONDS or settings.SECURE_HSTS_INCLUDE_SUBDOMAINS or settings.SECURE_HSTS_PRELOAD:
        error("HSTS must remain disabled pending real HTTPS verification.", "HSTS_SECONDS")
    if settings.SEO_INDEXING_ENABLED:
        error("Indexing must remain disabled during C6.1.", "SEO_INDEXING_ENABLED")
    return errors
