# Codeventra Labs production architecture proposal

**Status:** design and isolated templates only. Nothing in this document means the site is deployed. Domain ownership, DNS, hosting account eligibility, infrastructure, SMTP, certificates, and production secrets remain unconfirmed.

## Target topology

```mermaid
flowchart TD
    V[Visitors] --> DNS[Confirmed DNS]
    DNS -->|80 redirect / 443 TLS| N[Nginx reverse proxy]
    N -->|private Compose proxy network| W[Gunicorn / Django]
    W -->|internal data network| P[(PostgreSQL 17)]
    W -->|internal data network| R[(Redis 7 cache)]
    W --> S[SMTP provider]
    W --> U[(Private uploads volume)]
    N --> M[(Public media volume, read only)]
    O[Operator over restricted SSH] --> H[Single VPS host]
    H -. encrypted scheduled copy .-> B[Independent off-server backup]
```

One VPS is a cost-conscious starting point for a low-traffic agency portfolio. It is a single failure domain and provides no high availability. A host, disk, region, account, or operator error can make every service unavailable at once. Keep a migration path to managed PostgreSQL, external object storage, and a second application host/load balancer when uptime, load, or recovery needs justify the added cost.

## Service responsibilities and boundaries

| Service | Responsibility | Exposure and persistence |
| --- | --- | --- |
| Nginx | TLS termination, HTTP redirect, request limits, proxy headers, public media | Only service publishing TCP 80/443. Public media mounted read-only. |
| Gunicorn/Django | Website, admin, contact handling, WhiteNoise static assets | Port 8000 is Compose-only; non-root image; read-only root filesystem; persistent private uploads. |
| PostgreSQL | Primary application data | `data` network only; persistent named volume; no host port. Strong unique credentials. |
| Redis | Rate-limit/cache data | `data` network only; no host port; authentication and memory cap. Cache is disposable; persistence disabled. |
| SMTP | Contact email delivery | Outbound from web only; provider TLS/auth settings and delivery must be verified. |

The proposed Compose file separates an `internal: true` data network from the Nginx-facing proxy network. PostgreSQL and Redis are only on the internal network. Gunicorn has no published host port. Nginx alone publishes 80/443. Do not expose the Docker daemon or mount its socket into containers. Compose is not a substitute for a host/provider firewall: permit inbound 80/443 and SSH (22 or a deliberately changed port), restrict SSH source addresses where practical, and deny other inbound ports. Do not apply firewall changes in this phase.

The production proxy network pins Nginx to `172.20.0.10`, matching the existing trusted proxy IP in Django middleware. Check for host/network conflicts before deployment. Django proxy protocol trust remains unset in current settings; only enable it after confirming that Nginx overwrites `X-Forwarded-Proto` and no untrusted client can reach Gunicorn.

## Isolated production configuration

`deploy/compose.production.yaml` is a proposal; it does not alter local `compose.yaml`. It uses persistent named volumes for Postgres, private uploads, and public media, plus explicit image version tags. Before deployment, resolve reviewed image tags to immutable digests and maintain an image update process. Pass configuration from a protected, host-side environment file, never Git. Compose interpolation values must be supplied to the Compose CLI (for example, `docker compose --env-file /etc/codeventra/production.env -f deploy/compose.production.yaml config`); the service `env_file` only injects values into the web container. Compose interpolation may expose resolved secrets in rendered configuration output; only authorized operators should handle that output, and it must not be logged or shared.

The app image must be supplied as an approved immutable registry digest through `APP_IMAGE`. PostgreSQL and Redis use explicitly versioned image tags as a starting pin and should also be digest-pinned by the release owner after reviewing the official images and update policy. Avoid `latest`, `stable`, and other floating tags in a release record.

Migrations are deliberately not in the container start command. For each release, an operator reviews the migration plan and backup state, then runs the approved migration as a controlled one-off operation. Application restarts do not run migrations. Migrations that require an incompatible schema transition need an expand/contract release plan.

The application image creates `/app/private_uploads` and `/app/media` for UID 10001 before switching to its non-root user. New named volumes are initialized from those image directories by Docker's volume-copy behavior. Confirm ownership and writable access with a disposable deployment rehearsal before production; do not recursively change ownership on live data without a reviewed recovery plan. Nginx mounts only public media read-only. It never mounts the private attachment volume. WhiteNoise serves static files from the image.

Redis is a bounded, authenticated, no-persistence cache (`allkeys-lru`). Confirm that current application behavior treats the Redis contents as disposable and that rate limiting still works under eviction before launch. If Redis later stores queues, sessions, or other durable work, redesign persistence and eviction before using it for that purpose.

## DNS, HTTPS, and proxy rollout

Certificate file paths in `deploy/nginx/production.conf.example` are placeholders. The template is not loadable as-is and must not be activated before a valid certificate and real hostnames exist. Start with a separate reviewed HTTP-only bootstrap configuration to verify reachability and obtain the certificate; then install the TLS server and redirect configuration. Select and test an ACME challenge method and renewal automation; do not assume the example provisions certificates.

