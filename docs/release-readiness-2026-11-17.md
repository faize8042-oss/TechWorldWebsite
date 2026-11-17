# TechBullion Hub release readiness — 17 November 2026

## Current result

Latest branding, copy and SEO source is built and running at
http://127.0.0.1:8080/. Docker recovered after a normal Desktop restart; no reset,
application migration or development volume deletion occurred. The owner confirmed
that domain and hosting are still unpurchased. Production launch remains pending.
Rollback image: `techworld-django:before-techbullionhub-20261117`.

## Completed

- Activated TechBullion Hub branding, favicon, service-focused copy and SEO changes.
- Corrected duplicate SEO metadata on two published development articles after
  backing up their public metadata under ignored validation-results. URLs, bodies
  and original publication dates were preserved. Database edits do not transfer
  through Git; export/review them as part of content migration before launch.
- Fixed Skip to content so the main landmark receives keyboard focus; updated
  preview-notice insertion for the extra HTML attribute.
- Added persistent private Blog/News image storage to the proposed production
  Compose, with an explicit operator initializer and no Nginx mount. The initializer
  has no network or credentials and only the CHOWN capability.
- Verified storage ownership/mode and non-root writes using a disposable volume.
  A PowerShell quoting issue initially prevented cleanup; the exact labelled QA
  volume was inspected/removed, and the corrected test passed automatic cleanup.
- Updated the production source-test parser to recognize hyphenated service names;
  existing network, secret and socket assertions remain enforced.
- Excluded unrelated local portfolio work/archive from website image builds.
- Refreshed the read-only client snapshot with the current site. Public pages,
  images and browser-session tools are included; Admin/private routes and POSTs
  are denied. Enquiry/search/filter forms are disabled and noindex is enforced.
  The initial Quick Tunnel request timed out; a retry produced a verified link.

## Executed verification

| Check | Actual result |
| --- | --- |
| Full live publishing verifier | 19 PASS / 0 FAIL / 3 SKIP; exit 0 |
| Isolated PostgreSQL regression | 116 passed; temporary test DB destroyed |
| Production storage/credential source tests | 15 passed |
| Production Compose schema | config --no-interpolate --quiet passed |
| Production storage runtime | Disposable volume mode 0700, UID/GID 10001:10002 and non-root writes passed; QA volume removed |
| Public article SEO audit | 2 articles; 0 reported issues after metadata correction |
| Real development database restore | Custom archive restored into random QA DB; six key table counts matched; QA DB/archive removed |
| Browser responsive checks | 15 pages × 390/768/1440px = 45 combinations; no detected overflow/broken images/incorrect H1 counts |
| Browser user journeys | Mobile menu/Escape, Blog search/reset, enquiry validation and all four demos passed |
| Keyboard skip navigation | Main landmark receives focus |
| Themes and console | Both themes work; no captured console errors during reviewed journeys |
| Basic local homepage timing | Median 34.5ms across five responses; local smoke measurement only |
| Production-style compression | DEBUG=False hashed CSS served with gzip in isolated container: 1,878 bytes vs 6,360 source bytes |
| Public preview HTTPS boundary | Main pages/demo/JS 200; Admin/.env/private uploads 404; contact POST 405; noindex verified |

The verifier still skips its unavailable local Playwright probe, production
TLS/cookies, and historical credential/log review. Connected-browser checks above
supplement the first skip without changing verifier totals. This is not a full
screen-reader, cross-browser, contrast or Web Vitals certification.

`scripts/test-development-restore.ps1` dumps the development DB, restores to a new
random QA DB, compares migration/user/project/Blog/News/enquiry counts, and removes
only its temporary copy/archive. No record values are printed. This validates DB
recovery locally, not production least-privilege roles or private-file recovery.

`scripts/test-production-publishing-storage.ps1` uses the initializer from the
production Compose on a uniquely labelled QA volume, never existing private storage.
No real enquiry cleanup or email sending occurred in this session.

## Remaining production launch gates

1. Purchase/control techbullionhub.net and hosting; deploy reviewed immutable
   images/dependencies with protected production settings and secrets.
2. Verify production DB roles/migrations/storage, private image/attachment delivery
   and paired database-and-files restoration from encrypted off-host backups.
3. Configure DNS/canonical redirects/TLS/renewal/proxy and check secure cookies,
   HTTPS redirects, real SMTP delivery, monitoring, alerts and rollback.
4. Install backup and 90-day enquiry cleanup schedules. Commands exist, but no
   production scheduler or mailbox/backup retention policy has been activated.
5. Review article facts/sources/image rights and legal text. SEO audit success is
   not fact-checking. Tools remain demonstrations without invented client results.
6. Complete final public-host accessibility/cross-browser/performance checks, then
   enable indexing, verify Search Console and submit the sitemap.

## Client preview

The refreshed snapshot is under ignored
`validation-results/client-share-20261117-1`, served on loopback port 8766.
Its public Quick Tunnel was verified during this session and requires the computer,
internet connection and snapshot/tunnel processes to remain active. It is not
permanent hosting. No unrelated portfolio files or archives were modified.
