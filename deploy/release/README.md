# Configure and launch TechBullion Hub

This is the supported first-deployment route. It automates image builds,
least-privilege PostgreSQL provisioning, migrations, current public content and
images, persistent storage, HTTPS configuration, encrypted backups, retention
cleanup, and enabling search indexing after public HTTPS verification.

## Hosting requirements

Use a **fresh Ubuntu 24.04 amd64 VPS with root/SSH access and Docker support**.
Allow at least **2 CPU cores, 4 GB RAM and 25 GB SSD** for this stack and its
builds; increase disk as uploads/database/backups grow. Ordinary PHP/shared
hosting cannot run this package. This is a single-server deployment, not a
high-availability service.

You will configure:

- The purchased domain: apex DNS `A` record to the server IPv4 and `www` as an
  alias to the apex. Set IPv6 only if it actually reaches this server.
- Provider firewall: public TCP 80/443; SSH restricted to your trusted IP.
  Do not expose PostgreSQL, Redis or Gunicorn. Avoid a DNS/CDN proxy during
  initial certificate issuance; direct DNS makes reachability unambiguous.
- An SMTP provider, its authenticated username/password, and a verified sender.
  Add the provider's SPF/DKIM records and a DMARC policy. Your public contact
  address remains `faize8042@gmail.com`; your sender can use your new domain.
- An **age public encryption recipient** generated on your own computer:
  `age-keygen -o techbullionhub-recovery.agekey`. Keep this private recovery key
  offline with a second secure copy. Copy only its public `age1...` recipient
  into server configuration. Losing the private key makes backups unrecoverable.
- A separate place to keep copies of encrypted backups. A server's own disk is
  not an off-server backup. Set up your hosting provider's backup/export service
  or download archives regularly; see the backup section below.

These are configuration/account tasks; no application code changes are needed.

## 1. Prepare the server and configuration

Run these commands on the server as root, using a stable release directory:

```sh
apt-get update
apt-get install -y git
git clone https://github.com/faize8042-oss/TechWorldWebsite.git /srv/techbullionhub
cd /srv/techbullionhub
sh deploy/release/setup-host.sh
cp deploy/release/config.example.json /root/techbullionhub-config.json
chmod 600 /root/techbullionhub-config.json
```

Edit `/root/techbullionhub-config.json`: replace the SMTP placeholders and backup
public recipient. Domain, contact address and certificate email are already set
for TechBullion Hub. Set `smtp_ssl: false` for STARTTLS (usually port 587), or
`true` for implicit TLS (usually port 465), according to your provider.

```sh
python3 deploy/release/release.py configure --config /root/techbullionhub-config.json
python3 deploy/release/release.py build
python3 deploy/release/release.py install
python3 deploy/release/release.py admin
```

`configure` asks for your SMTP password privately, generates separate application,
migration, backup, Redis and administrator secrets, and never overwrites an
existing setup. Keep `/etc/techbullionhub` private. File ownership is set for
the actual Linux container users; Compose file-secret ownership options are not
relied on. Do not copy development `.env`, users, enquiries or database volumes.

`build` uses the hash-locked Linux/Python 3.12 dependencies and digest-pinned base
images. Generated Compose configuration freezes built images by local content ID.
Do not prune these release images; keep them for recovery. This first-release
build command refuses to run after installation.

`install` fails on an unexpected existing database, uses the dedicated migration
role, reconciles permissions, imports the reviewed public content, then starts the
application. It does not republish drafts or import private records. Completed
steps are recorded so a failed installation can be retried. If a crash occurs
between a completed database/content operation and its marker write, stop and
inspect privately rather than deleting data to get past the guard.

`admin` creates your administrator account interactively. Use a unique strong
password and keep it private.

## 2. HTTPS, verification and launch

After DNS points to the server and TCP 80/443 are reachable:

```sh
python3 deploy/release/release.py certificate
python3 deploy/release/release.py smtp-check
python3 deploy/release/release.py backup
python3 deploy/release/release.py check
```

Certificate issuance uses Certbot's HTTP webroot. It switches Nginx to HTTPS only
after issuance succeeds, redirects `www` to the apex, and tests the actual public
pages using normal certificate validation. Unknown hosts are rejected. The app
continues to use a private Unix socket, with no public application port.

`smtp-check` verifies encrypted SMTP authentication **without sending a message**.
After configuring your real sender, use the website yourself to submit one enquiry
and confirm inbox delivery and attachment access in Admin. Sender reputation and
inbox delivery depend on the provider/DNS; authentication alone cannot prove them.

Review the live mobile/desktop pages and your existing article content. The
imported articles retain your existing wording and publication dates; their claims
have not been independently fact-checked. The four demos remain honestly labeled
as demonstrations with sample data.

```sh
python3 deploy/release/release.py launch
python3 deploy/release/release.py timers
```

`launch` requires the installation, SMTP authentication and first encrypted backup,
then verifies public HTTPS before enabling indexing and a five-minute HSTS period.
It reverts the configuration if the post-launch check fails. It never enables
HSTS preload or includeSubDomains. Submit `https://techbullionhub.net/sitemap.xml`
to your verified Google Search Console property after launch. Indexing/ranking
and ongoing editorial work are not guaranteed by software configuration.

