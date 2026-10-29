# C6.1 security hardening

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

## Controls and assumptions

Production Gunicorn binds only /run/codeventra/gunicorn.sock. Web no longer joins the proxy network. Its default image TCP command remains for local development; active compose.yaml is unchanged. EXPOSE metadata does not start a listener.

The dedicated socket volume is mounted only into web (read/write) and Nginx (read-only). Image directory ownership is 10001:10002, mode 2750. Gunicorn uses umask 0117 for socket mode 0660. Web runs as 10001:10002 with capabilities dropped, read-only root and writable /tmp. Docker fresh-volume metadata initialization passed in the isolated Linux run; existing target volumes still need verification; do not repair or reuse an existing volume blindly. Upload ownership remains compatible with UID 10001.

The custom Nginx Dockerfile configures workers to use group 10002 through the main-context nginx.conf user directive. Build it separately and supply an approved immutable NGINX_IMAGE digest. The stock root master startup model remains for TLS/listeners. Nginx workers have group access to connect but no directory write permission.

Gunicorn's Linux post_worker_init hook checks production settings, Django checks, actual listener family/path, directory ownership/mode, socket type/ownership/mode and disabled Gunicorn scheme headers. Only after these checks does it inject the non-HTTP WSGI key codeventra.private_socket=True. Production middleware rejects unmarked requests before SecurityMiddleware. Empty REMOTE_ADDR and trusted IP addresses do not establish production identity. HTTP headers cannot populate that internal key. Existing visitor IP validation still rejects invalid values and chains and supports IPv4/IPv6.

Nginx overwrites protocol with its connection scheme and visitor headers with its peer address. Gunicorn secure_scheme_headers is empty because Unix connections bypass forwarded_allow_ips filtering. Django's exact SSL proxy tuple requires explicit production Unix settings plus the request marker gate. Production checks require transport middleware first, HTTPS enabled, indexing disabled and HSTS disabled. Local HTTPS-disabled defaults remain unchanged.

The host, Docker administrator, web and Nginx processes are trusted. A compromised authorized socket client can forge headers. Database/Redis peers receive neither the socket mount nor a Gunicorn TCP endpoint. Host root or deliberately sharing the socket with another container defeats this boundary. Permissions authenticate channel access, not individual Nginx processes.

References: [Gunicorn 23 settings](https://docs.gunicorn.org/en/23.0.0/settings.html), [Django proxy SSL requirements](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header).


See `c6-1-harness-review.md` for operator isolation and recovery instructions.
