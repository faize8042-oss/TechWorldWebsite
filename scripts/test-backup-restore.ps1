# Synthetic recovery rehearsal on the existing DEVELOPMENT PostgreSQL engine.
# Creates two random QA databases only; does not read or dump the application DB.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$root = Split-Path -Parent $PSScriptRoot
$id = [Guid]::NewGuid().ToString('N')
$script = @'
set -eu
case "$1" in *[!0-9a-f]*|'') exit 1;; esac
test "${#1}" -eq 32
source_db="qa_backup_$1"
restore_db="qa_restore_$1"
archive="/tmp/qa_backup_$1.dump"
export PGPASSWORD="$POSTGRES_PASSWORD"
export PGUSER="$POSTGRES_USER"
cleanup() {
  dropdb --if-exists "$restore_db" >/dev/null 2>&1
  dropdb --if-exists "$source_db" >/dev/null 2>&1
  rm -f "$archive"
}
trap cleanup EXIT
createdb --template=template0 "$source_db"
psql -d "$source_db" -v ON_ERROR_STOP=1 -c "CREATE TABLE qa_items (id integer PRIMARY KEY, label text NOT NULL); INSERT INTO qa_items VALUES (1, 'synthetic-one'), (2, 'synthetic-two');" >/dev/null
pg_dump -Fc -f "$archive" "$source_db"
pg_restore --list "$archive" >/dev/null
createdb --template=template0 "$restore_db"
pg_restore --exit-on-error --no-owner --no-acl -d "$restore_db" "$archive"
test "$(psql -d "$restore_db" -At -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM qa_items WHERE (id=1 AND label='synthetic-one') OR (id=2 AND label='synthetic-two');")" = 2
dropdb "$restore_db"
dropdb "$source_db"
rm -f "$archive"
trap - EXIT
printf 'QA_BACKUP_RESTORE_COMPLETE\n'
'@
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $output = @($script | docker compose -f (Join-Path $root 'compose.yaml') -f (Join-Path $root 'compose.development-build.yaml') exec -T db sh -s -- $id 2>&1)
    $code = $LASTEXITCODE
} finally { $ErrorActionPreference = $previous }
if ($code -ne 0 -or $output -notcontains 'QA_BACKUP_RESTORE_COMPLETE') {
    throw 'Synthetic recovery rehearsal failed. Raw service output withheld; inspect temporary QA database cleanup privately.'
}
Write-Host 'PASS: synthetic database dump, archive listing, restore, row validation and temporary database/archive cleanup.'
