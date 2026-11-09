# Development image build and migration review

The root `compose.yaml` references `techworld-django:local` but has no `build`
section. Consequently, `docker compose build web` has nothing to build. The root
`Dockerfile` is the normal application build: Python 3.12, requirements install,
source copy, WhiteNoise static collection with placeholder credentials, and
Gunicorn as a non-root user. The preview and validation Dockerfiles are separate
workflows and are not the build for this development stack.

`compose.development-build.yaml` is an explicit opt-in override for the root
Compose file. It builds a separate image tag, preserving `techworld-django:local`
and the existing running containers. It also adds private publishing storage and
a one-shot ownership initializer, described in
[`development-publishing-storage.md`](development-publishing-storage.md).
Existing Contact/public media mounts, database storage, Redis configuration,
ports, and networks are preserved. Do not combine it with production Compose.

The root context and `COPY . .` include `blog/`, `news/`, `publishing/`, their
Python migrations, `config/`, `templates/` (including publishing templates), and
`static/css/publishing.css`. Blog, News, and publishing are already installed in
normal settings and routed by `config/urls.py`. Publishing uses abstract shared
models; its concrete database migrations are in Blog and News. Static collection
recreates `staticfiles/` in the image; Nginx proxies static requests to WhiteNoise.

The existing `.dockerignore` excludes `.env` and `.env.*`, Python environments,
Git, `private_uploads/`, `private_publishing/`, `media/`, backups, validation output, and local databases.
The build receives no env_file or secret build arguments. Compose reads `.env`
for interpolation and injects it at runtime only. Do not add credentials through
build arguments or copy an env file into the context under another name. Avoid
printing `docker compose config` without `--quiet`, which can expose resolved
runtime secrets.

Publishing cover images use `/app/private_publishing` by default, distinct from
contact attachments in `/app/private_uploads`. The development override now mounts
a project-scoped named volume at that path. Its initializer sets the volume root
to UID/GID 10001 and mode 0700 before web starts. The built image does not need
to be rebuilt for this storage change. Nginx receives no publishing mount.
Before replacement, preserve any publishing files in an old container's writable
layer as described in the storage runbook. Preparing the configuration does not
provision storage or move existing files.

## Build (operator commands; not performed during preparation)

Use PowerShell in `D:\TechWorldWebsite`. Retain the same project name and project
directory used by the running stack. If it was started with `-p NAME` or
`COMPOSE_PROJECT_NAME`, use that same value for every command below. Changing the
project name can select a different PostgreSQL volume. Do not use `down -v`,
volume prune, or delete/recreate the uploads directories.

First preserve the exact running web image, even if the local tag has moved:

```powershell
$webId = docker compose -f compose.yaml ps -q web
if ($LASTEXITCODE -ne 0 -or -not $webId) { throw 'Expected one running web container.' }
$oldImage = docker inspect --format '{{.Image}}' $webId
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the running image.' }
docker image tag $oldImage techworld-django:before-publishing
if ($LASTEXITCODE -ne 0) { throw 'Cannot preserve rollback image.' }
docker compose -f compose.yaml -f compose.development-build.yaml config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Invalid development Compose configuration.' }
docker compose -f compose.yaml -f compose.development-build.yaml build web
```

The build may need network access for the Python base image and dependencies;
requirements specify ranges, so this is not a locked reproducible build. Building
does not deploy the image or update the running container. Never build the new
source directly over the rollback tag.

Verify packaged code, templates, migrations, and collected CSS without touching
the stack or loading its secrets:

```powershell
docker run --rm --network none --entrypoint python techworld-django:development-publishing -c "from pathlib import Path; paths=['blog/models.py','news/models.py','publishing/models.py','blog/migrations/0001_initial.py','news/migrations/0001_initial.py','templates/publishing','static/css/publishing.css','staticfiles/css/publishing.css','staticfiles/staticfiles.json']; missing=[p for p in paths if not Path('/app',p).exists()]; assert not missing, missing; assert not list(Path('/app').rglob('.env*')); print('Application files and collected static assets verified; no .env files found.')"
```

## Read-only database migration review

These commands use the **new image**, the existing runtime environment, and the
existing development database. `--no-deps` prevents starting PostgreSQL or Redis;
they must already be running. These commands create only disposable web runner
containers and do not apply migrations or restart services. Do not use `exec web`
for this review: that would inspect the old running image.

```powershell
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps web python manage.py check
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps web python manage.py makemigrations --check --dry-run
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps web python manage.py showmigrations blog news
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps web python manage.py migrate --plan
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps web python manage.py sqlmigrate blog 0001
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps web python manage.py sqlmigrate news 0001
```

Review the entire plan for unrelated pending migrations, inspect the initial
Blog/News tables, constraints and indexes, and stop on any failure or unexpected
operation. No migration application or deployment is authorized by this runbook.
Before a separately approved application, take and verify a PostgreSQL backup
using the established backup procedure, and back up media/private uploads.

## Rollback

Before deployment, the existing containers and database are unchanged. Simply
stop using the override; the original image tag remains available. A rebuild
alone requires no service or database rollback.

If a later, separately approved deployment needs to be reverted, create this
temporary override in the repository root:

```yaml
# compose.rollback.yaml
services:
  web:
    image: techworld-django:before-publishing
    pull_policy: never
```

Then, only when a web replacement is approved, use the base file plus the rollback
override (omit the development build override):

```powershell
docker compose -f compose.yaml -f compose.rollback.yaml up -d --no-deps --no-build web
```

This replaces only web and retains PostgreSQL, Redis, Nginx, and both upload
mounts. Do not run it as part of build preparation. Application rollback does not
undo database changes. If initial Blog/News migrations were later applied,
normally retain their additive tables while using the old image. Do not run
`migrate blog zero` or `migrate news zero`: those delete editorial data. Database
restoration requires a separately reviewed recovery plan and a verified backup.

## Preparation validation

- Compose merged configuration: `config --quiet` passed. Docker emitted a local
  config.json access warning; no daemon or image operation was performed.
- Django system checks and `makemigrations --check --dry-run` passed using
  `config.publishing_test_settings`; no model changes are missing migrations.
- 92 application tests passed with that settings module, using only a temporary
  in-memory SQLite test database and synthetic configuration.
- Broad offline unittest discovery ran 86 tests: 11 failures were PowerShell
  execution-policy blocks, and one import error arose because
  `test_launch_offline.py` is a standalone runner that calls `sys.exit` at import.
  Its embedded application suite passed 80 tests. No execution policy was changed.
- `git diff --check` passed. No images were built, stack services restarted,
  PostgreSQL migrations applied, or tunnels started. Image contents and live
  database plans still need the operator checks above after a build.
