# Publishing security and QA verification

From Windows PowerShell 5.1 in `D:\TechWorldWebsite`, run:

```powershell
.\scripts\verify-publishing.ps1
```

The runner uses `compose.yaml` **and** `compose.development-build.yaml` with the
existing Compose project name/environment. Set `COMPOSE_PROJECT_NAME` to the
original project name if necessary. It does not install dependencies, start or
restart services, rebuild/pull images, apply application migrations, or change
credentials. Docker Desktop, Compose v2, an already running development stack,
and Python 3.10+ are prerequisites. The repository `.venv` is preferred. Django,
Pillow and the PostgreSQL driver must already be in the development image.

## Results and safety boundaries

* **PASS**: the named probe executed and its assertions succeeded.
* **FAIL**: a required assertion or prerequisite failed. Exit code is **1**.
* **SKIP**: unavailable or inapplicable; **NOT VERIFIED**, never a successful
  security assertion. Optional browser, real production HTTPS, historical log
  review, and live details when there are no public articles can be skipped.
* Exit code **0** means all required probes passed, not that skipped checks
  passed. The final totals count probe groups, not individual Django tests.

Docker failure is a required-prerequisite FAIL, with dependent groups SKIPped.
This prevents a workstation without Docker access from giving a green overall
result. Test identifiers/counts and controlled failure messages are displayed;
raw Docker errors, interpolated Compose output, HTTP bodies, DB exceptions and
test tracebacks are captured rather than echoed because they can contain secrets.
The runner never prints `.env`, resolved environment values or credentials.
Each helper must return both a zero exit code and its completion marker before
the runner reports PASS; an empty or interrupted probe cannot pass silently.

Runtime security, migration history/connectivity, and storage probes execute in
the **running web container**, using its deployed settings and code. The current
probe is supplied over stdin without writing files into that container.
Migration drift and the full Django suite run in a disposable `compose run
--rm --no-deps --pull never` web container with this checkout mounted read-only
at `/app`; no dependency or storage-init service is launched. This tests the
candidate checkout; it does not prove the image contains every current source
change. Live HTTP probes exercise the deployed image through Nginx.

The PostgreSQL tests use `config.verification_test_settings`, importing the real
development settings and retaining middleware/security behavior. Before Django
initializes, the helper supplies a random `test_publishing_qa_<uuid>` database
name and temporary image/media paths. It verifies that database name is absent
from `pg_database` before running tests. Django creates/migrates/drops only that
new test database; it never uses the default `test_<application-db>` name or
`--keepdb`. The development DB login needs `CREATEDB`; never grant that permission
to a production runtime role. Test setup/teardown does not manually close shared
connections. Existing image-streaming regression tests consume the response
iterator once, preserving PostgreSQL `TestCase` transactions.

Email uses Django's in-memory backend and test caches use process-local memory.
Existing contact tests mock delivery and validate attachment bytes in memory
without saving attachment files. No
real contact form is submitted. All publishing fixture content/users/images
exist only in the test DB and temporary storage. Application DB probes execute
SELECTs and inspect migrations; they do not migrate or alter application data.

Live probes are restricted to `http://127.0.0.1:8080`, reject cross-origin
navigation and redirects, and use GET requests plus **empty-credential Admin
login POSTs** to verify missing-token rejection, hostile-Origin rejection, and
valid same-origin CSRF acceptance through Nginx. Those POSTs only render login
validation errors: they do not log in, create sessions for an authenticated user,
modify content, or send email. Normal GETs may generate the site's usual access
logs/analytics. Do not point this development suite at production.

## Coverage

