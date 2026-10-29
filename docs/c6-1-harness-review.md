# C6.1 validation harness review

## Final validation status (2026-10-29)

READY for the scoped C6.1 pre-commit change; NOT READY for production deployment.
No critical or high implementation finding was identified. Evidence: `validation-results/codeventra-c61-validation-42034212ee95426c8ffd6da4754203ba/`.
The successful operator-run Linux Docker validation supersedes earlier daemon
access failures and claims that runtime validation was never executed. This final
review inspected retained evidence and reran offline checks without invoking Docker.
No real credentials or `.env` were accessed; existing development containers were
not modified. Nothing was staged, committed, pushed or deployed.

Implemented and passed: both image builds; synthetic Compose render/replay;
disposable certificate generation; isolated startup; Gunicorn 23 config and Unix
readiness; `nginx -T`; Nginx socket visibility; TLS/proxy, redirect/query and IPv4
identity checks; forged forwarded/alternate SSL/HTTP marker header checks;
directory `10001:10002/2750` and socket `10001:10002/0660`; non-root web identity;
unauthorized UID/GID denial; application TCP listener ownership checks; database
and Redis mount/path exclusion and sampled active TCP refusal from their network
namespaces (ports 8000, 8001, 8080, 80, 443).

The ownership-aware TCP probe permits an unrelated namespace listener only after
a complete stable descriptor census and different kernel creator UID. It does
not claim the entire network namespace has no TCP listeners.

Synthetic production `check --deploy` completed with the expected HSTS-disabled
`security.W004` warning. Focused Django tests: 37 passed; full suite: 79 passed.
Test suites use development-mode synthetic settings and in-memory SQLite/cache/
email; they do not validate production database-backed routes. Final offline
regressions passed 13 PASS outputs (three PowerShell groups and ten generated
Python probe cases); `git diff --check` passed.

`outcome.txt` records success, no `failure.txt` exists, and final cleanup inventories
are empty for owned containers, networks, volumes and images. Shared build cache
and pulled base images remain outside run-owned cleanup. Evidence stays on disk
and is excluded from future staging by `/validation-results/` in `.gitignore`.

## Unimplemented integration scenarios

- Emitted secure cookies and CSRF enforcement through full application routes.
- Unknown HTTP hosts/TLS names and IPv6 visitor identity through Nginx.
- Worker unlink/replace denial and read-only-root/writable-upload behavior.
- Stale socket cleanup, web restart/recreation and Nginx reconnection.
- Startup refusal for deliberately invalid/additional listeners, paths,
  ownership/modes, Gunicorn scheme headers and production settings.
- Live direct unmarked WSGI/ASGI rejection. Unit and fake-hook contracts do not
  replace dedicated Linux negative integration tests.

## Privilege boundary and deployment blockers

Nginx workers have restricted group 10002 socket access, without directory write
permission; its master process still runs as root. The whole Nginx container is
not non-root. Successful proxy requests demonstrate access, not worker mutation
denial. Host/Docker administrators and authorized socket clients remain trusted;
a compromised authorized socket client can forge headers.

Complete outstanding integration scenarios before release. Approve immutable
application/custom Nginx image digests and dependency/base-image review; verify
real domain/DNS, certificate trust/renewal and actual HTTPS; privately validate
production inputs and a separate least-privilege PostgreSQL runtime role; verify
target-volume permissions, database-backed routes, SMTP and backup/restore.
Synthetic TLS and fresh-volume success do not approve real deployment inputs or
existing volumes. HSTS and indexing remain disabled. Build tags/ranges can vary.

## Safe preflight

```powershell
.\scripts\validate-c6-1.ps1 -PreflightOnly
```

Checks local Docker/Git executable discovery and required source-file existence.
Prints proposed project, images, service containers, networks, volumes, temporary
directory and results directory. Creates no directories/resources, starts no
processes, reads no environment values or secrets and runs no builds. It cannot
verify daemon access, Linux/Desktop engine, Compose capabilities, collisions,
registry availability or runtime readiness. Names are proposals; a later full
execution generates a fresh GUID. The successful full run supplies runtime evidence; this mode is optional.

