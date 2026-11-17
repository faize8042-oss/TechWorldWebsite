# TechBullion Hub

A Django website for software development services, practical technology articles,
company news, and interactive portfolio demonstrations.

**Operator:** Faizan Yousuf · Lahore, Pakistan

**Public contact:** faize8042@gmail.com

## Deploy after purchasing hosting

The supported release targets a fresh Ubuntu 24.04 amd64 VPS with Docker support.
The [deployment guide](deploy/release/README.md) provides the configuration fields
and ready-to-run commands for installation, HTTPS, public content, encrypted
backup, retention schedules and verified search indexing. Production dependencies
are hash-locked separately from the development dependency ranges.

The project previously used the name **Codeventra Labs**. Some Docker images,
volumes, scripts, and historical documents retain the earlier names for continuity.

## Features

- Home, Services, About, Projects, Contact, Privacy, and Terms pages.
- Blog and News with search, filters, pagination, drafts, and scheduled publication.
- Django Admin for editorial content, projects, and enquiries.
- Private contact attachments and controlled delivery of published article images.
- Contact email notifications, validation, and rate limiting.
- Responsive layouts, keyboard focus styles, and light/dark themes.
- Page metadata, canonical URLs, sitemap, breadcrumbs, and article structured data.
- Four browser-session demos: inventory planning, appointment scheduling,
  quotation building, and support-request prioritization. These use sample data.
- Read-only SEO auditing and an explicit 90-day unanswered-enquiry cleanup command.

## Technology

| Component | Technology |
| --- | --- |
| Application | Python, Django 5.2 |
| Frontend | Django templates, HTML, CSS, vanilla JavaScript |
| Database | PostgreSQL 17 |
| Cache | Redis 7 |
| Web serving | Gunicorn, Nginx, WhiteNoise |
| Local environment | Docker Desktop and Docker Compose |

The Docker image uses Python 3.12. Dependency ranges are in
[`requirements.txt`](requirements.txt). This project does not use React or Next.js.

## Local setup

Install Git and Docker Desktop with Linux containers enabled. Examples below use
Windows PowerShell from the repository root.

```powershell
git clone https://github.com/faize8042-oss/TechWorldWebsite.git
Set-Location TechWorldWebsite
Copy-Item .env.example .env
```

For a fresh checkout, edit `.env` and replace the example database password,
`SECRET_KEY`, analytics secret, and email values. Keep `.env` private; never commit
credentials. Configure SMTP before relying on real enquiry notifications.

Build and start the development stack:

```powershell
docker compose -f compose.yaml -f compose.development-build.yaml build web
docker compose -f compose.yaml -f compose.development-build.yaml up -d
```

On the new installation, initialize the database and create an administrator:

```powershell
docker compose -f compose.yaml -f compose.development-build.yaml exec web python manage.py migrate
docker compose -f compose.yaml -f compose.development-build.yaml exec web python manage.py createsuperuser
```

For an existing installation, back up the database and private uploads before
applying migrations. Keep the original Compose project name so existing volumes
remain attached. Do not use `docker compose down -v` to update the website.

Open:

- Website: <http://127.0.0.1:8080/>
- Administration: <http://127.0.0.1:8080/admin/>
- Blog: <http://127.0.0.1:8080/blog/>
- News: <http://127.0.0.1:8080/news/>

PostgreSQL is available on loopback port `5433` in the development Compose file.
Containers use the Compose database connection configured for the web service.
Development uses `DEBUG=True`; use the separate production configuration for launch.

## Testing

### Full development verification

With Docker Desktop and the existing development services running:

```powershell
.\scripts\verify-publishing.ps1
```

The verifier checks live routes, CSRF, container configuration, migration drift,
private storage, and regression tests in a randomly named PostgreSQL test database.
It does not migrate the application database. `SKIP` means **not verified**.

### Offline application tests

Create a local Python environment and install dependencies if needed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B scripts/test_launch_offline.py
```

The offline runner uses synthetic settings, an in-memory SQLite database, local
cache, and in-memory email. It does not read `.env` or contact the development
database, Redis, or SMTP. It does not replace PostgreSQL runtime verification.

**Release package validation — 17 November 2026:** 123 application tests and 22
operator/credential checks passed with the locked production dependencies. A fresh
production-stack rehearsal passed, including PostgreSQL roles, HTTPS/private socket
routing, content/image import, encrypted backup recovery and failed-backup restart.
See the [deployment package report](docs/deployment-package-2026-11-17.md).

**Development verification — earlier on 17 November 2026:** 116 PostgreSQL tests passed; full live
verifier 19 PASS / 0 FAIL / 3 SKIP. Docker recovered and the latest branding/SEO
changes now run locally. Browser journeys, a development DB restore and disposable
production-image-storage checks also passed. See the
[current readiness report](docs/release-readiness-2026-11-17.md) for scope and limits.

## Editorial and operational tools

Read-only public-content SEO audit:

```powershell
docker compose -f compose.yaml -f compose.development-build.yaml exec -T web python manage.py audit_public_seo
```

Preview unanswered-enquiry retention candidates without deleting anything:

```powershell
docker compose -f compose.yaml -f compose.development-build.yaml exec -T web python manage.py cleanup_unanswered_enquiries
```

The cleanup command requires `--apply` to delete eligible records. Read the
[retention guide](docs/enquiry-retention.md) before scheduling or applying it.

## SEO and deployment status

SEO changes are implemented in source. Search indexing remains disabled until a
verified public HTTPS deployment is available. Do not enable indexing on temporary
client-preview tunnels.

After purchasing and configuring the domain, follow the
[SEO and content plan](docs/techbullionhub-seo-plan.md) to verify canonical URLs,
structured data, Search Console ownership, and sitemap submission.

The [release package](deploy/release/README.md) automates deployment, HTTPS setup,
backup and retention schedules, and verified indexing. Configure the purchased
hosting/domain, sender credentials and backup destination, then run its supplied
commands. Actual certificate issuance, inbox delivery, provider monitoring and
off-server recovery verification still depend on those services. No production
site has been deployed while hosting and the domain remain unpurchased.

Temporary client previews export public pages into a read-only snapshot. Admin,
private files, and enquiry submissions are unavailable there; interactive demos
use page-session sample data. A tunnel link lasts only while its server and tunnel
processes are running.

## Further documentation

- [Deployment configuration and launch](deploy/release/README.md)
- [Verified deployment package](docs/deployment-package-2026-11-17.md)
- [Development readiness snapshot](docs/release-readiness-2026-11-17.md)
- [Latest SEO implementation and content plan](docs/techbullionhub-seo-plan.md)
- [Publishing editorial guide](docs/publishing-editorial-guide.md)
- [Publishing verification](docs/publishing-security-verification.md)
- [Development build guide](docs/development-image-build.md)
- [Private publishing storage](docs/development-publishing-storage.md)
- [Enquiry retention](docs/enquiry-retention.md)
- [Portfolio demo checks](docs/portfolio-demo-qa.md)
- [Production readiness](docs/production-readiness.md)
- [Deployment handoff](docs/deployment-handoff.md)

Historical reports describe the state on their recorded dates. Current source
and fresh test results take precedence.