| Probe / test group | Verification | Requires Docker |
| --- | --- | --- |
| Source contracts | Nginx `$http_host` preserves port, forwarded scheme overwritten; publishing CSS responsive breakpoints exist | No |
| Live HTTP | Home, services, about, projects, contact, privacy, terms, blog, news, health, robots, sitemap, Admin login; internal navigation, search, filters, invalid/out-of-range page handling; published details and metadata where available | Running website; Docker CLI not needed |
| Live security | nosniff, frame denial, referrer policy; anonymous Admin redirect; hostile Host rejection; missing/hostile/valid CSRF; guessed public private-storage paths return 404 | Running website |
| Runtime Django | Required security/auth/CSRF/session middleware, explicit hosts, valid non-wildcard trusted origins, SameSite and HttpOnly session settings, development HTTP cookie/redirect/proxy profile; system checks | Yes |
| Config regression tests | Development origin/port failures and successes, trusted proxy spoofing defenses, production secret/DEBUG/host/origin/HTTPS/database/SMTP guards; production private-socket transport | Yes for PostgreSQL run |
| Authorization | Anonymous/non-staff/staff without model permissions cannot list/add/change/delete Blog or News through Admin; denial cannot mutate fixtures; public mutation verbs return 405; superuser editorial access; logout requires POST and CSRF and invalidates authentication | Yes |
| Publishing | Draft/future details and images hidden, publication boundary, published pages visible; search/category/kind/all-page visibility; private-only category not listed; malformed slug and query handling; plain-text XSS escaping for Blog and News | Yes |
| Images | PNG/JPEG/WebP acceptance; spoofed content, SVG, corrupt/oversized/pixel-bomb rejection; JPEG re-encoding, EXIF removal, randomized names; no direct storage URL; private/no-store responses; safe content type/nosniff; missing/traversal rejection; unpublishing immediately revokes image route | Yes |
| Storage | Effective web private named volume, persistence, ownership and mode 0700, web UID access, no symlinks or group/world writable children, no static/media overlap; private volume or its ancestors absent from Nginx mounts; Nginx config has no private publishing reference | Yes |
| PostgreSQL/migrations | PostgreSQL 17 connectivity, consistent applied history, no pending migrations, no installed-app model migration drift; all existing Django app tests on a unique isolated PostgreSQL DB | Yes |
| SEO | Existing SEO tests plus both publishing types: published sitemap inclusion, draft/future exclusion, details/metadata/canonical origin, escaped JSON-LD; configured robots/indexing behavior | Yes; live endpoints also checked |
| Contact and regressions | All tests in config, core, projects, contact, analytics, blog, news, publishing; existing form validation, attachment validation, rate limiting, branding, routes and privacy/SEO tests reused; enforced-CSRF contact rejection cannot send email or create a submission | Yes |
| Nginx/Compose | Resolved development config, Nginx syntax and loaded forwarding config, web/nginx running, PostgreSQL/Redis healthchecks healthy; no public DB/Redis binds in Compose or running containers | Yes |
| Browser layout | If Playwright + Chromium are available locally: home/blog/news at 390, 768, 1440 px; HTTP success, visible body/main heading, no horizontal overflow; third-party requests blocked | No CLI requirement; running website |

The development Compose PostgreSQL port bound to **127.0.0.1:5433** is accepted as
an existing local developer facility; Redis must have no published ports. Any
non-loopback datastore exposure fails. No port or mount is changed by the suite.
Root permissions protect private files even where files have normal read bits.
Image type validation trusts decoded bytes, not the upload's MIME claim; accepted
images are always served as newly encoded JPEGs. The model's 8 MB limit and
16-megapixel limit are exercised in isolation; Nginx's existing 6 MB request cap
can reject an upload earlier.

Browser checks are automated layout smoke tests, not a pixel-perfect visual or
accessibility audit. Missing Playwright **or** missing Chromium means SKIP / NOT
VERIFIED. CSS breakpoint presence alone never establishes working responsiveness.
To enable browser checks, install Playwright and its Chromium runtime in your
chosen local Python environment separately, then rerun the same command. The
runner never downloads a browser. Human review remains necessary for menus,
text wrapping, focus, touch interactions, image cropping and actual devices.

## Development HTTP versus production HTTPS

This entry point intentionally verifies local HTTP. It accepts development DEBUG
as a boolean and reports its current state. It requires the HTTP development
profile (no secure-only cookies/SSL redirect/trusted TLS header). It does **not**
turn off security settings, override the deployed security profile or treat
Django's HTTP-specific `check --deploy` warnings as proof of a vulnerability.
Production guard regressions run with synthetic settings in isolated tests.
Existing production settings/checks are not modified.

