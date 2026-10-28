# Phase C5 pre-deployment validation

**Scope:** local review of the Phase C4 production proposal, including production Compose and Nginx templates, Django production checks, proxy trust, data isolation, private attachment handling, backup guidance, and local regression/HTTP checks. No production deployment, service start, database migration, backup, restore, domain/DNS setup, or SEO activation was performed. This is not an assertion that production is ready.

**Verification date:** 2026-10-28 (local validation recorded below).

## Initial repository state

- Branch: `feature/codeventra-ui`.
- Starting commit: `8a2211f9d711fa4d63a97ec101d9a76d871f74e6`.
- Working tree: clean before this phase.
- Phase C4 deployment proposal and local safeguards are present.

## Current Git baseline

- Verified on 2026-10-28 before this report update: branch `feature/codeventra-ui`, commit `0b9c6d650bccbd3c1ce90bc510d7b275a21d32cc` (`docs: detail production Compose findings`).
- The working tree is not clean: `contact/tests.py` has an unstaged private-storage regression test that currently fails pending an approved storage implementation change. It was not included in the report commit.

## Production Compose findings

- `docker compose -f deploy/compose.production.yaml config --quiet` **passed** with harmless placeholder values supplied from temporary files outside the repository. This validates Compose rendering only; no production service, network, or volume was started or created. The template is not deployable as supplied because its image, host/certificate, secret, and connection values still require real reviewed deployment inputs.
- The four services are `db`, `redis`, `web`, and `nginx`. Web waits for healthy PostgreSQL and Redis; Nginx has only a start-order dependency on web, with no web readiness health check. PostgreSQL and Redis have health checks; web and Nginx do not.
- Only Nginx publishes host ports 80 and 443. Gunicorn port 8000 is exposed within Compose networks and PostgreSQL/Redis publish no ports. The `data` network is internal; the `proxy` bridge uses a fixed subnet and Nginx address. Web is attached to both networks, so database-network peers can reach Gunicorn over `data`; Compose does not apply directional peer filtering.
- PostgreSQL, private uploads, and public media use persistent named volumes. Nginx receives only the public-media volume, read-only; private uploads are not mounted into Nginx. Redis is deliberately non-persistent, memory-limited to 128 MB, and configured with `allkeys-lru`, so cached/rate-limit state is disposable.
- Services use `unless-stopped`, `no-new-privileges`, and read-only root filesystems for web/Nginx. There are no privileged containers, added Linux capabilities, Docker socket mounts, or hardcoded credentials. Web’s filesystem and volume ownership still need a disposable deployment rehearsal. The template does not specify CPU/memory resource limits.
- The application image must be supplied as an immutable digest. PostgreSQL, Redis, and Nginx use version tags, not digests. The PostgreSQL health check uses its configured role, and Redis checks authenticated `PING`; Redis password interpolation also places the password in the server process arguments. Keep Compose rendering output private because interpolated values may be sensitive.
- The template has no automatic migration command or migration service, which avoids uncontrolled startup migrations. The web database URL uses `POSTGRES_USER`, which the official PostgreSQL image initializes as a superuser; create and configure a separate least-privilege runtime role before deployment. Compose CLI interpolation inputs must be supplied separately from web’s service-level `env_file`.
- Static DNS resolution for the Nginx upstream may become stale after web-container replacement. HTTPS enablement in Compose also conflicts with Django’s currently unset trusted-proxy header and can cause redirect loops. These are deployment blockers requiring approved template/application changes before activation.

## Nginx findings

