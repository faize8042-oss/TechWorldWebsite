# Development private publishing storage

Use only `compose.yaml` plus `compose.development-build.yaml`, from the repository
root and with the existing Compose project name. Retain any original `-p NAME`
or `COMPOSE_PROJECT_NAME` setting for every command. A different project name
selects different named volumes, including PostgreSQL storage.

Blog and News use `PublishingStorage` at `/app/private_publishing`. The override
mounts the project-scoped `private_publishing` named volume there. A one-shot
`publishing-storage-init` service uses the already-built development image as
root, without network access or application environment, to set the volume root
to UID/GID 10001 and mode 0700. Web waits for successful completion. The initializer
does not recursively change existing files or remove anything. Existing imported
files must also be readable/writable by UID 10001; inspect their ownership before
enabling uploads if importing an existing collection.

The volume survives web container replacement. Nginx has no mount of it and its
`/media/` alias still points only to the public `./media` bind mount. Publishing
delivery continues through Django's publication checks. Contact's
`./private_uploads:/app/private_uploads` bind mount is unchanged. PostgreSQL's
`postgres_data` volume is unchanged. Redis has no configured volume in the base
file; its existing configuration is preserved. Production files are unchanged.

## Before any future web replacement

These are operator commands, not a request to restart services or apply migrations.
If the old web container contains publishing uploads in its writable layer,
mounting the new volume will hide those files in the replacement container.
Inspect and preserve them first. The following copy is read-only for the running
container and writes a uniquely named local backup (skip the copy only if the
directory is confirmed absent):

```powershell
$webId = docker compose -f compose.yaml ps -q web
if ($LASTEXITCODE -ne 0 -or -not $webId) { throw 'Expected running web container.' }
docker exec $webId python -c "from pathlib import Path; p=Path('/app/private_publishing'); print('exists:', p.exists()); print('files:', sum(1 for f in p.rglob('*') if f.is_file()) if p.exists() else 0)"
if ($LASTEXITCODE -ne 0) { throw 'Storage inspection failed.' }
$backupPath = Join-Path (Get-Location) ('backups/publishing-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backupPath -ErrorAction Stop | Out-Null
docker cp "${webId}:/app/private_publishing/." $backupPath
if ($LASTEXITCODE -ne 0) { throw 'Publishing backup failed; do not replace web.' }
```

If files exist, arrange a verified copy into the new volume with UID 10001 access
before replacing web. This runbook does not overwrite or automatically import
existing uploads. Keep the original container and backup until verified.

## Validate configuration without exposing resolved credentials

```powershell
docker compose -f compose.yaml -f compose.development-build.yaml config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Invalid merged Compose configuration.' }
```

## Initialize and verify permissions without restarting services

Run with Docker daemon access. These commands create disposable runners and the
named volume if absent; they do not start dependencies, restart web, or access
the database. `--rm` removes only the disposable runner, retaining the volume.

```powershell
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps publishing-storage-init
if ($LASTEXITCODE -ne 0) { throw 'Publishing storage initialization failed.' }
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps --entrypoint python web -c "import os, stat; p='/app/private_publishing'; s=os.stat(p); assert os.getuid()==10001; assert s.st_uid==10001; assert s.st_gid==10001; assert stat.S_IMODE(s.st_mode)==0o700; assert os.access(p, os.R_OK|os.W_OK|os.X_OK); print('UID 10001: private volume permissions verified')"
if ($LASTEXITCODE -ne 0) { throw 'Permission verification failed.' }
```

## Verify persistence across separate web runner containers

This writes a unique storage probe, not an article or database row. It is retained
for inspection; no files or volumes are deleted. The second runner must read the
same bytes after the first runner has been removed. This exercises the same mount
used by the web service when it is eventually recreated, without restarting it.

```powershell
$probeName = '.storage-probe-' + [guid]::NewGuid().ToString('N')
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps --entrypoint python web -c "import os, sys; from pathlib import Path; assert os.getuid()==10001; p=Path('/app/private_publishing')/sys.argv[1]; f=p.open('xb'); f.write(b'publishing-volume-persistence-v1'); f.close(); print('Probe written as UID 10001')" $probeName
if ($LASTEXITCODE -ne 0) { throw 'Probe write failed.' }
docker compose -f compose.yaml -f compose.development-build.yaml run --rm --no-deps --entrypoint python web -c "import os, sys; from pathlib import Path; assert os.getuid()==10001; assert (Path('/app/private_publishing')/sys.argv[1]).read_bytes()==b'publishing-volume-persistence-v1'; print('Persistence verified in a new web runner')" $probeName
if ($LASTEXITCODE -ne 0) { throw 'Persistence verification failed.' }
```

No deployment/recreation command is included here. Do not use `down -v`, volume
prune, or remove the publishing volume. When rolling back the application image,
retain this publishing mount if publishing files must remain available.

## Preparation results

Merged Compose validation and mount/dependency assertions passed during preparation.
Live ownership and persistence checks could not run because this session cannot
access the Docker engine named pipe. No storage volume was provisioned, container
restarted, migration applied, or existing upload moved during preparation.
