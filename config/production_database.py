"""Production secret contract. No database connections or value-bearing errors."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, unquote

RUNTIME_KEYS = frozenset({
    "DATABASE_URL", "SECRET_KEY", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS",
    "REDIS_URL", "CONTACT_EMAIL", "DEFAULT_FROM_EMAIL", "EMAIL_HOST",
    "EMAIL_PORT", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "EMAIL_USE_TLS",
    "EMAIL_USE_SSL", "ANALYTICS_HMAC_SECRET", "SEO_SITE_URL",
})


def validate_database_url(value, login="cv_runtime"):
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {"postgres", "postgresql"}
                 and unquote(parsed.username or "") == login
                 and bool(parsed.password) and parsed.hostname == "db"
                 and parsed.port in {None, 5432} and parsed.path == "/codeventra"
                 and not parsed.query and not parsed.fragment)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError("DATABASE_URL violates the production database identity contract.")


def load_runtime_environment(environ):
    # Reject ambient database overrides, libpq options, and privileged credentials.
    # The Compose template has no env_file; only the protected allowlist is imported.
    forbidden = {"DATABASE_URL", "PRODUCTION_ENV_FILE", "DJANGO_SETTINGS_MODULE_OVERRIDE"}
    if any(key in forbidden or key.startswith(("POSTGRES_", "PG", "MIGRATION_", "BACKUP_"))
           for key in environ):
        raise ValueError("Privileged or ambient database configuration is forbidden in web.")
    if environ.get("PRODUCTION_RUNTIME_FILE") != "/run/secrets/django_runtime":
        raise ValueError("PRODUCTION_RUNTIME_FILE must use the dedicated runtime secret mount.")
    try:
        values = json.loads(Path(environ["PRODUCTION_RUNTIME_FILE"]).read_text(encoding="utf-8"))
        if (not isinstance(values, dict) or set(values) - RUNTIME_KEYS
                or not all(isinstance(v, str) for v in values.values())):
            raise ValueError
    except (OSError, ValueError, TypeError):
        raise ValueError("Invalid production runtime secret file.") from None
    validate_database_url(values.get("DATABASE_URL"))
    # No ambient overrides of application secrets/configuration are allowed.
    if RUNTIME_KEYS.intersection(environ):
        raise ValueError("Runtime configuration must come only from the dedicated secret file.")
    environ.update(values)


def runtime_database_errors(database, admin, contract):
    errors = []
    if admin != "cv_init" or contract != "runtime-secret-v1":
        errors.append("Production credential separation contract is missing or unsupported.")
    if (database.get("USER") != "cv_runtime" or database.get("USER") == admin
            or not database.get("PASSWORD") or database.get("HOST") != "db"
            or database.get("NAME") != "codeventra"
            or str(database.get("PORT", "")) not in {"", "5432"}
            or database.get("OPTIONS", {}) != {"options": "-c search_path=public"}):
        errors.append("DATABASE_URL must configure the dedicated runtime identity without elevated options.")
    return errors


NUMERIC_SETTINGS = {"EMAIL_PORT": (1, 65535), "HSTS_SECONDS": (0, 2147483647),
                    "ANALYTICS_RETENTION_DAYS": (1, 2147483647)}


def validate_production_settings(values):
    """Validate raw strings before django-environ can emit value-bearing errors."""
    for name, (minimum, maximum) in NUMERIC_SETTINGS.items():
        if name not in values:
            continue  # Existing safe settings defaults remain in force.
        value = values[name]
        if (not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,10}", value)
                or not minimum <= int(value) <= maximum):
            raise ValueError(f"{name} must be a decimal integer in the approved range.") from None
    transport = {}
    for name, default in (("EMAIL_USE_TLS", "true"), ("EMAIL_USE_SSL", "false")):
        value = values.get(name, default)
        if not isinstance(value, str) or value.lower() not in {"true", "false", "1", "0"}:
            raise ValueError(f"{name} must be true, false, 1 or 0.") from None
        transport[name] = value.lower() in {"true", "1"}
    if transport["EMAIL_USE_TLS"] == transport["EMAIL_USE_SSL"]:
        raise ValueError("EMAIL_USE_TLS and EMAIL_USE_SSL require exactly one secure transport.") from None
    validate_redis_url(values.get("REDIS_URL"))


def validate_redis_url(value):
    """Internal Redis service, password authentication, explicit database zero."""
    try:
        parsed = urlsplit(value)
        valid = (isinstance(value, str) and not any(c.isspace() or ord(c) < 32 for c in value)
                 and parsed.scheme == "redis" and parsed.hostname == "redis"
                 and parsed.port == 6379 and parsed.path == "/0"
                 and parsed.username in {"", "default"} and bool(parsed.password)
                 and not parsed.query and not parsed.fragment
                 and not re.search(r"%(?![0-9a-fA-F]{2})", value)
                 and not any(ord(c) < 32 for c in unquote(parsed.password or "")))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("REDIS_URL violates the authenticated production Redis contract.") from None