## Operations

```sh
python3 deploy/release/release.py check
python3 deploy/release/release.py backup
python3 deploy/release/release.py maintenance
python3 deploy/release/release.py renew
systemctl list-timers 'techbullionhub-*'
systemctl --failed
journalctl -u techbullionhub-backup.service -u techbullionhub-maintenance.service
docker compose -p techbullionhub -f /etc/techbullionhub/compose.json ps
```

Timers run daily cleanup at 02:00, backup at 03:00, and certificate renewal twice
daily, and HTTPS health checks every five minutes, with a small random delay.
Missed runs are persistent. Commands share an
operator lock, so backup, renewal and cleanup cannot overlap. Failed jobs are
visible in systemd; arrange your provider's monitoring/alerts for these services
and public HTTPS. No alert destination/account is assumed or messaged.

Cleanup applies the approved **90-day** rule only to unanswered enquiries, using
the existing database/file checks. Analytics uses its configured retention period.
Answered enquiries are not deleted by this command.

## Backup and recovery

Backups briefly stop the application, wait for in-flight workers, then use the
read-only `cv_backup` identity to export PostgreSQL and archive the public media,
private enquiry uploads and publication images together. The stream is encrypted
with age before reaching the host disk. The app is restarted even if encryption
fails. Only complete encrypted archives are retained. Allow a short maintenance
window; this is not a zero-downtime backup system. The temporary database dump
uses a 512 MB container tmpfs; increase that setting before the database exceeds
that size and ensure sufficient RAM. Check free disk/memory regularly.

Archives are in the configured backup directory, default
`/var/backups/techbullionhub/*.tar.age`. Copy encrypted files off the server after
each backup using a provider service or a separate scheduled transfer you
configure. Download one and decrypt it on your own computer to verify the key.
No archives are automatically deleted; choose retention based on your storage
and privacy requirements. A practical starting policy is 7 daily plus 4 weekly
encrypted copies; apply it to your off-server storage too. Deleted enquiries may
remain in retained archives until those archives expire. The 90-day enquiry
cleanup does not erase historical backups.

Keep a secure copy of the release source, `/etc/techbullionhub` and the image
identities separately. The application keys in that directory are needed for
continuity. Encrypt configuration backups too; never put them in Git.

Recover on an isolated fresh server first; never restore over a live database.
Disable timers/web while recovering. Decrypt with the offline key:

```sh
age -d -i /secure/offline/techbullionhub-recovery.agekey -o /secure/restore.tar /secure/backup.tar.age
mkdir -m 700 /secure/restored
tar -xf /secure/restore.tar -C /secure/restored
```

Use the same release's configure/build steps, restore the original protected
configuration/keys when available, start only `db`/`redis`, provision `fresh.sql`
and role passwords as in `install`, then use `pg_restore --exit-on-error` into
the **empty** `codeventra` database as `cv_init` using `restored/tmp/database.dump`.
The dump preserves `cv_owner`
ownership. Restore each directory below `restored/files/` to its matching named volume
with owner `10001:10002`; private directories require mode 0700. Reconcile
`deploy/postgres/grants.sql`, run `check`, then start web/proxy and verify public
article images and a private attachment through authenticated Admin. Delete
plaintext recovery files securely according to your storage policy afterwards.
The automated disposable rehearsal tests decryption, database restoration and
file hashes without touching development data.

## Updates and rollback

For later updates, keep a separate checkout of the approved commit; run the
release checks before deploying. Take an encrypted backup and preserve the
current `/etc/techbullionhub/compose.json` and exact images first. Review migration
compatibility before changing the image/migrating. This first-install command
does not pretend that arbitrary future database migrations are reversible.

If no schema migration has occurred, restoring the prior generated Compose file
and recreating web with `docker compose -p techbullionhub -f
/etc/techbullionhub/compose.json up -d --no-deps web` rolls back the app image.
After an incompatible schema change, recover the paired database/files backup
on an isolated server, verify it, then switch traffic. Never run `down --volumes`
or delete production volumes as a troubleshooting step.

## Local evidence and repeatable checks

```powershell
python scripts/test_release.py
```

The rehearsal creates a random, labeled project with separate volumes, generated
test secrets, loopback-only ports and a one-day self-signed test certificate. It
uses the same operator code and production images for first installation,
content import, real database roles/migrations, Redis, private socket proxy,
cleanup, age backup/decryption and PostgreSQL recovery. Certificate trust is
relaxed only in this isolated test; live `check` always verifies public TLS.
Cleanup validates ownership before removing QA resources. Your development stack
is not used. GitHub runs these checks for pushes and pull requests.

References: [Docker secret mounts](https://docs.docker.com/compose/how-tos/use-secrets/),
[Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/),
[Certbot webroot and renewal](https://eff-certbot.readthedocs.io/en/stable/using.html),
[age](https://github.com/FiloSottile/age).