- Static review found upstream and server-block syntax that passed the isolated syntax test, explicit TLS 1.2/1.3, a 6 MB body limit, bounded proxy timeouts, and header assignments that overwrite client-supplied `Host`, `X-Forwarded-Proto`, `X-Forwarded-For`, and related forwarding headers. Nginx proxies application requests to `web:8000`; Gunicorn has no published host port.
- The HTTP server currently redirects using `https://$host$request_uri`; an unrecognized Host can influence the redirect destination. Replace this with a canonical, validated host policy before exposure.
- The file combines an HTTP-to-HTTPS redirect with a TLS server whose hostname and certificate paths are placeholders. As supplied, it cannot provide HTTP-only certificate bootstrap and cannot start successfully until the referenced certificate exists. Bootstrap should use a separately validated HTTP-only config; obtain a real certificate only after domain/DNS control is confirmed, validate the TLS config, then activate HTTPS and verify it externally before enabling the redirect.
- The media alias serves only `/srv/media/`, which Compose mounts from the public-media volume read-only. `autoindex off`, `try_files`, and deny rules cover dotfiles, `.env`, `.git`, and private-upload path names. Private attachment storage is not mounted into Nginx; no private attachment URLs should be generated by Django.
- Isolated `nginx -t` **passed** against local image digest `sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5` using a disposable synthetic certificate on Docker's `none` network. This is syntax-only; the production-pinned Nginx image, live certificate, TLS negotiation, Docker DNS refresh, routing, and response-header behavior were not runtime-tested. The active local Nginx was not restarted or modified.
- Django must not trust forwarded HTTPS until direct untrusted access to Gunicorn is prevented and the intended Nginx path is verified. Set Django proxy trust only after that boundary is established and the proxy is confirmed to overwrite the protocol header. Keep HSTS disabled during bootstrap; enable it only after HTTPS and all relevant hostnames are verified, and leave preload disabled unless separately approved.

## Architecture review

- Production topology is isolated in `deploy/compose.production.yaml`; local `compose.yaml` is development configuration and remains untouched.
- PostgreSQL and Redis are attached only to the Compose `data` network, which is marked internal. Neither publishes a host port. Only Nginx publishes 80/443; Gunicorn is exposed to the Compose proxy network only.
- Web also joins the proxy network, so it can reach Nginx peers and has a network path with egress through that bridge. The database network itself is internal. Review egress restrictions if the threat model requires web-only SMTP egress.
- Compose interpolation values such as `POSTGRES_PASSWORD`, `DATABASE_URL`, `REDIS_URL`, and `APP_IMAGE` must be supplied to the Compose CLI environment (for example, with its `--env-file` option). The service-level `env_file` injects variables into the web container; it does not supply Compose interpolation values. Treat rendered Compose output as secret-bearing and do not save, publish, or paste it into logs.
- The app image is required as an immutable digest. PostgreSQL, Redis, and Nginx use pinned version tags but not digests; pin reviewed digests before deployment and define an image update process.
- The app has a read-only root filesystem, a non-root image user, and persistent volumes for private uploads/public media. Verify volume ownership with a disposable rehearsal. Nginx mounts only public media read-only; private attachments are not mounted into Nginx.
- Redis is authenticated, memory-bounded, and non-persistent with `allkeys-lru`. It is appropriate only while cache and rate-limit state are disposable; verify eviction behavior before launch.
- The web service uses `POSTGRES_USER` in `DATABASE_URL`. The PostgreSQL official image creates that role as a superuser; use a separate least-privilege runtime role before deployment.
- Web also joins the internal data network, so PostgreSQL and Redis peers can reach Gunicorn. No host port is published, but Compose does not provide directional peer filtering.
- The HTTP redirect reflects `$host`, allowing an unknown host to influence its destination. The Nginx upstream uses static DNS resolution and may need reload after web-container replacement.
- Redis expands its password into the `redis-server --requirepass` process argument as well as receiving it through the environment.
- No resource limits, host firewall, backup jobs, monitoring, certificate issuance/renewal, or recovery rehearsal are implemented by this template.

## Django and proxy review

- Production-only checks require a long secret, `DEBUG=False`, confirmed hosts, HTTPS CSRF origins, PostgreSQL, SMTP credentials, and explicit HTTPS enablement. They do not connect to those services.
- Redirects and secure cookies require `ENABLE_HTTPS=True`; HSTS defaults to zero. `SECURE_PROXY_SSL_HEADER` is unset while production Compose forces `ENABLE_HTTPS=True`. Behind TLS-terminating Nginx, this can cause redirect loops. Resolve the proxy trust and network boundary before activation. Active settings were not changed.
- Nginx overwrites `Host`, forwarded protocol, and client IP headers. The configured static proxy address matches Django's trusted proxy IP. Validate the address does not conflict with the target host networks.
- TLS certificate paths and hostnames are placeholders. The template is not deployable as supplied. Obtain and validate a certificate, review renewal, then validate Nginx before activation. Keep public SEO indexing disabled.

## Data protection and recovery review

