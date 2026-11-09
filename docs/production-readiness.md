# Production deployment readiness

This is a preparation guide. The application has not been deployed, the planned domain and DNS are unverified, and HTTPS has not been configured.

See the proposed [deployment architecture](deployment-architecture.md), [hosting cost plan](hosting-cost-plan.md), and [launch checklist](launch-checklist.md) for the isolated production design. These are planning artifacts only; no production behavior has been verified.

The Phase C5 local audit and its current verification record are in [pre-deployment validation](pre-deployment-validation.md). A successful local syntax or settings check does not verify a live deployment.

## Current architecture

Docker Compose runs Django 5.2 under Gunicorn, PostgreSQL 17, Redis 7, and Nginx. WhiteNoise serves collected static assets. Nginx currently listens on HTTP and proxies to Gunicorn; it mounts only the public `media` directory. Contact attachments use `/app/private_uploads`, outside the public media mount. Compose currently supplies local development settings and is not a production deployment configuration.

## Completed safeguards

- `DEPLOYMENT_MODE` defaults to `development`; production-only system checks run when explicitly set to `production`.
- Production checks validate secret strength, confirmed hosts, HTTPS CSRF origins, PostgreSQL, SMTP credentials, and explicit HTTPS enablement without contacting services.
- HTTPS redirect and secure cookies remain disabled in local development. HSTS remains zero unless explicitly configured with HTTPS; subdomain and preload flags remain false.
- Development leaves forwarded protocol headers untrusted. C6.1 production uses the validated private Unix socket marker and exact proxy SSL tuple; Nginx must overwrite forwarded headers.
- Runtime logs go to container stderr. Contact email failure logs include only the submission ID and exception class, not message contents or exception text.
- `/health/` returns only `ok` with `text/plain` and `Cache-Control: no-store`. It is a liveness check and does not test database or Redis readiness.
- SEO indexing remains disabled by default. The health endpoint is not included in the sitemap.

## Required production environment

The production template now follows the [C6.2.1 credential isolation contract](c6-2-1-postgresql-hardening.md).
Use its dedicated runtime JSON secret mount and administrator/migration/backup
separation; do not pass a shared environment file to web. Runtime application
values below belong in the allowlisted JSON, while deployment gates are explicit
Compose environment entries. These are proposed inputs, not deployment approval. Set:

- `DEPLOYMENT_MODE=production` and `DEBUG=False`.
- `SECRET_KEY` to a unique, randomly generated secret of at least 50 characters.
- `ALLOWED_HOSTS` to only hostnames confirmed for the deployment.
- `CSRF_TRUSTED_ORIGINS` to the corresponding verified HTTPS origins (scheme included).
- `DATABASE_URL` in runtime JSON to the dedicated `cv_runtime` PostgreSQL connection; never the initialization administrator or migration login.
- `CONTACT_EMAIL`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, and `EMAIL_HOST_PASSWORD` to verified SMTP values. Keep TLS/SSL mode consistent with the provider.
- `ENABLE_HTTPS=True` only after HTTPS termination and forwarded request behavior are verified.
- Keep `SEO_INDEXING_ENABLED=False` and `SEO_SITE_URL` empty until the public HTTPS origin, domain control, and launch approval are confirmed.
- Keep `ANALYTICS_HMAC_SECRET` unique and protected. `REDIS_URL` must target the private deployment Redis service.

Validate configuration without connecting to external services:

```sh
DEPLOYMENT_MODE=production python manage.py check
DEPLOYMENT_MODE=production python manage.py check --deploy
```

The production checks intentionally fail until production values are supplied. Django's deploy check can also report hardening recommendations (including HSTS) that require rollout decisions after HTTPS is live; do not suppress them blindly. Start HSTS at a short duration after HTTPS verification, increase gradually, and keep `includeSubDomains` and `preload` off unless every subdomain and policy requirement has been verified.

## HTTPS and reverse proxy prerequisites

Use this order for production HTTPS; do not skip gates:

1. Confirm domain ownership, canonical hostnames, DNS, host firewall, and non-conflicting Docker networks.
2. Verify the C6.1 Gunicorn Unix socket boundary: only web and Nginx mount the socket, database/Redis have no socket mount, and Gunicorn has no TCP listener. Verify socket ownership and proxy marker checks.
3. Obtain a valid certificate through the selected DNS challenge or a separately reviewed HTTP-only bootstrap configuration. The production Nginx template itself requires certificate files and redirects HTTP to HTTPS, so it cannot bootstrap TLS as supplied.
4. Configure and rehearse certificate renewal, replace hostname/certificate placeholders, and configure unknown-host rejection or a fixed canonical redirect target.
5. Validate the finalized Nginx config with the exact pinned image and real deployment paths. Confirm Nginx overwrites `X-Forwarded-Proto` and client-IP headers from the connection.
6. Confirm `ALLOWED_HOSTS` and HTTPS `CSRF_TRUSTED_ORIGINS` exactly match verified hostnames; confirm service URLs and credentials are consistent without printing secrets.
7. After the proxy behavior and access boundary are verified, approve and configure Django `SECURE_PROXY_SSL_HEADER` for the exact Nginx header. Test through the proxy that Django recognizes HTTPS while SSL redirect is still disabled.
8. Only after that test passes, enable `ENABLE_HTTPS=True` and verify HTTPS requests, HTTP-to-HTTPS redirects, secure cookies, CSRF behavior, and unknown-host rejection. The current production Compose template hard-codes this setting to `True`, so do not start it until all earlier gates pass or a reviewed staging override has been used.
9. Add HSTS gradually after stable HTTPS. Keep `includeSubDomains` and `preload` off until every subdomain and policy requirement has been separately reviewed.

