# Final deployment handoff — 2026-10-31

**NO-GO today until the gates below have evidence.** Preparation grants no execution
approval. All commands below are future operator instructions except A. No Docker,
network service connection, credential read, migration or infrastructure action
was performed during this handoff. Preserve existing uncommitted work.

## Critical path and command approval contract

Run A now; resolve reviewed Linux lock/wheel closure and image provenance; purchase
fresh VPS/domain; run B; run C on a separate disposable Linux engine; provision
secrets/storage and rehearse release/restore on that isolated host; only then D.
Do not skip C to meet a deadline. Parallelize procurement and dependency review.

Every command in B–E inherits the target, prerequisites, risk and approval in its
section header. Operator must record approval for each section before executing
any command in it, plus the per-step gates stated below. Shell examples use bash
on Ubuntu 24.04 as root (`sudo -i` after authorized SSH). Never paste actual secret
values into shell commands. Stop on any nonzero exit; never continue blindly.
Public IPs, reviewed digests, release checksum, email and SSH CIDR are required
operator inputs, not supplied facts. No commands target development Compose.

## A. Safe local verification (PowerShell, repository root)

Target: source and synthetic in-memory tests. Approval: current repository-only
request. No credential inputs, Docker, network databases or SMTP.

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

## B. New VPS preparation

Target: purchased, empty Ubuntu 24.04 VPS only. Prerequisites: provider console,
verified SSH host key, key-based sudo operator, recovery access, approved IP/CIDR,
4 GiB RAM minimum plus disk/backup headroom. Approval: purchase, OS/package/firewall
and certificate changes. Risks: cost, SSH lockout, reboot, public port exposure.
Use provider firewall to allow 22 only from operator CIDR and 80/443 publicly;
reject all other inbound traffic including IPv6. Docker published ports bypass
some UFW rules: provider firewall is required. No Docker group membership needed.

```bash
set -euo pipefail
. /etc/os-release
test "$ID:$VERSION_ID" = ubuntu:24.04
apt-get update
apt-get upgrade -y
apt-get install -y ca-certificates curl ufw certbot python3 openssl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
read -r -p 'Approved SSH source CIDR: ' SSH_CIDR
ufw default deny incoming
ufw default allow outgoing
ufw allow from "$SSH_CIDR" to any port 22 proto tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
systemctl enable --now docker
install -d -m 0700 /etc/codeventra /srv/codeventra /srv/codeventra/release /srv/codeventra/backups
```

Keep the current SSH session; verify a second login before tightening sshd to
`PasswordAuthentication no` and `PermitRootLogin no`; run `sshd -t` before
`systemctl reload ssh`. Reboot via provider console if OS upgrades require it,
then verify access and time synchronization. Record package versions.
Docker setup source: https://docs.docker.com/engine/install/ubuntu/ .

### Domain/DNS and TLS (B continuation, separate DNS/CA approval)

Target: registrar/DNS zone codeventralabs.com and new VPS. Prerequisites: domain
ownership, correct nameservers and VPS IP, registrar MFA, renewal/payment custody.
Risks: incorrect routing, issuance limits, downtime; approval: zone changes and CA
terms. Buy domain without transferring any existing unrelated zone. Set apex A to
VPS IPv4, www CNAME to codeventralabs.com., TTL 300. Remove conflicting parking
records. Add AAAA only after end-to-end IPv6 and firewall verification, otherwise
leave absent. Optional CAA `0 issue "letsencrypt.org"` after reviewing zone policy.
Do not change MX/TXT mail records; Gmail SMTP does not require moving domain mail.
From independent resolvers verify both names resolve to the approved server.
Port 80 must be free and reachable before standalone issuance.

```bash
read -r -p 'Approved certificate account email: ' ACME_EMAIL
certbot certonly --standalone --non-interactive --agree-tos --email "$ACME_EMAIL" --cert-name codeventralabs.com -d codeventralabs.com -d www.codeventralabs.com
```

Protect `/etc/letsencrypt` root-only; never loosen private key permissions.
Certificates cover both names; HTTP redirects to apex, HTTPS www serves the same
site with apex canonical metadata. Mount whole LetsEncrypt tree read-only.

## C. Disposable isolated validation

