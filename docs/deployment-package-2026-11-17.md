# Deployment package verification — 17 November 2026

The first-deployment package is ready for configuration on a fresh Ubuntu 24.04
amd64 VPS. The domain and hosting remain unpurchased. No production server,
certificate, mailbox, backup destination or monitoring account was configured.

## Delivered

- `deploy/release/release.py`: configuration wizard, immutable image preparation,
  separated database identities, schema migration, public content/image import,
  storage initialization, admin creation, HTTP certificate bootstrap, public HTTPS
  checks, SMTP authentication check, gated indexing launch, encrypted paired
  backups, retention cleanup, renewal and systemd schedules.
- Hash-locked Linux Python 3.12 dependencies, package wheel checksums, pinned
  Python/PostgreSQL/Redis/Nginx base identities and non-root production image.
- A public-only content bundle: one category, one blog post, one news item and
  their two existing cover images. No users, enquiries, analytics, private
  attachments, drafts or future publications are exported.
- GitHub release-check workflow and a repeatable disposable Docker rehearsal.
- [Configuration and launch guide](../deploy/release/README.md), including
  recovery, backup copying, operating checks and rollback limits.

## Passed locally

- Final production image built successfully; dependency hash verification and
  `pip check` passed.
- **123 application tests** passed against the locked production dependencies.
- **22 operator and credential/storage contract tests** passed, including
  secret file ownership/modes and configuration rollback on failed launch.
- A fresh, separately named Docker project completed PostgreSQL provisioning,
  all application migrations, authenticated Redis startup, public content import,
  real private-socket Gunicorn/Nginx routing and HTTPS page/image delivery.
- Runtime SQL administration was denied, migration/administrator secret mounts
  were absent from web, and a new category received a valid post-import ID.
- Public content SEO audit: two published articles, zero metadata issues.
- Enquiry and analytics cleanup commands executed on the disposable database.
- An encrypted backup decrypted successfully; PostgreSQL restored into a new QA
  database with both articles recovered. Both article image hashes matched and a
  synthetic private attachment was recovered byte-for-byte.
- Deliberately invalid backup encryption restarted the web service and removed
  the partial archive while preserving the previous successful backup.
- Verified-launch indexing and staged HSTS configuration served indexed pages
  and the configured sitemap after recreation of the production web service.
- The image excludes `.env`, real uploaded files and unrelated local portfolio
  work. All rehearsal containers, volumes and networks were cleaned up; the
  original development services remained running.

The rehearsal used its own generated secrets, test-only self-signed certificate,
loopback ports and databases. It did not use real SMTP credentials or send email.
Normal live HTTPS verification retains certificate trust checking. Rehearsal
output is kept locally in ignored `validation-results/` files.

## Configuration and live verification still required

Purchase the domain and supported hosting; configure DNS/firewall, SMTP sender
verification and credentials, age public recipient and off-server backup storage.
Run the supplied launch commands, create the administrator account and confirm a
real enquiry reaches the chosen inbox. Verify the generated certificate and
renewal on that server, enable the supplied schedules, and configure provider
monitoring for failed jobs/public availability. Submit the sitemap through your
verified Search Console account.

Current article wording and dates are preserved; their claims were not
independently fact-checked. Demos remain labeled sample-data demonstrations.
Traffic growth, provider deliverability, future security updates and ongoing
content/operations cannot be guaranteed by a first-deployment package.
