# Codeventra Labs QA — 2 November 2026

## Confirmed repair

The expanded PostgreSQL verifier failed before test execution. Its sanitized
trace ended at Django's `call_command` argument validation. The helper supplied
`test_runner`, while the Django test command accepts `testrunner`. Correcting
that option allowed all 105 regression tests to execute successfully against a
random isolated PostgreSQL database, followed by database destruction.

The PowerShell verifier self-test still required the unsupported Compose `run
--no-build` option. It now rejects that option and retains the no-pull,
no-dependency-startup and disposable-container checks.

Unexpected helper exceptions now report frame filename, line and function only;
exception messages, source lines, locals and credentials remain withheld.
A focused regression test exercises Django's real command parser and verifies
all eight application labels reach the selected runner, without creating a DB.

## Executed checks

| Check | Actual result |
| --- | --- |
| Full development verifier | 19 PASS / 0 FAIL / 3 SKIP; exit 0 |
| Expanded PostgreSQL suite inside verifier | 105 tests passed |
| Independent PostgreSQL publishing suite | 12 tests passed |
| Python verifier diagnostic/command tests | 3 tests passed |
| PowerShell verifier self-tests | All groups passed |
| Offline main-site regression | 85 tests passed; system check clean |

Full verifier command: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify-publishing.ps1`.
Independent suite: `docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps --pull never web python manage.py test blog news publishing --noinput --verbosity 1`.
Local helper checks: `.venv/Scripts/python.exe -B -m unittest scripts.test_publishing_verifier` and
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_publishing_verifier.ps1`.
Main-site checks: `.venv/Scripts/python.exe -B scripts/test_launch_offline.py`.

## Browser user journeys

The live development site at http://127.0.0.1:8080 was inspected in Chromium
through the connected browser tools, separately from the verifier's unavailable
local Playwright installation.

- Home, Services, About, Projects, Contact, Blog, News, Privacy and Terms: checked
  at 390×844, 768×1024 and 1440×900 (27 page/viewport combinations). Each had one
  H1 and a main landmark, no detected horizontal overflow and no detected broken
  images. This is a focused responsive smoke check, not a full accessibility or
  cross-browser certification.
- Mobile menu opens and Blog navigation works.
- Blog search shows a useful no-results state; Reset restores published content.
- Published Blog and News links open detail pages with loaded cover images.
- News company filter shows the matching empty state; Reset restores the list.
- Contact navigation works; empty submission triggers native required-field
  validation and focuses Full name. No successful real enquiry or email was sent.
- Light theme switches and persists across navigation; restored dark theme.
- Portfolio currently has no published projects and displays its empty state.

Live HTTP probes also exercised navigation links, search/filter/pagination URLs,
anonymous Admin redirect, missing/hostile CSRF rejection, valid-origin empty
Admin form rendering, invalid Host rejection and missing private-storage URLs.
Draft/scheduled visibility, uploads, XSS, contact persistence/email-failure behavior
and permissions are covered by isolated tests, not real-record browser mutations.

One browser navigation batch timed out after 18 completed checks. State was
recovered, and all nine desktop checks completed separately.

## Small content correction

The Privacy page referred to an email address displayed on Contact, but Contact
has an enquiry form and no displayed email address. The source now links directly
to that form for privacy requests. Offline main-site tests passed afterward.
This template edit is not in the already-built running image; no image rebuild
or service restart was performed. Browser observations above concern that image.

## Remaining launch work

1. Owner inputs: domain/hosting, company identity/location, public contact channel,
   actual enquiry retention policy, applicable-law wording and real project case
   studies. Current legal pages retain operator notes requiring decisions.
2. Editorial review: current Blog and News use a similar topic and SEO title;
   confirm intended titles, original content, image rights and news source links.
   No existing records were edited and no news claims were fact-checked here.
3. Stage the final source in a reviewed image, including the Privacy fix. Current
   runtime and source-overlay checks do not establish complete image/source parity.
4. Isolated backup-and-restore rehearsal, persistent file recovery and production
   PostgreSQL role/ACL verification using the existing deployment runbooks.
5. Production domain/DNS/TLS, secure cookies, proxy checks, email deliverability,
   monitoring/alerts and rollback rehearsal on the actual target environment.
6. Full keyboard/screen-reader, measured contrast, cross-browser and performance
   audits, followed by final content review and controlled indexing activation.

The verifier still skips its local browser probe, production HTTPS/cookies and
historical credential/log review. Browser work above supplements only the first
skip; the saved verifier totals are unchanged. Production readiness is not claimed.
Existing services/data/volumes and unrelated uncommitted work were preserved.
