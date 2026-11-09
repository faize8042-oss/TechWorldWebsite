# Blog and News editorial guide

## Editorial workflow

Use Django Admin with individual staff accounts and the appropriate Blog/News model permissions. Create a category before a Blog post; category deletion is protected while posts reference it. News requires either Company announcements or Industry news. No articles, identities, announcements or partnerships are seeded.

Enter a title, unique stable slug, summary and plain-text body. HTML is escaped, not rendered. The optional author field is an approved public display name, never an email or a user-account relation. Do not enter confidential information in any public field. SEO title and description are optional; title and summary provide fallbacks.

Draft is the default. To publish, select Published and provide a publication date. Published items with dates in the future are scheduled automatically; no cron job is needed. The website uses timezone-aware server time (normal settings: UTC). A date equal to or before the current time makes a Published item public. Switching to Draft immediately prevents subsequent detail and image requests. Slug changes break old links; there are no automatic redirects. Admin indicates Draft, Scheduled or Public and supports search, date hierarchy and filtering. There are deliberately no bulk publish actions bypassing validation.

## Images and privacy

Optional cover images require descriptive alternative text. Upload JPEG, PNG or WebP images no larger than 8 MiB and 16 million pixels. Images are decoded, EXIF orientation applied, resized to at most 2400 by 2400 and re-encoded as JPEG without original metadata or filenames. Animated images become a single static frame. Transparency is converted to RGB.

PublishingStorage defaults to BASE_DIR/private_publishing, separate from MEDIA_ROOT and Contact attachments. An operator can configure PUBLISHING_IMAGE_ROOT in Django settings to an existing persistent private directory. It must remain outside any publicly served or collected directory, with no web server alias. No deployment files or Contact storage were changed. Production persistence and permissions must be provisioned by the operator before image uploads are used.

Templates and admin do not use storage URLs. Public image routes look up a currently public article on every GET/HEAD and return JPEG with private, no-store cache headers. Unpublishing prevents subsequent access; previously downloaded copies cannot be recalled. Configure any upstream cache to honor no-store. Listing, detail and sitemap responses also prohibit storage. Original image paths have no public route. Replaced/deleted image files are retained privately to avoid unsafe deletion during transactions; operator-reviewed orphan cleanup and backup retention are separate maintenance tasks.

## Website behavior

/blog/ and /news/ provide search over title, summary and body, category/type filters and nine articles per page. Invalid page inputs are handled by Django pagination. Pagination retains filters. Empty states do not invent content. Detail bodies and metadata are escaped, and JSON-LD script delimiters are escaped. No account emails are queried or serialized.

SEO uses the existing explicitly configured HTTPS origin and indexing switch. Published articles appear in sitemap.xml only when indexing is enabled. Article metadata and BlogPosting/NewsArticle JSON-LD use approved public fields. Search/filter/pagination pages request noindex. The standalone preview adds only empty Blog/News listing pages and navigation; its dummy database, method restrictions, host restrictions and private-path boundary remain in force. Preview never imports the publishing models.

## Review and isolated validation (PowerShell)

```powershell
git status --short
git diff -- config/settings.py config/urls.py config/preview.py config/preview_urls.py core/seo.py core/test_seo.py templates/includes/navbar.html templates/includes/footer.html
Get-ChildItem publishing,blog,news,templates/publishing -Recurse
.venv\Scripts\python.exe manage.py check --settings=config.publishing_test_settings
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.publishing_test_settings
.venv\Scripts\python.exe manage.py sqlmigrate blog 0001 --settings=config.publishing_test_settings
.venv\Scripts\python.exe manage.py sqlmigrate news 0001 --settings=config.publishing_test_settings
.venv\Scripts\python.exe manage.py test --settings=config.publishing_test_settings --noinput
.venv\Scripts\python.exe scripts/test_client_preview.py
.venv\Scripts\python.exe scripts/test_client_preview_security.py
```

The isolated settings never import normal settings, read .env or connect to the existing database; the test runner applies all migrations only in a disposable in-memory SQLite database. Initial migrations are blog/migrations/0001_initial.py and news/migrations/0001_initial.py. PostgreSQL integration, real-browser layout review, live admin upload testing and deployment persistence have not been validated. Do not apply migrations to existing databases as part of this review. A future operator-approved rollout must apply blog before creating blog content and apply news before creating news content.
