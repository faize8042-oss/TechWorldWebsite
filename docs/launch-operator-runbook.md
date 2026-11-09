> Final execution sequence and current packaging updates: [deployment handoff](deployment-handoff.md).
> This supplements the earlier evidence below; no runtime success is claimed.

# Operator runbook

Status: future operator procedure, not execution approval. No infrastructure was
changed during preparation. Use a fresh isolated production project and storage.

## Safe commands now (PowerShell, repository root)

```powershell
.venv/Scripts/python.exe -B scripts/test_launch_offline.py
.venv/Scripts/python.exe -B scripts/test_c621_django.py
.venv/Scripts/python.exe -B -m unittest discover -s scripts -p test_c621_offline.py
.venv/Scripts/python.exe -B -m unittest discover -s scripts -p test_c621_harness_offline.py
.venv/Scripts/python.exe -B -m unittest discover -s scripts -p test_c621_image_offline.py
.venv/Scripts/python.exe -B scripts/test_c61_probe.py
node --check static/js/main.js
node --check static/js/navigation.js
node --check static/js/theme.js
git diff --check
git diff --exit-code -- compose.yaml
git status --short
```

Do not use wildcard unittest discovery over command-style test scripts: the
existing test_c621_django.py invokes its runner and exits at import time.

## Dependency and image gate

Follow [validation image procedure](c6-2-1-validation-image.md). No local reviewed
lockfile or wheelhouse was found. Select Linux architecture and Python 3.12 patch
version; record resolver version, trusted package index and base platform digest.
On a separately approved matching Linux resolver host, resolve requirements.txt
with all extras/markers, download binary wheels only, and generate a lock with
every direct/transitive version and independently verified SHA-256. Record wheel
filenames, metadata Requires-Dist, licenses and provenance. Verify closure with
an offline hash-required install and pip check. Do not derive Linux pins from the
local Windows environment (Python 3.14). The validation Dockerfile remains blocked
until these reviewed inputs exist. Build and runtime testing require separate
authorization; neither was performed. Review application and Nginx base/dependency
pins and vulnerability results before creating immutable production images.

## Host, domain and TLS

Provision a supported Linux VPS with enough RAM for configured container limits
(at least 4 GiB plus monitoring/headroom), persistent encrypted disks, SSH key
access, firewall and off-host backups. Publish only 80/443 and restricted SSH;
never publish PostgreSQL, Redis or Gunicorn. Confirm Docker subnet compatibility.
Set apex A (and AAAA only with working IPv6) and www canonical DNS after ownership
verification. Obtain certificates with a reviewed DNS challenge or separate HTTP
bootstrap configuration; the supplied TLS Nginx template cannot bootstrap itself.
Replace certificate placeholders, verify renewal and reload procedures. Never
activate the production template before certificate files exist and TLS works.

## Secrets and fresh database

Use protected files outside the repository, readable only by required container
identities; mount runtime JSON at /run/secrets/django_runtime. Follow the allowlist
in config/production_database.py. Generate independent Django, analytics, Redis,
cv_init, cv_runtime, cv_migrate and cv_backup secrets. Preserve Gmail SMTP with a
dedicated authorized app password, TLS/587 or SSL/465. Runtime DATABASE_URL must
use cv_runtime@db/codeventra; migration secret contains only cv_migrate URL.
Percent-encode password URI components. Never print credentials in commands/logs.
Set confirmed hosts and CSRF HTTPS origins. Redis config and REDIS_URL passwords
must agree. Keep SEO_INDEXING_ENABLED=False and HSTS_SECONDS=0.

Use [C6.2.1 provisioning and migration instructions](c6-2-1-postgresql-hardening.md)
sections 4–7 as the authoritative SQL/credential procedure. Fresh.sql must run only
on a confirmed empty database; grants.sql follows, then independent SCRAM passwords.
Use psql -X -v ON_ERROR_STOP=1 in a protected operator session. Do not reuse or adopt
existing development data. A separately reviewed migration job must mount runtime
and migration secrets only, use config.migration_settings and SET ROLE cv_owner.
Normal web startup checks intentionally reject migration identity. Inspect migration
plans before applying; then verify ownership and runtime/backup denial contracts.
An opt-in `migrate` service is now provided under the operator profile. Its default
command prints the plan only; runtime approval and rehearsal remain mandatory.

## Release and rollback

Select approved APP_IMAGE and NGINX_IMAGE digests; supply protected secret file
paths to deploy/compose.production.yaml. Provision socket directory 10001:10002
mode 2750 and private/media paths writable by UID 10001. Verify Nginx socket group
10002, no TCP Gunicorn listener, dropped web capabilities/read-only root, internal
data network and SMTP-only operational egress requirements. Added mail_egress is
a bridge, not a destination firewall: restrict outbound traffic at the host if
required. Resource limits are initial budgets requiring load verification.
Review finalized Compose/Nginx configs and deployment checks on the approved host
before starting services. Do not run development compose.yaml for production.

Before any release, capture approved images/configuration and a paired database
and upload recovery point. Follow [backup/restore procedure](production-readiness.md):
cv_backup custom-format pg_dump, encrypted off-host storage, checksum, archive
listing and actual restore into an isolated target. Reapply owner/ACL contracts;
verify attachments against restored records. Define RPO/RTO, retention and alerting.
Rollback to a known-good image/configuration only after schema compatibility review.
Do not blindly reverse migrations or delete volumes; restore only through a
separately approved recovery plan with traffic/writes paused as needed.

## Smoke tests before traffic/indexing

Check every public page, published/draft portfolio visibility, 404/500, health,
versioned CSS/JS, mobile menu/keyboard/focus/reduced motion, contact validation,
CSRF rejection, sixth-submission limit and controlled SMTP success/failure. Confirm
private attachments are inaccessible publicly and downloads require admin object
permission. Test forged proxy headers, unknown hosts, HTTP redirect, secure cookies,
TLS chain and renewal. Health is liveness only, not DB/Redis readiness. Monitor
dependency health, errors, disk usage and backup age externally. Enable indexing
only after content/domain/TLS approval, then inspect canonical/social URLs,
sitemap and robots. Increase HSTS gradually only after stable HTTPS.
