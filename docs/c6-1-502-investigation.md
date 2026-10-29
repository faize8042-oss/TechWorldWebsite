# C6.1 Unix socket 502 investigation

Investigated run: `codeventra-c61-validation-478feda61ac943078d2a735f4bb94097`.
That earlier investigation used static inspection and offline checks; its pending
status is superseded by the successful Linux run documented below.

## Findings

The saved production Compose render gives both web and Nginx the logical volume
`gunicorn_socket`, named `<run>_gunicorn_socket`, at `/run/codeventra`. Web has
write access; Nginx has read-only access. The harness replaces Nginx's mounts
but preserves that source, target and read-only flag. The final isolated Compose
render was not saved in this run, nor were actual container mounts.

Gunicorn binds `unix:/run/codeventra/gunicorn.sock`; the Nginx upstream uses the
same path. Runtime log lines 66–71 show Gunicorn 23 starting two workers and
serving the readiness request with HTTP 200. The production worker hook verifies
directory ownership/mode `10001:10002/2750` and socket `10001:10002/0660`.
The application Dockerfile provisions that directory, and the Nginx Dockerfile
sets the worker group to 10002. No worker shutdown/restart is logged.

Nginx repeatedly reports errno 2 (`ENOENT`), rather than errno 13 (`EACCES`).
This establishes a missing path in the consumer namespace at connection time,
but does not establish which component is missing or why. Read-only mounting
does not itself prevent connecting to a Unix socket; it prevents filesystem
modification. There is no evidence supporting weaker permissions or TCP exposure.

The leading hypothesis is a mount alias collision: Nginx has a tmpfs at
`/var/run` as well as a socket volume under `/run`. If `/var/run` resolves to
`/run` in the built image, mount ordering could hide the socket volume. The
saved build log identifies the base image but does not show its symlink layout
or effective mount namespace. This is **not a confirmed root cause**. Socket
unlinking after readiness is also not excluded by the saved logs alone.

Database and Redis health probes pass; web and Nginx have null health diagnostics.
Compose's startup messages saying “Healthy” do not prove Nginx proxy readiness.
Cleanup verification records no remaining owned containers, networks, volumes
or images.

## Correction and runtime resolution

The production template and isolated replay now use `/run/nginx` for the PID
tmpfs and `/run/nginx/nginx.pid` for Nginx's PID file. Neither `/run` nor its
`/var/run` alias is covered by runtime tmpfs. The read-only socket volume stays
at `/run/codeventra`. No permission relaxation or TCP fallback was introduced.
The earlier suggestion to use canonical `/run` as the tmpfs target is withdrawn:
a parent mount can mask the nested socket and must be rejected.

Offline regressions reject mismatched socket topology and covering tmpfs aliases.
The harness retains final synthetic replay, mounts and namespace metadata, and
checks consumer socket visibility before TLS retries. The successful run verified
socket metadata and proxy traffic, resolving the observed 502 validation blocker.
The precise cause of the earlier failure remains unproven because that run did
not retain effective mount/inode evidence. Restart and stale-socket scenarios
remain separate unimplemented integration tests.

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
