# Local development release — 2 November 2026

Website: http://127.0.0.1:8080/ (local computer only).

## Implemented and activated

- Rebuilt development image, collected 141 static files, replaced only web.
  PostgreSQL, Redis, Nginx and existing database/upload volumes were preserved.
- Main page wording, Lahore location, public email, operator Faizan Yousuf,
  owner-approved 90-day unanswered-enquiry policy and privacy contact link.
- Four working browser-session demos on Projects; no invented client work.
- Demo fields now follow both themes; favicon added; demos included in gated
  sitemap. Indexing remains disabled until public deployment is verified.
- Removed unfinished operator instructions from public Terms. General website
  terms still need business/legal review; no statutory compliance claim is made.
- Default-read-only unanswered-enquiry cleanup command, explicit --apply mode,
  private attachment cleanup and regression tests. No real deletion was run.
- Build/Git exclusions now also cover private publishing storage and local test
  error logs. No credentials or private records are included in release notes.

## Actual checks

- Expanded PostgreSQL regression: 111 tests passed, isolated random test DB removed.
- Full verifier: 19 PASS / 0 FAIL / 3 SKIP, exit 0.
- Offline main-site regression: 91 tests passed, system checks clean.
- Verifier Python diagnostics/parser tests: 3 passed; PowerShell self-tests passed.
- Live HTTP: public pages, internal links, search/filter/pagination, article details,
  Host rejection, anonymous Admin and CSRF behavior passed through Nginx.
- Browser: updated portfolio visible in actual Docker site; inventory result
  correct; light fields use RGB 246/248/255 background and 21/27/50 text. Prior
  isolated browser checks exercised all demos, reset, duplicate-booking rejection,
  safe text rendering and 390px layouts (see portfolio-demo-qa.md).
- Synthetic recovery drill: custom pg_dump archive created/listed/restored;
  two fixture rows validated; two random QA databases and temporary archive removed.
  This does not validate the older real backup, private-upload recovery,
  encryption/off-host custody or production least-privilege roles.

An initial sitemap expectation mismatch was corrected to explicitly include the
four new demo paths. Windows blocked temporary file access in one restricted test
run; rerunning with appropriate access passed. No failure was counted as a pass.

## Rollback

The previous image is retained as
`techworld-django:before-portfolio-update-20261102`. It was preserved before any
development image replacement. No database migration was applied by this release.
Rolling back requires selecting that image and recreating only web using a reviewed
Compose override. Do not delete volumes or roll back Blog/News migrations.

## Still required before public launch

1. Domain and hosting purchase, final production environment and reviewed immutable
   dependency/image versions. Development DEBUG=True is not a production release.
2. Production DB role/ACL/migration verification, real paired DB/private-upload
   restore rehearsal, encrypted off-host backups and recovery alerts.
3. Domain/DNS/TLS/renewal, secure cookies/proxy, SMTP delivery and sender checks,
   monitoring, rollback rehearsal and end-to-end production smoke tests.
4. Schedule and monitor retention cleanup. Mailbox/backups/logs/active-project
   retention must be decided separately; the cleanup command is not a scheduler.
5. Editorial/image-rights/source review for Blog/News and business review of legal
   text. Published article records were preserved. Team/client claims need evidence.
6. Complete cross-browser, keyboard/screen-reader, measured contrast and performance
   audits on the final public environment; enable indexing only after launch checks.

The verifier's browser probe still skips because local Playwright is unavailable;
connected-browser checks supplement it. Production TLS/cookies and historical
credential/log review remain unverified. Production readiness is not claimed.