## Production settings and readiness

The generated diagnostic WSGI application explicitly selects `config.settings`,
also set explicitly in the web service environment. Startup assertions require
production mode, DEBUG off, Unix transport, HTTPS redirect, secure-cookie flags,
the exact proxy SSL tuple, transport/security middleware ordering, indexing off
and HSTS zero. The real production Gunicorn hook remains in use. The diagnostic
handler invokes transport and security middleware around synthetic JSON only;
it does not exercise the full production middleware stack or routes.

`validation_settings.py` exists solely for focused/full `manage.py test` runs.
Those commands select it through `DJANGO_SETTINGS_MODULE=validation_settings`,
set development mode and disable HTTPS. It imports base settings, then uses
in-memory SQLite/cache/email and temporary public media. Gunicorn and
`check --deploy` use `config.settings`, never this test module. Test containers
still mount the run's disposable Compose volumes; no real volumes are attached.

Compose startup is not proof of application readiness. A separate retry loop
requires an actual HTTP response over Gunicorn's Unix socket, followed by a
separate Nginx TLS/proxy probe including redirect/header assertions. Retry windows
are 120 seconds; an in-flight native command can extend the window. Each native
command is separately bounded by `-TimeoutSeconds` (default 1200).

## Certificate and isolation checks

The staged validation Dockerfile explicitly installs OpenSSL through Debian apt;
the production Dockerfile is untouched. This removes reliance on an incidental
CLI in python:slim. Generation uses restrictive umask, logs the version, verifies
the self-signature and checks expiration; actual Nginx TLS must subsequently
work. This repair is statically reviewed, not a tested Linux-image alternative:
package installation, generation and TLS compatibility remain unverified until
an authorized operator runs the harness. Registry/package access is required.

Socket checks require directory 10001:10002/2750, socket 10001:10002/0660,
non-root web execution and no TCP/TCP6 listeners in web's namespace. An unrelated
UID/GID must receive permission denial; successful proxy requests demonstrate
Nginx socket access. Database/Redis mounts and paths must exclude the socket.
Application-image helpers share each running peer's exact network namespace
and require TCP connection refusal to web addresses on ports 8000, 8001, 8080,
80 and 443. Timeouts/routing errors fail as inconclusive. This is sampled active
port coverage plus exhaustive listener-table snapshots, not continuous monitoring.

## Compose, arguments and environment

Compose output is converted from JSON into PowerShell objects and serialized
with depth 60. Compose config output already preserves the escaped shell dollars
(`$$`); serialization retains them verbatim for replay. Doubling them again
produces `$$$$`, which reaches the container shell as `$$` (its process ID).
Exact PostgreSQL health-check, Redis health-check and Redis startup command
contracts are checked on the initial render, generated file and replayed Compose
config before builds. `scripts/test-c6-1-compose-generation.ps1` provides offline
serialization and negative expansion regression cases without running the harness.
The rendered top-level project name is
removed; the explicit CLI project name is authoritative. Unexpected service sets
and dangerous service properties are rejected. Resources and built images carry
the GUID run label; helpers are labeled too.

Native commands use Windows CRT argument quoting for embedded quotes and trailing
backslashes, with shell execution disabled. Runtime argument/JSON round trips
remain untested. Docker children remove known interpolation keys and all
COMPOSE_* overrides without reading their values, disable implicit dotenv, and
remove DOCKER_HOST/DOCKER_CONTEXT overrides. Explicit synthetic env files and the
captured local named-pipe context select the target. Docker configuration,
credential helpers and build proxy configuration are not sandboxed; a trusted
Docker installation is a prerequisite.

## Cleanup and recovery

Cleanup inventories exact GUID labels, rechecks labels immediately before
removing IDs and processes containers, networks, volumes, then images. Individual
listing/removal failures are recorded and do not stop other resource removals.
Before each verified container is removed, its health status and recent health
probe results are saved to `health-<id>.json`. Known synthetic secret values are
redacted; full container inspection/environment is not saved. Health capture
failures are recorded separately and do not prevent cleanup.
A separate final inventory includes stopped containers and must find no owned
resources of any of those four kinds. No broad prune or Compose down is used.

