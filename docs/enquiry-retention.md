# Unanswered enquiry retention

Owner: Faizan Yousuf, Codeventra Labs, Lahore, Pakistan.
Owner-approved policy: 90 days for unanswered enquiries and attachments.

The app represents unanswered enquiries with status **New**. Move an enquiry to
**In progress** when responding or starting work. There is no mailbox integration
that can detect an email reply automatically. Cleanup requires both creation and
last update to be more than 90 days old, and preserves In progress/Completed rows.

Preview eligible records (no deletion):

```powershell
docker compose -f compose.yaml -f compose.development-build.yaml exec -T web python manage.py cleanup_unanswered_enquiries
```

The `--apply` option explicitly deletes eligible records. It is not invoked by
startup, tests against real data, or this handover. No real enquiries were deleted.
Private attachment deletion runs after the row transaction commits; a file still
referenced by another enquiry is retained. If file removal fails, the command
fails with a sanitized error; review private storage because the row is already
deleted. This is not a transaction across database and filesystem.

Before production, review the dry-run count and configure an operator-owned daily
job for `python manage.py cleanup_unanswered_enquiries --apply` in the production
web environment. Alert on nonzero exit. No scheduler is installed locally and no
production schedule is claimed. Test with disposable records before enabling it.

The policy does not remove copies already delivered by email or present in
backups. The operator must set corresponding mailbox and backup retention and
verify removal after expiry. Active/completed project retention and legal holds
need a separate documented decision before launch.