Never trust client-supplied forwarded headers as proof of TLS. C6.1 production enables the proxy SSL tuple only with the Unix transport and marker boundary; development keeps it None. Production Compose forces ENABLE_HTTPS=True, so verify the complete C6.1 boundary and TLS before activation. No certificate or DNS changes are included in this preparation phase.

## PostgreSQL backup and restore rehearsal

Use `pg_dump` in custom format over a protected connection, writing directly to encrypted storage outside the repository and application host. Avoid shell history, process listings, or logs containing passwords; prefer a protected `PGPASSFILE`/secret injection mechanism. Example after substituting secret-managed connection parameters:

```sh
# Set PGPASSFILE to a protected, mode-0600 file with the database password.
# Supply non-secret connection fields as a libpq keyword string; do not put
# the password in a URI or command argument.
set -eu
umask 077
RUN_ID=YYYYMMDDTHHMMSSZ-UNIQUE_ID
mkdir -m 0700 "/secure-backup/$RUN_ID"  # Fails if this run directory already exists.
pg_dump --format=custom --no-owner --no-acl --file="/secure-backup/$RUN_ID/database.dump.partial" --dbname="host=DB_HOST port=5432 dbname=DB_NAME user=BACKUP_USER sslmode=verify-full"
pg_restore --list "/secure-backup/$RUN_ID/database.dump.partial"
mv "/secure-backup/$RUN_ID/database.dump.partial" "/secure-backup/$RUN_ID/database.dump"
```

Restrict backup access, encrypt in transit and at rest, and define retention based on business recovery objectives, legal/privacy obligations, and available storage. Keep backups separate from the production host and test restore access regularly. Integrity checks should include successful `pg_dump`, `pg_restore --list`, and periodic restore rehearsals.

The example run ID is a placeholder; generate a unique UTC value for each run. Write only to access-controlled encrypted storage. The new run directory prevents a repeated identifier from silently overwriting an earlier archive, and the final rename marks completion only after the dump and archive listing succeed. Record and protect a checksum separately from the archive; monitor failures and alert an owner. The storage provider, encryption mechanism, key custody/recovery, retention enforcement, and alerting are not selected or implemented.

The command uses `--no-owner --no-acl`; `pg_dump` also omits cluster-wide roles and tablespaces. Before restore, recreate the required database, least-privilege application/migration roles, ownership, and grants from reviewed provisioning instructions. Keep role passwords in secret management, not in backup scripts or SQL exports. The C6.2.1 production proposal separates initialization, ownership, migration, runtime and backup roles; actual database privileges and existing ownership adoption remain unvalidated. Follow its scoped backup and restore limitations.

For a rehearsal, provision an isolated, disposable PostgreSQL instance with no production network route and a separate database name. Restore the candidate dump there using a dedicated rehearsal credential, run schema/application smoke checks, confirm expected record counts without exporting personal data, then securely delete the isolated instance and its files. Restore the paired private-upload backup to an isolated storage target too; confirm files referenced by restored records exist and compare a protected file manifest/checksum. Coordinate the database snapshot and upload snapshot (or pause writes) and record them as one recovery point so records do not refer to missing files. Never point restore commands at production or an existing live database. This phase performs no backup or restore.

## SMTP, attachments, and static assets

- Verify SMTP connectivity, TLS mode, sender authorization, delivery, and failure handling using a controlled test mailbox before accepting public enquiries.
- Persist `private_uploads` on access-controlled storage that is not served by Nginx or exposed through a public URL. Verify Django Admin authorization before downloads. Keep backups of private files encrypted and access restricted.
- Run `python manage.py collectstatic --noinput` during image/build preparation and verify versioned static assets load through WhiteNoise in the deployed image.
- Preserve upload validation and ensure Nginx continues to expose only intentionally public media. Do not mount private uploads into a public server path.

## SEO activation prerequisites

Keep `SEO_INDEXING_ENABLED=False` until the confirmed public HTTPS origin is live, canonical URLs and robots output are checked, published project visibility is reviewed, and launch approval is given. Then set `SEO_SITE_URL` to that verified origin and explicitly enable indexing. The sitemap contains public pages and published projects only; `/health/` is excluded.

## Rollback and post-deployment verification

Keep the last known-good application image and configuration available for rollback. Roll back application code/configuration as a coordinated release; assess migrations separately before rollback, and preserve database volumes and backups. Define a recovery point and owner before production launch.

Before and after deployment, verify:

1. `python manage.py check` passes and review all `check --deploy` findings.
2. HTTPS, redirects, HSTS policy, secure cookies, and host/CSRF validation behave as intended.
3. `/health/` returns only the minimal liveness response; database readiness is monitored separately by infrastructure.
4. Public pages, custom error pages, sitemap, robots, and noindex behavior are correct.
5. Static assets load, private attachments cannot be fetched publicly, and authorized admin download works.
6. SMTP delivery and failure handling work; logs contain no message body, credentials, or attachment contents.
7. A fresh backup is readable and a restore rehearsal has succeeded in isolation.
8. SEO indexing stays disabled until its separate activation prerequisites and approval are met.

## Pending deployment tasks

- Confirm domain ownership, hostname, DNS, host allowlist, hosting, TLS certificate, and proxy design.
- Create production secrets and service credentials in protected deployment storage.
- Decide private-upload persistence, backup, retention, and recovery objectives.
- Verify SMTP and perform a database restore rehearsal.
- Review Django deploy-check findings and approve a staged HSTS policy.
- Create the production Compose/proxy configuration in the deployment phase; current local Compose and Nginx settings are not production TLS configuration.
- Obtain explicit approval before deployment, public indexing, DNS changes, or live infrastructure changes.
