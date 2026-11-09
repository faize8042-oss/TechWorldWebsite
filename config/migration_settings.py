"""Operator-only migration settings; never use for web/Gunicorn.

The normal runtime secret is needed for base settings, but the runner receives
only runtime + migration secrets, never the initialization administrator secret.
System checks deliberately reject this identity for web. See the runbook.
"""
import json
from pathlib import Path

from .settings import *  # noqa: F403
from .production_database import validate_database_url

if DEPLOYMENT_MODE != "production":  # noqa: F405
    raise ValueError("Migration settings require production mode.")
try:
    migration_values = json.loads(Path("/run/secrets/django_migration").read_text())
    if not isinstance(migration_values, dict) or set(migration_values) != {"DATABASE_URL"}:
        raise ValueError
    migration_url = migration_values["DATABASE_URL"]
except (OSError, ValueError, KeyError, TypeError):
    raise ValueError("Invalid dedicated migration secret.") from None
validate_database_url(migration_url, login="cv_migrate")
DATABASES = {"default": env.db_url_config(migration_url)}  # noqa: F405
DATABASES["default"]["OPTIONS"] = {"assume_role": "cv_owner", "options": "-c search_path=public"}
del migration_url, migration_values
