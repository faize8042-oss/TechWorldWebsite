# Publishing verifier investigation (2026-11-02)

## Confirmed cause: mount isolation false failure

Windows PowerShell 5.1's `ConvertFrom-Json` sends the JSON mount array down
the pipeline as a single object. `@($json | ConvertFrom-Json)` therefore
produced a nested array. The filter selected the entire web mount list when
any destination matched; its `Type` contained both `bind` and `volume`, so
the volume predicate failed. Assigning the decoded array before wrapping it
enumerates the mount records correctly. The verifier now also compares the
running named volume with merged Compose and checks planned Nginx mounts.

The actual merged Compose configuration was resolved locally: web mounts
private_uploads, media, and the private_publishing named volume; Nginx mounts
only its configuration file and media. The initializer also mounts the private
volume for ownership setup. Nginx has no private volume in merged Compose.
Running container mounts could NOT be inspected: Docker engine access was
denied at the Windows named pipe. Runtime isolation remains unverified.

## Migration drift and PostgreSQL regression failures: cause not yet established

The original implementation discarded the process exit code, setup errors,
and almost all management-command output. The reported aggregate failures
do not establish either real model drift or a PostgreSQL privilege problem.
Do not treat either failure as fixed or suppress it.

Drift runs in a one-off web container, using the read-only checkout at /app,
with `config.settings`, development environment from both Compose files,
and `makemigrations(check=True, dry_run=True, interactive=False)`. The local
offline equivalent against all installed apps reports no changes. This
does not establish the Docker result. The probe now distinguishes setup
failure from the drift command and explicitly reports drift exit 1.

Tests use the same one-off container, `config.verification_test_settings`,
and the eight app labels config/core/projects/contact/analytics/blog/news/
publishing. Django creates, migrates, tests, and destroys a new random
`test_publishing_qa_<32 hex characters>` database. Test settings preserve
PostgreSQL, disable persistent connections, and redirect cache, mail, media,
and publishing storage to isolated resources. The runner checks CREATEDB
or superuser capability and database-name nonexistence, then closes the
preflight application connection before handing control to Django. No role
privileges are altered. The random-name validation now requires an exact
match. Real PostgreSQL permissions, migration setup and teardown remain
unverified in this session.

Both container probes now report process exit and completion-marker status;
Python reports the stage and exception type, with validated SQLSTATE codes
when available. Test failures retain their identifiers and report exception
types without assertion values. No raw Docker output, connection strings,
credentials, or tracebacks are printed. One-off execution explicitly uses
`--no-build --pull never --no-deps`. No live migrations, container restarts,
image builds/pulls, volume deletion, or live publishing writes were performed.

## Validation

- Windows PowerShell mount regression: five cases passed (mixed valid mounts,
  Nginx exact-volume exposure, ancestor exposure, wrong volume, read-only volume).
- Offline Django: 105 tests passed, including with the diagnostic test runner.
- Django system checks: passed; all-app migration drift: no changes detected.
- Launch offline: 85 tests passed; preview: 11; preview security: 6.
- Full verifier: PASS=3 FAIL=1 SKIP=11, exit 1. Source and live HTTP/CSRF
  probes passed; Docker prerequisite failed; browser runtime unavailable.
- Docker Compose configuration resolved successfully, but Docker engine
  probes and PostgreSQL tests were NOT executed.

Rerun in the operator's Docker-enabled PowerShell, retaining the existing
Compose project environment:

```powershell
Set-Location D:\TechWorldWebsite
.\scripts\verify-publishing.ps1
```

The resulting stage/exit/SQLSTATE diagnostics are needed to finish the
PostgreSQL and container drift investigation if those failures persist.

## Final two probes: startup diagnostics follow-up

The live failure is still unconfirmed. In this session `docker info` failed
with access denied to the engine pipe; no disposable probes or PostgreSQL
regressions could be executed. An individually readable /tmp mount does not
establish visibility of all /app file destinations or Python import origins.

Both probes construct `docker compose -f <root>/compose.yaml -f
<root>/compose.development-build.yaml run --rm --no-deps --pull never -T
--no-build --workdir /app --entrypoint python -e
PYTHONDONTWRITEBYTECODE=1`, followed by one `--volume
<absolute-Windows-file>:/app/<relative-file>:ro` per verification file,
then `web -c <bootstrap> drift` (or `tests`). The bootstrap opens the helper
with runpy and preserves its mode argument and exit code. All files are
validated as host leaf files first. No package directory is mounted over
an image package. Individual test files and verification settings deliberately
shadow their image counterparts; the application's settings, models,
migrations and package initializers remain from the image. Docker creates
missing destination parents; file/directory conflicts or runtime errors
are now classified without echoing untrusted stderr. Import discovery in
the diagnostic mode reports whether an image package shadows the scripts
namespace or resolves config somewhere unexpected.

PowerShell passes an argument array directly to docker, with no shell layer.
The bootstrap contains no embedded double quotes, avoiding PS 5.1's native
quote stripping. Offline tests execute that bootstrap through Windows
PowerShell 5.1 and check both probes' exact mount arguments. No evidence
currently justifies changing mount locations or replacing image packages.

Run this safe, database-free diagnostic command on the Docker-enabled host:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scriptserify-publishing.ps1 -DiagnoseStartup
```

It prints the exact Docker argv as a JSON array (each element is one argument),
checks each mounted destination is a readable file, and discovers config and
scripts import origins. It does not execute settings, migrations or tests.
It uses disposable containers with no build, pull, dependency startup or
existing-container restart. Success here is startup verification only.
Normal execution now emits a Python-started marker before opening the helper
and classifies native failures using fixed labels. Raw stderr is withheld.
An additional confirmed reporting bug was corrected: the helper's literal
migration-drift failure explanation was previously discarded by its own
output filter. Actual failing exit codes and missing completion markers
continue to fail the suite.

Validation: Windows PowerShell regression checks passed (mount isolation,
both command arrays, actual Python bootstrap marshalling, sanitized startup
classification and database-free diagnostic mode); both Python diagnostic
unit tests passed. Full live verification remains outstanding:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scriptserify-publishing.ps1
```