On the real TLS deployment, separately verify certificate chain/name/expiry,
HTTP-to-HTTPS redirects, session/CSRF Secure and SameSite attributes, session
HttpOnly, real origins, public ALLOWED_HOSTS, private proxy transport and forwarded
scheme trust, direct upstream inaccessibility, caching and cookie behavior, and
run `manage.py check --deploy` with the **actual production environment**. Review
the existing staged HSTS/indexing policy before enabling either; the suite does
not enable them. Local HTTP cannot certify TLS, secure-cookie transport or HSTS.
Production HTTPS checks remain SKIP in this runner.

## Troubleshooting

* Docker inaccessible: open Docker Desktop and use a PowerShell session with
  access to its engine. Verify `docker info` and `docker compose version` locally.
  Never paste raw Docker/config output containing environment interpolation.
* Compose config fails: check `.env` variable **presence privately**, both Compose
  file paths, and the original project name. Do not print or attach `.env`.
* Container missing/unhealthy: investigate the existing deployment separately.
  The runner will not start, repair, restart or rebuild it. Web/nginx have no
  configured Docker healthcheck; their running state and live HTTP are checked.
* Pending migrations: review `docker compose -f compose.yaml -f
  compose.development-build.yaml exec -T web python manage.py migrate --check`.
  Plan migration application separately; do not add automatic migration to QA.
* Drift: review `python manage.py makemigrations --check --dry-run` using the
  correct development environment. This covers all installed models, not only
  Blog/News. No migration files are generated by the runner.
* PostgreSQL test failure: inspect the reported failing test identifiers; check
  PostgreSQL 17, test-DB creation privileges, installed image dependencies and
  read-only checkout compatibility. A missing privilege is a FAIL, never a
  fallback to SQLite. A forced interruption can leave the printed-prefix test
  database behind; identify its ownership/name and remove it only after manual
  review. The suite never drops arbitrary existing databases.
* Storage failure: compare volume mounts and UID with
  `docs/development-publishing-storage.md`. Correct ownership/permissions through
  the normal deployment procedure; the verifier never chmods/chowns files.
* Live 403 on valid Admin CSRF: inspect the Nginx Host forwarding contract and
  confirm it includes port 8080. Do not fix this by adding wildcard origins.
* Test diagnostics: for detailed tracebacks, run the reported test identifier in
  a separately isolated test environment and inspect output privately. Avoid
  running ad-hoc tests with a predictable test DB name and `--noinput`.

When Docker is unavailable, these commands still give useful **offline** checks:

```powershell
python manage.py test --settings=config.publishing_test_settings --noinput --verbosity 1
python manage.py check --settings=config.publishing_test_settings
python manage.py makemigrations --check --dry-run --settings=config.publishing_test_settings
python scripts/publishing_verify.py source
```

They use SQLite in memory, not PostgreSQL, and cannot replace container/runtime
verification. After fixing Docker access, run the complete PostgreSQL/container
suite with the original single command:

```powershell
.\scripts\verify-publishing.ps1
```

## Remaining manual security work

Disposable drift/test containers use the existing image without rebuilding or
pulling it. The verifier overlays individual checkout files with temporary
read-only bind mounts: both Python verification helpers, PostgreSQL verification
settings, all `test*.py` files under the eight tested application packages, and
the Nginx/Gunicorn configuration read by those tests. This includes security
tests and `core.test_seo`, which they import. It does not mount `/app` or replace
application package directories; application code and migrations come from the
installed image. Missing mount sources fail before container launch. Changes to
application code still require an appropriately current image, outside this
verification command; this helper/test-source fix requires no image rebuild.
Drift uses `makemigrations --check --dry-run`; regression tests retain the random
`test_publishing_qa_<uuid>` PostgreSQL database and temporary media/storage roots.

Review historical application/Nginx/collector logs in their access-controlled
location for credential, session, CSRF token, personal-data or database-URL
leakage; verify log retention, redaction, access controls and backup permissions.
Do not export raw logs to QA artifacts. An isolated failed-login regression
checks that synthetic credentials do not reach Python log records, but this
does not certify historical logs or downstream collectors. Historical log audit
is explicitly SKIPped by the runner. Review production TLS, real staff role
assignment, operational backup/restore procedures, external dependency CVEs and
manual mobile/accessibility behavior separately. No suite proves absence of all
vulnerabilities.