Any cleanup failure, failed verification or native timeout causes nonzero exit
and retains staging. Results contain run label, context, staging path, removal
records, errors and final inventories. Successful cleanup alone permits deletion
of the verified absolute GUID staging directory. Build cache and pulled base
images are shared, not run-owned, and remain untouched.

After an interrupted run, read `validation-results/<run>/run.txt`, select its
recorded context, list exact-label resources (including stopped containers),
inspect every ID/label, then remove only verified run IDs in the same dependency
order. Re-list all four kinds before manually removing staging. Daemon builds
can outlive the CLI: wait for outstanding work and repeat exact-label discovery.
A killed PowerShell process cannot guarantee finally runs. Concurrent Docker
administrator tampering is outside this ownership guarantee.

## Remaining coverage

All implemented runtime assertions above passed in the recorded run. These dedicated
Linux integration scenarios remain unimplemented:

- Emitted secure cookies and CSRF enforcement through full application routes.
- Unknown HTTP hosts/TLS names and IPv6 Nginx visitor identity.
- Nginx worker unlink/replace denial, read-only-root and writable-upload behavior.
- Stale-socket cleanup, web restart/recreation and Nginx reconnection.
- Startup refusal for deliberately invalid/additional listeners, socket paths,
  ownership/modes, Gunicorn scheme headers and production settings.
- Direct unmarked WSGI/ASGI rejection through a live server; unit contracts do
  not replace these integration cases.
- Real certificate trust/renewal/DNS, production inputs, least-privilege database
  role, actual database-backed requests, SMTP and backup/restore rehearsals.

Production security validation is incomplete. Passing the implemented subset
must never be described as full C6.1 or production readiness validation.


### C6.1 socket mount correction

Nginx must not mount tmpfs at `/var/run` (the image aliases it to `/run`),
`/run`, or another parent of `/run/codeventra`. The production template and
isolated replay retain the read-only named socket volume. The custom Nginx
image sets its main-context PID directive to `/run/nginx/nginx.pid`; only
`/run/nginx` receives the dedicated 1 MiB runtime tmpfs. Cache and temporary
files retain their existing restricted tmpfs mounts and the root stays read-only.
Gunicorn's Unix-only transport, UID/GID and socket permissions are unchanged.

Run `powershell -NoProfile -File scripts/test-c6-1-compose-generation.ps1`
for offline coverage of mount parents/aliases, PID configuration, serialization
and sanitized command diagnostics. No Docker or environment files are needed.
Failures identify the validation stage and sanitized Docker command; raw failed
command output, environment assignments, paths and payloads are omitted.

The successful Linux run verified the dedicated PID path, socket visibility,
TLS/proxy and security checks, and exact-label cleanup.

### TCP listener ownership correction (2026-10-29)

The saved failure `4:184549503:34065` decodes to IPv4
`127.0.0.11:34065`, consistent with Docker embedded DNS. The old probe read
`/proc/net/tcp{,6}`, which describes the entire network namespace, and rejected
all LISTEN entries without consulting process descriptors. This confirms the
probe was broader than its Gunicorn security requirement; the saved artifacts
do not include inode ownership, so DNS attribution remains to be verified on
Docker.

The generated probe now takes stable TCP-table and PID snapshots and scans
all visible process descriptors for `socket:[inode]` links. Any locally held
TCP listener fails (including a root-created listener inherited by Gunicorn).
An unheld listener is accepted only with a nonzero inode and a kernel creator
UID different from the application UID, after a complete successful census.
This identifies sockets outside the isolated application PID namespace without
assuming that a particular loopback address or port is safe. Missing ownership
for an application-created socket, unreadable/racing descriptors, PID changes,
zero inodes and TCP-table changes fail closed. The isolated web service must
retain its private PID namespace; this is not a general host-wide audit.
No command lines, environment values or arbitrary exception strings are logged.
The production Gunicorn Unix-only worker guard and separate peer-container
connection-refusal tests are unchanged.

Final offline validation: 13 PASS outputs. Earlier Docker API named-pipe
access denials are historical and superseded by the successful operator run.
