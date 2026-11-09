# Publishing PostgreSQL test connection fix

## Cause and changes

`PublishingTests.test_images_reencoded_private_and_revoked` exhausted the test
client's streaming iterator, then called `response.close()` again. Django 5.2's
`closing_iterator_wrapper` already closes the response while temporarily
disconnecting `close_old_connections` from `request_finished`. The second close
sent that signal without this protection. Connection cleanup sees autocommit
disabled by `TestCase`'s atomic transaction and closes the connection. PostgreSQL
then rejects queries in that transaction, including subsequent test setup.
In-memory SQLite ignores connection close requests, masking the defect.

Removed the redundant close. Regression assertions now check response closure,
no call to `connection.close`, no closed transaction, and a successful ORM query
after streaming for both Blog and News. Existing JPEG, metadata, privacy, and
publication revocation assertions remain intact. The integrity-error tests
already use nested atomic savepoints correctly. No application connection,
transaction, publication, storage, or database constraint behavior was changed.
The fixture's temporary storage cleanup and settings restoration do not close
database connections; the clock mock is scoped to its context manager.

The database-free preview test now uses `config.preview_settings.MIDDLEWARE`
with a valid preview host. It retains `SimpleTestCase`'s database prohibition
and asserts that analytics neither attempts a write nor logs an exception,
even with an analytics secret configured. Production analytics handling is
unchanged.

## Local validation

Run from `D:\TechWorldWebsite`:

```powershell
python manage.py test --settings=config.publishing_test_settings --noinput --verbosity 1
python manage.py check --settings=config.publishing_test_settings
python manage.py makemigrations blog news --check --dry-run --settings=config.publishing_test_settings
python scripts/test_client_preview.py
python scripts/test_client_preview_security.py
python scripts/test_launch_offline.py
```

Results: 92 Django tests passed; system checks reported no issues; no Blog/News
migration drift; 11 preview tests, 6 preview security tests, and 80 launch tests
passed. These are offline checks, not PostgreSQL verification. Existing
`DATABASES` override warnings and the deliberate contact email failure log
remain in the broader suite; the preview analytics warning is gone.

## Operator PostgreSQL verification

Docker engine access was denied in the repair session. Run these commands from
the operator's PowerShell with Docker access and the existing development DB
already running. Retain any original Compose project name (`-p NAME` or
`COMPOSE_PROJECT_NAME`). Use the existing development image and dependencies.
The read-only source mount ensures the runner tests this checkout, rather than
stale tests baked into the image. No build or service restart is required.

```powershell
Set-Location D:\TechWorldWebsite
$sourcePath = (Get-Location).Path
$files = @('-f', 'compose.yaml', '-f', 'compose.development-build.yaml')
docker compose @files config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Invalid Compose configuration.' }

# Assert the runner uses PostgreSQL without opening a database connection.
docker compose @files run --rm --no-deps --volume "${sourcePath}:/app:ro" --workdir /app --entrypoint python web -c "import os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; import django; django.setup(); from django.conf import settings; assert settings.DATABASES['default']['ENGINE']=='django.db.backends.postgresql'; print('PostgreSQL backend verified')"
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL preflight failed.' }

docker compose @files run --rm --no-deps --volume "${sourcePath}:/app:ro" --workdir /app --entrypoint python web manage.py test blog news publishing --settings=config.settings --noinput --verbosity 2
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL publishing tests failed.' }

# Repeat to check clean teardown and a fresh test database lifecycle.
docker compose @files run --rm --no-deps --volume "${sourcePath}:/app:ro" --workdir /app --entrypoint python web manage.py test blog news publishing --settings=config.settings --noinput --verbosity 2
if ($LASTEXITCODE -ne 0) { throw 'Repeated PostgreSQL publishing tests failed.' }
```

Expected: 12 tests pass on each run, with no closed-connection errors and no
preview analytics exception. Django creates, migrates, and drops its separate
test database (normally `test_techworld_db`); the configured DB user needs test
database creation privileges. `--noinput` may replace an existing database with
that reserved test name, so ensure it contains only disposable test data.
Do not run `migrate` against the development database. These commands do not
start dependencies, restart containers, delete volumes, or change credentials.
PostgreSQL results remain unverified until the operator runs them.
