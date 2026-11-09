# TechBullion Hub SEO implementation — 8 November 2026

Owner-approved name: **TechBullion Hub**. Planned domain: **techbullionhub.net**.
The owner has not purchased the domain. Primary focus: software services,
supported by practical guides and technology news. Operator: Faizan Yousuf,
Lahore, Pakistan; public contact faize8042@gmail.com.

## Implemented

- Rebranded public templates, navigation, legal pages, metadata, email messages,
  organization/website structured data and favicon. Historical infrastructure
  identifiers and records remain unchanged to preserve existing volumes/services.
- Service-focused homepage title and description with the confirmed Lahore
  location. No invented clients, reviews, team credentials or traffic claims.
- Correct self-canonical URLs on valid paginated Blog/News lists. Tracking
  parameters are discarded; filtered/search variants remain noindex. Normal
  paginated archives can be indexed after the launch gate is enabled.
- Article publisher identity, breadcrumb structured data, language/section,
  author link to the visible Faizan Yousuf section, and social image/alt metadata.
- Published image responses become indexable only after explicit SEO activation;
  draft/future images remain inaccessible through the existing publication gate.
- Sitemap lastmod values use stored article/project modification timestamps.
  Static pages are not assigned invented last-modified dates.
- Read-only `audit_public_seo` command reports duplicate public article titles and
  descriptions, missing bylines and missing cover descriptions. It does not edit
  articles or inspect draft/future records.
- Default offline test runner now covers all eight application groups.

## Content plan for relevant enquiries

These are proposed original guides, not published articles or claims about search
volume. Write from actual implementation/testing experience; include examples,
screenshots, limitations and supporting sources where appropriate.

| Search intent | Proposed guide | Useful internal destination |
| --- | --- | --- |
| Choose a business website | Business website checklist for a small business in Pakistan | Services, Contact |
| Plan scope and budget | What determines the cost of a business website? | ScopeQuote demo; explain sample pricing |
| Choose software | Custom web application or an off-the-shelf tool: a decision checklist | Services, Projects |
| Solve stock problems | How to calculate reorder points with supplier lead times | StockPilot demo |
| Reduce double bookings | Designing an appointment booking flow that prevents conflicts | SlotDesk demo; state session-only limits |
| Improve site quality | A practical website launch checklist: forms, mobile use and backups | Services, Contact |
| Evaluate automation | Which repetitive business tasks are worth automating? | Automation services |
| Improve support | How to prioritize support requests using impact and urgency | ResolveDesk demo |

Start with two thoroughly reviewed guides and build on real reader questions.
Do not copy competitor articles, manufacture client case studies, mass-produce
unrelated posts, buy backlinks or promise rankings. For news, verify the original
source, link it directly, distinguish reporting from opinion and avoid publishing
the same article in both Blog and News. Review the existing similar AI articles
and generic SEO titles through Admin after the current database is available.

## Before enabling indexing

1. Purchase/control techbullionhub.net, deploy the application, and establish
   working HTTPS, DNS and a stable public origin. Choose apex as canonical;
   configure www to redirect to it on the real hosting server. The domain was not
   added to development ALLOWED_HOSTS and no DNS/registrar changes were made.
2. Configure the production host and CSRF settings using the deployment runbooks.
   Set `SEO_SITE_URL=https://techbullionhub.net` only for the verified deployment.
   Keep `SEO_INDEXING_ENABLED=False` until public checks and content review pass.
3. Run the read-only editorial audit:

   ```powershell
   docker compose -f compose.yaml -f compose.development-build.yaml exec -T web python manage.py audit_public_seo
   ```

4. Confirm unique titles/descriptions, canonical URLs, public images, bylines,
   private-route denials, mobile rendering and page performance on the live domain.
   Validate Article/Breadcrumb/Organization/WebSite markup in Google's Rich Results
   Test and check the sitemap contains only intentionally public content.
5. Enable `SEO_INDEXING_ENABLED=True` on the verified public deployment. Check
   `/robots.txt`, `/sitemap.xml`, page robots tags and image response headers.
   Keep temporary client snapshots noindex. This change does not index a tunnel.
6. Verify ownership in Google Search Console with a DNS TXT record, submit
   `https://techbullionhub.net/sitemap.xml`, and inspect the homepage and key
   service/article URLs. Search Console has not been configured in this task.
7. Monitor indexing, search queries, impressions, clicks and real enquiry quality.
   Review monthly; improve pages that answer relevant reader needs. Structured
   data, sitemap submission and technical fixes do not guarantee rankings or visits.

## Verification and deployment limit

116 isolated SQLite application tests passed after the final SEO changes,
including pagination/tracking/filter behavior, schema identity, image metadata,
launch gating, read-only editorial auditing, draft privacy and the existing security suites. System checks clean.
Browser checks on the isolated source preview confirmed distinct metadata, the
new brand, noindex, one H1 and no overflow at 390px on Home, Services, About,
Blog and News. The source preview had synthetic empty data, not existing articles.
Docker reports `Docker Desktop is unable to start`; the image could not be rebuilt,
PostgreSQL tests could not be repeated, and the primary Docker site was not updated.
The domain was inaccessible through the web reader and its ownership/live state
was not established. Temporary preview remains separate from a production release.

## Sources

- Google SEO Starter Guide: https://developers.google.com/search/docs/fundamentals/seo-starter-guide
- Helpful content: https://developers.google.com/search/docs/fundamentals/creating-helpful-content
- Site names: https://developers.google.com/search/docs/appearance/site-names
- Pagination: https://developers.google.com/search/docs/specialty/ecommerce/pagination-and-incremental-page-loading
- Article markup: https://developers.google.com/search/docs/appearance/structured-data/article