Target: dedicated disposable Linux Docker engine, never the development engine or
production. Prerequisites: reviewed source snapshot and approval of that snapshot,
all Linux Python 3.12 direct/transitive dependencies pinned with verified hashes,
binary wheels, offline hash-required install and pip check, approved build/SBOM/
vulnerability results and locally resolvable immutable manifests. Approval: image
build/acquisition separately, then disposable execution. Risks: image execution,
resource consumption, temporary objects. No real secrets, ports or persistent
volumes. Missing lock/wheels/digests means STOP, not mutable-tag substitution.

Follow `c6-2-1-validation-image.md` exactly for build and image review; root
Dockerfile still has unlocked requirements and mutable base, so it is NOT an
approved reproducible release builder. Do not invent hashes. Require approved
app, custom Nginx, PostgreSQL 17 and Redis images as well as the validation image.
Verify platform, PostgreSQL PGDATA and UID/GID contracts, unexpected image volumes,
entrypoint/history, native psycopg imports and no embedded secrets. Record source
and artifact checksums. No fabricated RepoDigests or harness edits permitted.

```bash
python3 -I scripts/c621/harness.py
read -r -p 'Reviewed local postgres:17@sha256 reference: ' PG_REF
read -r -p 'Reviewed local validation repository@sha256 reference: ' VALIDATION_REF
python3 -I scripts/c621/harness.py --execute --approval 'APPROVE DISPOSABLE C6.2.1 VALIDATION' --postgres-image "$PG_REF" --python-image "$VALIDATION_REF" --timeout 600
```

Review sanitized report and exit status: fresh provisioning replay fails, role
membership/ownership/default ACLs, runtime DML and DDL denial, migration owner,
backup read-only, rollback, secret isolation and cleanup must pass. Inspect engine
objects after harness cleanup by recorded generated names only; never prune.
Then rehearse D's exact image/config/secrets/migration/storage/TLS equivalent and
E restore on fresh isolated storage with synthetic data. C6.2.1 alone does not
prove Nginx, Redis, SMTP, certificate renewal or full production operation.

## D. Production activation

Target: fresh VPS project `codeventra-prod` only. Prerequisites: B/C pass, approved
release archive with checksum and all four image digests, accepted source snapshot
(including uncommitted fixes packaged intentionally), secrets custody, backup
rehearsal, downtime plan. Approval: secret creation, new storage/network/container
creation, role SQL, migration plan, then public activation separately. Risks:
credential loss, data loss from wrong target, schema errors and public exposure.
Never use `git archive HEAD` as the release: it omits the current uncommitted work.
Transfer a reviewed clean source artifact excluding dotenv/uploads/logs/results/
Git/venv, verify its externally approved SHA256, unpack into the empty release
folder. Do not copy the workspace wholesale or read local credentials.

### 1. Secrets and release parameters

In a protected, unrecorded root console use `umask 077` and a secret manager to
create independent random credentials (at least 32 random bytes) and these files:

| Host file in /etc/codeventra | Contract |
| --- | --- |
| postgres-admin | cv_init password; no newline surprises |
| runtime.json | string-only RUNTIME_KEYS from config/production_database.py |
| migration.json | only DATABASE_URL for cv_migrate |
| redis-password | same random hex password used below |
| redis.conf | bind 0.0.0.0; protected-mode yes; port 6379; requirepass secret |
| backup.pgpass | db:5432:codeventra:cv_backup:password; mode 0600 |

Runtime JSON requires SECRET_KEY, ANALYTICS_HMAC_SECRET, DATABASE_URL
`postgresql://cv_runtime:<encoded>@db:5432/codeventra`, REDIS_URL
`redis://default:<encoded>@redis:6379/0`, ALLOWED_HOSTS
`codeventralabs.com,www.codeventralabs.com`, CSRF_TRUSTED_ORIGINS
`https://codeventralabs.com,https://www.codeventralabs.com`, SEO_SITE_URL
`https://codeventralabs.com`, CONTACT_EMAIL, DEFAULT_FROM_EMAIL, EMAIL_HOST
`smtp.gmail.com`, EMAIL_PORT `587`, EMAIL_USE_TLS `True`, EMAIL_USE_SSL `False`,
EMAIL_HOST_USER and authorized Gmail app password EMAIL_HOST_PASSWORD.
All JSON values are strings. Migration URL uses cv_migrate, never cv_init.
Use a secret-manager URI encoder, never interpolate passwords into commands.
Redis config also needs `maxmemory 128mb`, `maxmemory-policy noeviction`,
`save ""`, `appendonly no`, `logfile ""`. Redis is cache/rate limits only; restart
clears limits. No public Redis port; password and URL must match. Noeviction errors
must be monitored; never silently fall back to a local cache.