There is also a confirmed HTTPS activation mismatch: production Compose sets `ENABLE_HTTPS=True`, which enables Django SSL redirects, while current Django settings leave `SECURE_PROXY_SSL_HEADER=None`. Since Nginx terminates TLS and forwards HTTP to Gunicorn, do not activate this Compose template until the trusted-proxy setting has been approved, implemented, and verified. The HTTP redirect also uses the request `$host`; reject unknown hosts or use a fixed canonical redirect target before enabling it.

Exact safe order:

1. Confirm domain control, canonical hostnames, approved hosting, DNS ownership, and the target host's firewall and network routes. Check that the production Docker subnet does not conflict with host or existing Docker networks.
2. Establish the Gunicorn trust boundary. Confirm there is no host-published Gunicorn port and identify every container/network peer that can reach web; the current web service also joins the data network. Restrict or explicitly trust those peers before Django trusts forwarded protocol headers.
3. Obtain a valid certificate using a selected DNS challenge, or use a separate reviewed HTTP-only bootstrap configuration. The production Nginx template is not a bootstrap file: it requires certificate files and redirects HTTP to HTTPS.
4. Configure certificate renewal and rehearse it. Replace Nginx host and certificate placeholders, and confirm the certificate covers every configured hostname.
5. Reject unknown HTTP hosts or change the redirect to a fixed confirmed canonical hostname. Validate the final Nginx configuration with the exact pinned image and certificate paths.
6. Prepare protected production values and an approved immutable application image. Confirm `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, database credentials/URL, Redis password/URL, and SMTP settings agree. Validate Compose interpolation without printing or storing resolved secrets.
7. Verify Nginx overwrites `X-Forwarded-Proto` from `$scheme` and client-IP headers from the connection, then verify untrusted clients cannot reach Gunicorn through any host or container path.
8. After steps 2 and 7 pass, approve and configure Django `SECURE_PROXY_SSL_HEADER` for the exact overwritten header. Test through the proxy that Django recognizes HTTPS while `ENABLE_HTTPS=False`; the current settings do not yet provide this trust.
9. Only after the HTTPS proxy test passes, set `ENABLE_HTTPS=True`. In the current production Compose template this value is hard-coded, so all preceding gates and an appropriate staging/override validation must be complete before starting it. Then verify HTTPS, HTTP redirect, secure cookies, CSRF behavior, and unknown-host rejection.
10. After stable HTTPS operation, consider HSTS with an approved short duration. Keep subdomain and preload flags off until every subdomain and policy requirement has been reviewed. Never enable preload automatically.
11. Keep SEO indexing disabled until the separate domain, content, and launch approval gates are complete.

The Nginx template overwrites `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, and `X-Forwarded-Port`. Body size is limited to 6 MiB, matching the existing application upload cap plus multipart overhead. Nginx denies dotfiles and environment/Git/private-upload paths and disables directory listing. Public media is intentionally served from its separate read-only volume. No private attachments or `.env` path is mounted there.

## Django production settings plan

The existing Phase C3 `DEPLOYMENT_MODE` controls production-only, network-free Django checks. Keep local defaults unchanged. In a future approved deployment, provide:

| Setting | Production plan |
| --- | --- |
| `DEPLOYMENT_MODE` | `production`; enables deployment checks. |
| `DEBUG` | `False`, explicitly. |
| `SECRET_KEY` | Unique random secret, at least 50 characters under existing checks; store in protected host configuration. |
| `ALLOWED_HOSTS` | Exact confirmed public hostnames only; no wildcard or localhost. |
| `CSRF_TRUSTED_ORIGINS` | Exact HTTPS origins, each hostname also in `ALLOWED_HOSTS`. |
| `ENABLE_HTTPS` | `True` only after certificate, proxy, and direct Gunicorn isolation are verified. This enables redirects and secure cookies in current code. |
| `SECURE_SSL_REDIRECT`, secure cookies | Derived by current settings from `DEBUG=False` and `ENABLE_HTTPS=True`; confirm at rollout. |
| `SECURE_PROXY_SSL_HEADER` | Currently `None`. Configure only after verifying the trusted Nginx overwrite and network boundary. |
| `USE_X_FORWARDED_HOST` | Leave false; Nginx supplies the canonical `Host`. |
| HSTS | Current `HSTS_SECONDS` default is zero, with subdomains/preload false. Introduce gradually after stable HTTPS. |
| Referrer and security headers | Current strict-origin-when-cross-origin, nosniff, and `X_FRAME_OPTIONS=DENY` protections remain. Review deploy-check results. |
| Database | PostgreSQL URL to the private service with strong unique credentials and TLS only if the service boundary requires it. |
| Redis | Authenticated URL to private Redis; do not publish its port. |
| SMTP | Verified provider host, port, TLS mode, sender authorization, and protected credentials. |
| Static files | Build-time `collectstatic`; serve versioned manifest assets using WhiteNoise in the immutable app image. |
| Private uploads | Persistent private volume at `/app/private_uploads`; never a public URL or Nginx mount. Back up encrypted. |
| `SEO_SITE_URL` | Set only to the verified HTTPS origin after domain control and public routing work. |
| `SEO_INDEXING_ENABLED` | Keep false until separate launch approval. |