- Contact attachments use a separate private storage root and the production Compose template mounts its private volume only into web. Nginx mounts public media only. A behavior-based test found that the storage backend can still generate a `/media/` URL; the production volume separation prevents Nginx from directly serving that private volume, but storage URL generation should be disabled. The focused test is pending a storage-code fix. No real attachments were read or changed.
- PostgreSQL has a persistent named volume and no published port. Redis has no published port. Production data does not exist in this local validation.
- Backup guidance now documents unique non-overwriting runs, archive validation before completion, role/grant recreation, paired database/upload recovery points, and file verification in an isolated restore. Backup storage, encryption/key recovery, alerting, and actual restore rehearsal remain unimplemented. No backup or restore was performed. Proposed RPO/RTO are planning values only, not measured guarantees.
- Do not put a password in a database URI passed on the `pg_dump` command line. Use a protected `PGPASSFILE` and non-secret connection parameters, then encrypt and transfer the resulting dump using the approved backup process.

## Validation record

Placeholder-only Compose rendering is a syntax/configuration check, not evidence that images, credentials, networks, or runtime behavior are production-ready.

- Production Compose config validation: **passed** with `docker compose config --quiet`, explicit placeholder-only environment files under system temp, and no services started. No real credentials were used.
- Production Nginx syntax validation: **passed** using local image digest `sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5` on Docker's `none` network. A synthetic self-signed certificate was generated inside a disposable offline helper container and removed after `nginx -t`. This is syntax-only and does not validate the production-pinned `nginx:1.28.1-alpine`, real certificate, TLS, DNS, or proxy behavior.
- `python manage.py check`: **passed**, no issues. `check --deploy` completed with five local warnings: HSTS unset, SSL redirect off, secure session cookie off, secure CSRF cookie off, and `DEBUG=True`.
- Last full Django suite: **49 passed** before focused test additions. It created and removed a temporary test database through the local PostgreSQL service. No full-suite rerun followed the user's instruction not to execute migrations.
- Focused configuration suite: **18 passed** in a disposable network-isolated container with placeholders and `SimpleTestCase` settings overrides. This corresponds to the original 8 config tests plus 10 new tests; expected full-suite count is 59, not fully rerun.
- Focused private-storage behavior test: **failed** as expected because `storage.url()` did not raise `ValueError`. It used a synthetic filename only, no database/migration, and did not open or create an attachment. The test change in `contact/tests.py` is uncommitted; no storage implementation change has been made pending approval.
- Local HTTP GET checks: **passed** for `/`, `/about/`, `/services/`, `/projects/`, `/contact/`, `/privacy/`, `/terms/`, `/sitemap.xml`, `/robots.txt`, and `/health/` (all 200, expected HTML/XML/plain-text content types). Public HTML pages contained `noindex, nofollow`. Health returned only `ok` as `text/plain` and `Cache-Control: no-store`.
- Existing Compose services: **db, web, nginx, and redis were up**; PostgreSQL and Redis reported healthy. No service was recreated. No production container, network, or volume was started or created. Docker build was not run.
- Automated tests added: 10 committed config tests; one additional private-storage test remains uncommitted and currently fails pending the application-code fix.

## Environment and data handling note

No `.env` contents were printed, copied, modified, or mounted. **Correction to earlier assurances:** the initial host-side Django management checks/tests imported `config/settings.py`, which calls `environ.Env.read_env(BASE_DIR / ".env")`; those commands therefore caused Django to read `.env` before the user explicitly prohibited access. Since that prohibition, validation used placeholders and no further `.env` reads or mounts were performed. No real credentials were exposed in output. No customer attachments were opened, copied, moved, or deleted.

## Remaining production gates

Deployment remains blocked by the HTTPS proxy-trust mismatch, PostgreSQL application superuser credentials, Host-reflecting redirect, private-storage URL behavior, unresolved internal Gunicorn peer boundary, and placeholder host/certificate values. Domain/VPS, DNS, production secrets, image digests, SMTP delivery, backup encryption/storage/key recovery, restore rehearsal, retention, monitoring, and explicit deployment approval also remain outstanding. During initial report preparation, the latest prior commit was `ecf0e34a1f8e9a2758fb8b0c1fba1da5ca3b643f`; an uncommitted `contact/tests.py` regression test remains pending the storage fix. Do not deploy, enable indexing, or activate production templates on the basis of this local review.