Compose file secrets are bind mounts, not an encrypted vault. Host parent directory
0700 root prevents host traversal. Set runtime.json and migration.json to UID
10001 GID 10002 mode 0400 so non-root jobs can read mounts. Redis image startup
identity/secret readability must be rehearsed; root-owned mode 0444 files inside
0700 parent permit its non-root process to read without host-wide traversal.
Keep admin/backup files 0600 root. Never print secret files, env or expanded config.

Create `/etc/codeventra/release.env` (root 0600, nonsecret metadata only): APP_IMAGE,
NGINX_IMAGE as approved repository@sha256 values and POSTGRES_ADMIN_PASSWORD_FILE,
DJANGO_RUNTIME_SECRET_FILE, DJANGO_MIGRATION_SECRET_FILE, REDIS_PASSWORD_FILE,
REDIS_CONFIG_FILE as the absolute paths above. In the reviewed release copy replace
only db/redis image tags with approved immutable digests; review the diff and hash.
Neither mutable repository defaults nor validation base digest is release approval.

```bash
cd /srv/codeventra/release
cv() { docker compose --env-file /etc/codeventra/release.env -p codeventra-prod -f /srv/codeventra/release/deploy/compose.production.yaml "$@"; }
cv config --quiet
cv pull db redis web nginx migrate
```

Image acquisition above requires explicit registry/network approval. Verify pulled
manifests against approved release inventory before execution. Store finalized
Compose/config plus image digests and source checksum in protected release record.
Configure Docker log rotation before starting services (merge reviewed daemon
configuration; fresh-host restart requires approval); monitor disk and backup age.

### 2. Fresh database and storage

Confirm project name unused and no preexisting `codeventra-prod_*` volumes. Stop
if any exist; do not adopt them. Init-only cv_init secret stays away from Django.

```bash
cv up -d --no-build --pull never db redis
cv ps
cv exec -T db psql -X -v ON_ERROR_STOP=1 -U cv_init -d codeventra < deploy/postgres/fresh.sql
cv exec -T db psql -X -v ON_ERROR_STOP=1 -U cv_init -d codeventra < deploy/postgres/grants.sql
cv exec db psql -X -v ON_ERROR_STOP=1 -U cv_init -d codeventra
```

At the psql prompt use `SET password_encryption='scram-sha-256';` then
`\password cv_runtime`, `\password cv_migrate`, `\password cv_backup`, entering
matching manager-held values interactively; `\q`. No SQL password literals.
Review server logging before password ceremony. Confirm db/redis healthy; pg_isready
is liveness, not proof that runtime authentication or ACLs work.

New named volumes copy image directory metadata on first use. Explicitly provision
only these new volumes using the reviewed app image and a one-off root job:

```bash
cv run --rm --no-deps --user 0:0 --cap-add CHOWN --cap-add FOWNER --entrypoint sh web -c 'chown 10001:10002 /run/codeventra /app/private_uploads /app/media && chmod 2750 /run/codeventra && chmod 0700 /app/private_uploads && chmod 0755 /app/media'
cv run --rm --no-deps web python manage.py check --deploy --fail-level WARNING
cv run --rm --no-deps migrate
```

Review deployment-check output: HSTS/preload warnings are deliberate while HSTS=0;
record only those specific accepted warnings, investigate all others. The strict
WARNING command can exit nonzero for that policy; do not apply migrations until
review is signed. Do not weaken checks or make a general warning suppression.
Migration default prints plan only. Inspect every RunSQL/RunPython; require
session_user=cv_migrate/current_user=cv_owner using the migration settings before
DDL. Approve this exact plan, then:

```bash
cv run --rm --no-deps migrate python manage.py migrate --settings=config.migration_settings --skip-checks
cv exec -T db psql -X -v ON_ERROR_STOP=1 -U cv_init -d codeventra < deploy/postgres/grants.sql
cv exec -T db psql -X -v ON_ERROR_STOP=1 -U cv_init -d codeventra < deploy/postgres/inventory.sql
```