No settings change was made during this design phase. Local defaults still leave proxy trust and HTTPS redirects/cookies disabled, HSTS at zero, and SEO indexing off. Before production activation, the HTTPS proxy-trust mismatch described above requires an approved settings change and validation with protected deployment values; do not print resolved secrets or enable production mode locally.

## Database, backup, and recovery

PostgreSQL uses a persistent named volume and only the internal network. Restrict administrative access to an authorized operator through a protected local socket/tunnel or one-off maintenance container; never add a public database port. Back up with scheduled logical custom-format `pg_dump`, encrypted before leaving the host, and copy it to independent off-server storage. Back up private uploads separately and encrypt them too. Do not export contact submissions for development or routine QA.

Provider backups/snapshots are useful for fast whole-server recovery, but remain a separate protection from independent logical and file backups. A snapshot alone is not a complete backup strategy. Define a retention schedule (initial proposal: daily logical backups retained 14 days, weekly retained 8 weeks, monthly retained 6 months, subject to privacy and storage review); restrict access and key recovery. Verify each backup's integrity and rehearse restoration periodically into an isolated disposable environment with no route to production. A backup is not proven reliable until a restore rehearsal succeeds.

Proposed initial targets, subject to business approval and rehearsal: **RPO 24 hours** for database and private uploads; **RTO 8 hours** for rebuilding the single VPS and restoring service. These are planning targets, not measured guarantees. Restore the approved image/config, restore database and files, apply only reviewed schema steps, verify health and privacy controls, then switch DNS or service routing if needed. Preserve the original volumes until recovery has been accepted. Keep encryption keys, database/SMTP/app secrets, DNS access, image registry access, and certificate renewal access recoverable by designated operators using a separate protected mechanism.

## Release, health, logging, and rollback

No automatic production deployment is proposed. Use reviewed Git changes, CI/test results, a versioned immutable image, and a manual approval checkpoint. Release sequence:

1. Verify the Django test suite and system checks.
2. Build and identify a versioned image; record its digest.
3. Securely transfer or pull the approved image.
4. Verify recent database and upload backups are readable and off-server.
5. Review migration SQL/plan and compatibility with the running image.
6. Obtain explicit deployment approval.
7. Apply only approved migrations in a controlled one-off command.
8. Start/update the application and proxy containers without resetting volumes.
9. Verify `/health/`, TLS, public endpoints, and logs.
10. Verify a controlled SMTP delivery and private attachment access control without exposing real submissions.
11. Monitor resource use, disk space, HTTP errors, restarts, certificate expiry, SMTP failures, and backup job outcomes.
12. Roll back the image/config if necessary, while assessing schema compatibility separately.

The existing `/health/` is a minimal liveness check; it does not prove database/Redis readiness. Use container health checks and separately observed endpoint checks. Send container logs to stderr/stdout and retain them using a bounded host log policy. Avoid logging contact body, attachment data, credentials, or full request headers. Set alerts for disk usage, memory pressure, restarts, certificate expiry, backup failure, and unexpected public 5xx responses. No monitoring service is selected or priced yet.

Keep the last known-good image and config available. Rolling an image back does not necessarily reverse a database migration. Prefer backward-compatible expand/contract migrations; if a migration is irreversible, the release needs a tested forward-fix or restore plan before approval. Never restore a backup over production as an ad hoc rollback.

## Risks, assumptions, and approval checkpoints

- Domain, ownership, DNS, hosting account eligibility, regional availability, and actual checkout price are unconfirmed.
- One VPS is a single failure domain; no high availability or guaranteed recovery has been demonstrated.
- Capacity estimate assumes a low-traffic portfolio. Monitor memory, CPU, disk, database growth, and upload size before scaling down or up.
- TLS renewal, firewall rules, SSH access policy, backup provider, independent storage, SMTP provider, monitoring, taxes, and retention need owners and implementation plans.
- No backup, restore rehearsal, external endpoint, public email delivery, or production runtime behavior has been verified in this phase.
- Before production: approve domain/provider/cost, secrets and access owners, exact immutable image digests, firewall, certificate/renewal plan, backup storage and retention, RPO/RTO, migration plan, SMTP verification, and SEO activation separately.

## Official planning references

Prices and product availability were checked on 2026-10-28 and are provisional; recheck the provider checkout immediately before purchase. See [hosting cost plan](hosting-cost-plan.md).

- Hetzner Cloud plan details and availability: https://www.hetzner.com/cloud/cost-optimized/
- Hetzner Cloud price adjustment (effective 2026-06-15): https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
- Hetzner IPv4 prices: https://docs.hetzner.com/general/infrastructure-and-availability/ipv4-pricing/
- Hetzner backup and traffic billing: https://docs.hetzner.com/cloud/billing/faq/
- DigitalOcean Droplet pricing: https://www.digitalocean.com/pricing/droplets
