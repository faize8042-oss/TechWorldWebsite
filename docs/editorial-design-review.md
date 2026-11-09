# Focused editorial design update — 2 November 2026

Reference: https://techbullion.com/.

Reviewed the live homepage, Artificial Intelligence category, article detail,
story groupings and mobile category layout using both the web reader and browser.
The browser initially showed a security check, then loaded normally without
intervention. Reference content, branding, images and source code were not copied.

## Scope chosen

TechBullion's editorial hierarchy fits Codeventra Labs' Blog and News sections.
Those listings and article pages were updated, keeping the software-services
homepage, Services, About, Contact, portfolio demos, main navigation and backend
security behavior intact. No newsletter subscription, advertising, social account
or popularity claims were introduced.

- Large section titles and visible reading-section navigation.
- Leading story with a larger image/headline treatment; simpler article cards,
  compact category/date labels, author and estimated reading time.
- Restrained separators, fewer rounded panels and an exploration sidebar.
- Article headings, summary, author/date/read-time metadata and comfortable
  reading width with links to other public articles when available.
- Both themes retained; scoped dark-blue category labels in light theme and
  visible keyboard focus styling.
- Sidebars stack below the main content on small screens. Existing search,
  category/type filters, pagination, empty states, escaping and private images
  remain in place. Reading time uses a 220-word/minute estimate.

Related links always use the existing public publication queryset and exclude the
current article. Draft and scheduled visibility are covered by a new regression
test. No database migration or real content-record edit was required.

## Verification

- Main-site offline suite: 91 passed (Windows temporary-file access required).
- Expanded isolated PostgreSQL suite: 112 passed; temporary test DB destroyed.
- Full verifier: 19 PASS / 0 FAIL / 3 SKIP, exit 0.
- Connected browser checked Blog/News listing and both existing published detail
  pages at 390, 768 and 1440px widths: 12 combinations, one H1 per page, no
  detected horizontal overflow or broken images.
- Live HTTP checks exercised internal navigation, search, filters, pagination,
  article details and CSRF behavior. Visual inspection covered both themes.

The verifier's local Playwright probe still skips; connected browser checks above
were performed separately. Production TLS/cookies and historical log review remain
unverified. The reference has many more articles than the current site; no fake
stories, most-read statistics or editor selections were added to fill space.