`--skip-checks` is ONLY for the migration identity intentionally rejected by web
checks; full runtime checks precede it. Run live privilege probes from the isolated
rehearsal on this new target under separately approved read-only/transactional
probe scope; verify runtime/backup cannot CREATE/SET ROLE owner and backup cannot
INSERT/UPDATE/DELETE. Inventory alone cannot prove login denial behavior.
Remove migration credential access from routine operators after the window.
Static collection must already have succeeded with build-only synthetic settings
inside the approved app image: verify staticfiles.json and served hashed CSS/JS.
Do not run collectstatic on read-only production containers or use real secrets
at build time. Private uploads stay on their separate 0700 volume, never Nginx.

### 3. TLS renewal and opening traffic

With certificate already issued and accepted warning review complete:

```bash
cv run --rm --no-deps nginx nginx -t
cv up -d --no-build --pull never web
cv up -d --no-build --pull never nginx
cv ps
cv logs --tail 100 db redis web nginx
```

Review logs confidentially; redact user data before attaching evidence. No admin
or database credentials should appear. web has no healthcheck: verify socket,
HTTPS /health/, actual DB writes and Redis-backed limits separately. Liveness
endpoint alone is insufficient.

Renewal target: only this nginx service. Prerequisite: successful TLS bootstrap,
approved short renewal interruption. Risk: brief downtime, failed restart.
Approval: install root-owned hooks and timer; dry-run also stops/starts nginx.
Create root 0750 `/etc/codeventra/renew-pre` and `renew-post` scripts with `#!/bin/sh`,
`set -eu` and the exact cv Compose prefix above followed by `stop nginx` and
`start nginx` respectively. Scripts must not depend on the interactive cv function.
Then:

```bash
certbot renew --cert-name codeventralabs.com --dry-run --pre-hook /etc/codeventra/renew-pre --post-hook /etc/codeventra/renew-post
```

Persist hooks in that certificate's reviewed renewal configuration or its pre/post
directories (dedicated server only); validate a second dry run without CLI hooks,
then `systemctl enable --now certbot.timer` and `systemctl list-timers certbot.timer`.
Post-hook starts Nginx even on renewal failure; restarting loads renewed certificate.
Monitor external expiry and hook/timer failures. Never remove current certificates
on renewal failure. Source: https://eff-certbot.readthedocs.io/en/stable/using.html .

### 4. Public acceptance (required before GO)

```bash
for route in / /services/ /projects/ /contact/ /privacy/ /terms/ /health/; do
  curl --fail --silent --show-error -o /dev/null -w '%{http_code}\n' "https://codeventralabs.com$route"
done
curl -sSI http://codeventralabs.com/
curl -sSI https://www.codeventralabs.com/
curl -sSI https://codeventralabs.com/robots.txt
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://codeventralabs.com/contact/ --data 'message=csrf-probe'
```

Expect pages 200, HTTP 301 to apex HTTPS, valid chain for both names, CSRF probe
403. Browser: secure cookies, keyboard/mobile nav, hashed CSS/JS 200, no mixed
content; projects published-only, missing page 404, no private attachment URL
access, admin object authorization. Controlled contact submission with consenting
test mailbox must persist and deliver SMTP; verify failure path with isolated
SMTP fixture. Rate-limit test uses one approved client IP and valid CSRF tokens:
sixth counted attempt must be rejected; do not spoof production proxy identity.
Confirm distinct clients have independent limits, forged forwarded headers cannot
bypass, direct Gunicorn/DB/Redis ports unreachable externally, unknown hosts rejected.
Check TLS renewal dry run, healthy dependencies, bounded logs, alerts, disk, backup
age and actual privilege denial evidence. Keep indexing false/HSTS zero until
separate approval after stable HTTPS. Verify canonical URLs before indexing.

## E. Backup, restore rehearsal and rollback

Target: production backup stream plus separate fresh recovery project/host.
Prerequisites: approved backup identity, paired DB/upload recovery point, encrypted
off-host destination/key custody, RPO/RTO and retention. Approval: pause writes,
read/export sensitive data, transfer encrypted backup, restore ONLY to named fresh
target, and traffic cutover separately. Risks: sensitive export, inconsistent files,
loss of writes since recovery point, schema/image incompatibility. Never down -v,
prune, reset development, or reverse migrations blindly.

