# Phase C5 pre-deployment validation

**Scope:** local review of the Phase C4 production proposal. This is not a deployment or an assertion that production is ready. The domain, VPS, DNS, production credentials, SMTP, certificates, backups, and live routing do not exist or have not been verified.

## Initial repository state

- Branch: `feature/codeventra-ui`.
- Starting commit: `8a2211f9d711fa4d63a97ec101d9a76d871f74e6`.
- Working tree: clean before this phase.
- Phase C4 deployment proposal and local safeguards are present.

## Architecture review

- Production topology is isolated in `deploy/compose.production.yaml`; local `compose.yaml` is development configuration and remains untouched.
- PostgreSQL and Redis are attached only to the Compose `data` network, which is marked internal. Neither publishes a host port. Only Nginx publishes 80/443; Gunicorn is exposed to the Compose proxy network only.
- Web also joins the proxy network, so it can reach Nginx peers and has a network path with egress through that bridge. The database network itself is internal. Review egress restrictions if the threat model requires web-only SMTP egress.
- Compose interpolation values such as `POSTGRES_PASSWORD`, `DATABASE_URL`, `REDIS_URL`, and `APP_IMAGE` must be supplied to the Compose CLI environment (for example, with its `--env-file` option). The service-level `env_file` injects variables into the web container; it does not supply Compose interpolation values. Treat rendered Compose output as secret-bearing and do not save, publish, or paste it into logs.
- The app image is required as an immutable digest. PostgreSQL, Redis, and Nginx use pinned version tags but not digests; pin reviewed digests before deployment and define an image update process.
- The app has a read-only root filesystem, a non-root image user, and persistent volumes for private uploads/public media. Verify volume ownership with a disposable rehearsal. Nginx mounts only public media read-only; private attachments are not mounted into Nginx.
- Redis is authenticated, memory-bounded, and non-persistent with `allkeys-lru`. It is appropriate only while cache and rate-limit state are disposable; verify eviction behavior before launch.
- No resource limits, host firewall, backup jobs, monitoring, certificate issuance/renewal, or recovery rehearsal are implemented by this template.

## Django and proxy review

- Production-only checks require a long secret, `DEBUG=False`, confirmed hosts, HTTPS CSRF origins, PostgreSQL, SMTP credentials, and explicit HTTPS enablement. They do not connect to those services.
- Redirects and secure cookies require `ENABLE_HTTPS=True`; HSTS defaults to zero. `SECURE_PROXY_SSL_HEADER` is unset. Keep it unset until the proxy overwrite and Gunicorn network boundary are verified. Active settings/application files were not changed.
- Nginx overwrites `Host`, forwarded protocol, and client IP headers. The configured static proxy address matches Django's trusted proxy IP. Validate the address does not conflict with the target host networks.
- TLS certificate paths and hostnames are placeholders. The template is not deployable as supplied. Obtain and validate a certificate, review renewal, then validate Nginx before activation. Keep public SEO indexing disabled.

## Data protection and recovery review

- Contact attachments use a separate private storage root and the production Compose template mounts its private volume only into web. Nginx mounts public media only. Verify authorized admin download behavior in a disposable environment before launch; no real attachments were read or changed.
- PostgreSQL has a persistent named volume and no published port. Redis has no published port. Production data does not exist in this local validation.
- Backup guidance requires encrypted off-host database and private-upload copies plus isolated restore rehearsals. No backup or restore was performed. Proposed RPO/RTO are planning values only, not measured guarantees.
- Do not put a password in a database URI passed on the `pg_dump` command line. Use a protected `PGPASSFILE` and non-secret connection parameters, then encrypt and transfer the resulting dump using the approved backup process.

## Validation record

Placeholder-only Compose rendering is a syntax/configuration check, not evidence that images, credentials, networks, or runtime behavior are production-ready.

- Production Compose config validation: **passed** with `docker compose config --quiet` and placeholder-only values. The Docker CLI warned that it could not read the user's Docker config file; validation still exited successfully. No production services were started.
- Production Nginx syntax validation: **passed** in a disposable `nginx:stable-alpine` container, using a temporary self-signed certificate at the template's placeholder path. This validates syntax only; it does not validate the pinned production image, real certificate, TLS behavior, DNS, or live proxy behavior. The active local Nginx was not restarted or changed.
- `python manage.py check`: **passed**, no issues.
- `python manage.py check --deploy`: **completed with five expected local/deployment warnings**: HSTS unset, SSL redirect off, secure session cookie off, secure CSRF cookie off, and `DEBUG=True`. Checks were not suppressed; local HTTP defaults remain intact.
- Django suite inside the existing web container: **49 passed**, including the expected mocked SMTP failure log; suite result `OK`.
- Local HTTP GET checks: **passed** for `/`, `/about/`, `/services/`, `/projects/`, `/contact/`, `/privacy/`, `/terms/`, `/sitemap.xml`, `/robots.txt`, and `/health/` (all 200, expected HTML/XML/plain-text content types). Public HTML pages contained `noindex, nofollow`. Health returned only `ok` as `text/plain` and `Cache-Control: no-store`.
- Existing Compose services: **db, web, nginx, and redis were up**; Postgres and Redis reported healthy. No service was recreated.
- Docker build: **not run**, because only documentation changed and neither application code nor build inputs changed.
- New automated tests: **none**; documentation-only changes.

## Remaining production gates

Domain purchase/ownership, VPS purchase and eligibility, exact costs, DNS, production secrets, certificate/renewal, host firewall and SSH policy, immutable image digests, SMTP delivery, data-retention decisions, backup storage and restore rehearsal, monitoring, and explicit deployment approval remain outstanding. Do not deploy, enable indexing, or activate the production templates on the basis of this local review.
