# Local development recovery drill. Reads the application DB, restores a temporary
# copy inside the existing PostgreSQL container, then removes only that QA copy.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$id = [Guid]::NewGuid().ToString('N')
$script = @'
set -eu
case "$1" in *[!0-9a-f]*|'') exit 1;; esac
test "${#1}" -eq 32
restore_db="qa_dev_restore_$1"
archive="/tmp/qa_dev_restore_$1.dump"
export PGPASSWORD="$POSTGRES_PASSWORD"
export PGUSER="$POSTGRES_USER"
test ! -e "$archive"
test "$(psql -d postgres -At -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM pg_database WHERE datname='$restore_db';")" = 0
created=0
cleanup() {
  if test "$created" = 1; then dropdb "$restore_db" >/dev/null 2>&1; fi
  rm -f "$archive"
}
trap cleanup EXIT
counts='SELECT (SELECT count(*) FROM django_migrations), (SELECT count(*) FROM auth_user), (SELECT count(*) FROM projects_project), (SELECT count(*) FROM blog_blogpost), (SELECT count(*) FROM news_newsitem), (SELECT count(*) FROM contact_contactsubmission);'
before=$(psql -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 -c "$counts")
pg_dump -Fc -f "$archive" "$POSTGRES_DB"
pg_restore --list "$archive" >/dev/null
createdb --template=template0 "$restore_db"
created=1
pg_restore --exit-on-error --no-owner --no-acl -d "$restore_db" "$archive"
restored=$(psql -d "$restore_db" -At -v ON_ERROR_STOP=1 -c "$counts")
after=$(psql -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 -c "$counts")
test "$before" = "$after"
test "$restored" = "$before"
dropdb "$restore_db"
created=0
rm -f "$archive"
trap - EXIT
printf 'QA_DEVELOPMENT_RESTORE_COMPLETE\n'
'@
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $output = @($script | docker compose -f (Join-Path $root 'compose.yaml') -f (Join-Path $root 'compose.development-build.yaml') exec -T db sh -s -- $id 2>&1)
    $code = $LASTEXITCODE
} finally { $ErrorActionPreference = $previous }
if ($code -ne 0 -or $output -notcontains 'QA_DEVELOPMENT_RESTORE_COMPLETE') {
    throw 'Development restore drill failed; raw output withheld. Check QA cleanup and concurrent source writes privately.'
}
Write-Host 'PASS: development DB archive restored; six key table counts matched; QA database and archive removed. Application DB unchanged.'