For a consistent DB/upload pair stop web while Nginx returns controlled maintenance
response; retain nginx config for recovery. Backup reads use cv_backup, not admin.
The following temporary pgpass mount is an explicit one-off operator action,
removed after dump; never add backup secrets to web or migration services.

```bash
cv stop web
umask 077
cv cp /etc/codeventra/backup.pgpass db:/tmp/codeventra-backup.pgpass
cv exec -T --user 0 db chmod 0600 /tmp/codeventra-backup.pgpass
cv exec -T --user 0 db sh -c 'PGPASSFILE=/tmp/codeventra-backup.pgpass pg_dump -h db -U cv_backup -d codeventra -Fc --no-owner --no-acl' > /srv/codeventra/backups/database.dump
cv exec -T --user 0 db rm /tmp/codeventra-backup.pgpass
cv run --rm --no-deps --entrypoint tar web -C /app -czf - private_uploads media > /srv/codeventra/backups/uploads.tar.gz
sha256sum /srv/codeventra/backups/database.dump /srv/codeventra/backups/uploads.tar.gz > /srv/codeventra/backups/SHA256SUMS
cv exec -T db pg_restore --list < /srv/codeventra/backups/database.dump > /srv/codeventra/backups/archive.list
cv start web
```

Secure backup directory 0700 and files 0600; encrypt using the approved backup
platform before off-host transfer; verify remote checksum and decryptability. On
any dump failure remove temporary pgpass through approved cleanup and restore
service deliberately. Archive listing is not restore proof.

On a separate fresh recovery host deploy the same reviewed release with its own
project/volumes/secrets. Run fresh.sql and grants.sql as above, set fresh login
passwords, **do not run migrations before restoring the complete dump**. With
recovery web stopped, copy dump into its DB container, then restore through pg_restore with
`--role=cv_owner --no-owner --no-acl --exit-on-error` using cv_migrate authentication
and a temporary protected pgpass, mirroring the backup transfer method. Exact
restore invocation inside the recovery db container (not production):

```bash
PGPASSFILE=/tmp/recovery-migrate.pgpass pg_restore -h db -U cv_migrate -d codeventra --role=cv_owner --no-owner --no-acl --exit-on-error /tmp/recovery.dump
```

This shell command runs only inside that new container; provision/copy protected
pgpass and dump there first, chmod 0600, remove afterward. Do not run it in the
production cv function context. Reapply grants.sql, inventory ownership/default
ACLs and privilege probes, restore uploads into fresh volumes with web stopped,
reapply UID10001/GID10002 and private0700 permissions. Verify row counts, attachment
hashes/admin downloads, SMTP fixture and all D smoke tests. Record elapsed recovery
time and recovered timestamp, compare RPO/RTO, then securely remove rehearsal
secrets. An approved backup provider encryption/upload implementation and scheduled
backup job remain operator artifacts: no storage account/key has been selected.

Rollback before public activation: stop only new nginx/web; retain DB/volumes and
reports for diagnosis. After activation, capture recovery point and pause writes;
select previous approved APP_IMAGE/NGINX_IMAGE/config only if schema compatibility
is proven; `cv up -d --no-build --pull never web nginx`. First release has no known
good prior production version: default rollback is maintenance, repair or restore
to a new recovery target, then approved DNS/traffic switch. Never overwrite the
only data copy or delete volumes. Restore entails explicit acceptance of RPO loss.

## Remaining blockers and GO signature

No actual locks, wheels, verified image manifest inventory, domain/VPS, secrets,
certificate, runtime proof, backup service or restore evidence exist yet. The
migration service and fixed certificate paths resolve packaging gaps only.
GO requires signed C report plus full-stack rehearsal, approved immutable release,
new target/secret custody, DNS/TLS/renewal, migration/ACL proof, static/private media,
SMTP/CSRF/rate limits and external smoke results, off-host backup+restore proof,
monitoring/alerts and named incident/renewal owner. Otherwise NO-GO.

CODEVENTRA LABS DEPLOYMENT HANDOFF READY ?
AWAITING INFRASTRUCTURE AND OPERATOR APPROVAL.
