# Production launch checklist

This checklist describes future approval gates. It does not indicate that any launch item has been completed.

See the [Phase C5 pre-deployment validation](pre-deployment-validation.md) for the local architecture audit and verification record.

## Ownership and infrastructure

- [ ] Confirm registration and control of the selected domain and canonical hostname(s).
- [ ] Confirm hosting account eligibility, server availability, exact checkout cost, region, tax, IPv4, and backup price against the approved $10–20 budget.
- [ ] Select an independent encrypted backup destination and verify its access/cost.
- [ ] Provision one VPS only after explicit purchase authorization; record its owner and access recovery procedure.
- [ ] Apply a reviewed host/provider firewall: inbound SSH (22 or approved alternate), 80, and 443 only; restrict SSH source addresses where practical. No database, Redis, Gunicorn, or Docker API ports from the public internet.
- [ ] Configure SSH key access through an authorized process and disable password/root login only after tested recovery access exists. This phase does not generate keys or change server settings.
- [ ] Configure DNS and verify public resolution/propagation from relevant networks.

## HTTPS and Django

- [ ] Confirm domain ownership, canonical hostnames, DNS, host firewall, and non-conflicting Docker networks.
- [ ] Confirm Gunicorn has no published host port and identify/restrict every network peer that can reach web, including peers on its data network.
- [ ] Obtain the certificate using a selected DNS challenge or a separate reviewed HTTP-only bootstrap config; the production Nginx template requires certificates and redirects HTTP, so it cannot bootstrap TLS as supplied.
- [ ] Configure/rehearse certificate renewal, replace hostname/certificate placeholders, and reject unknown redirect hosts or use a fixed canonical host.
- [ ] Validate final Nginx configuration with the exact pinned image and confirm it overwrites forwarded protocol and client-IP headers.
- [ ] Configure protected production values with `DEPLOYMENT_MODE=production`, `DEBUG=False`, a strong `SECRET_KEY`, exact `ALLOWED_HOSTS`, matching HTTPS `CSRF_TRUSTED_ORIGINS`, and consistent database/Redis URLs. Never commit or print secret values.
- [ ] After proxy behavior and Gunicorn isolation are verified, approve/configure Django `SECURE_PROXY_SSL_HEADER`; test that Django recognizes HTTPS while `ENABLE_HTTPS` is still false.
- [ ] Only after the proxy test passes, set `ENABLE_HTTPS=True`; verify HTTPS, redirects, secure cookies, CSRF, unknown-host rejection, and Django `check --deploy`. The current production Compose template hard-codes this setting to true, so do not start it before these gates pass.
- [ ] Enable HSTS gradually only after stable HTTPS; keep `includeSubDomains` and `preload` disabled until separately reviewed.
- [ ] Confirm static assets load through WhiteNoise and public media is intentionally served. Prove private contact attachments cannot be fetched through a public URL and authorized admin access still works.
- [ ] Verify SMTP TLS, sender authorization, successful delivery to a controlled mailbox, and failure handling without real customer data.

## Data, backup, and recovery

- [ ] Confirm PostgreSQL and Redis have no public ports and database/admin access is restricted.
- [ ] Confirm named-volume ownership and application write access in a disposable rehearsal.
- [ ] Configure scheduled encrypted logical PostgreSQL backups and encrypted private-upload backups to independent off-server storage.
- [ ] Set and document retention, access control, integrity verification, encryption-key recovery, and backup failure alerts.
- [ ] Verify a database backup and upload backup, then successfully rehearse restoration in an isolated environment with no production route. A snapshot alone is not complete backup validation.
- [ ] Approve measurable RPO/RTO targets. Current planning proposal is 24-hour RPO and 8-hour RTO; these are not achieved guarantees.

## Release and rollback

- [ ] Verify tests and system checks on the approved release commit.
- [ ] Build and record an approved immutable image digest; retain the last known-good image/config.
- [ ] Confirm current backups are readable/off-server and review the explicit migration plan.
- [ ] Obtain manual deployment approval before production changes.
- [ ] Apply reviewed migrations as a controlled one-off step; application container restarts do not run migrations automatically.
- [ ] Start/update only approved services, then verify `/health/`, TLS, all public endpoints, logs, disk/memory, SMTP, and private media security.
- [ ] Monitor errors, restarts, certificate expiry, disk capacity, backup completion, and contact delivery.
- [ ] If rollback is needed, restore the prior image/config only after checking schema compatibility. Rolling back an image does not roll back database migrations; use a tested forward fix or approved isolated restore plan where needed.

## SEO launch approval

- [ ] Keep `SEO_INDEXING_ENABLED=False` until launch approval.
- [ ] Confirm domain ownership and HTTPS work before setting `SEO_SITE_URL` to the actual HTTPS origin.
- [ ] Verify canonical URLs, `sitemap.xml`, and `robots.txt`; confirm the sitemap contains published projects only.
- [ ] Check redirect and trailing-slash behavior, 404/500 responses, and rendered public pages.
- [ ] Review noindex behavior while indexing is disabled, then explicitly approve enabling `SEO_INDEXING_ENABLED`.
- [ ] Submit the sitemap to Google/Bing only after launch approval. No submission is authorized in this phase.

## Operational acceptance

- [ ] Confirm log retention/redaction, health monitoring, alert recipients, on-call owner, and incident/recovery runbook.
- [ ] Confirm post-launch checks and owner for periodic restore rehearsal, dependency/image updates, Django deploy-check review, and cost review.
- [ ] Record approval for any unresolved risk, cost exception, availability limitation, or privacy/data-retention decision.
