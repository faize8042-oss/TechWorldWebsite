# Codeventra Labs temporary preview runbook

VERIFIED: repository repairs and offline tests. IMPLEMENTED BUT UNVERIFIED:
Docker images, Linux permissions, Windows networking. BLOCKED: reviewed dependency
closure/images and separate build, execution and public-exposure approvals.
No Docker or tunnel command was executed during repairs. C6.1/C6.2.1 unchanged.

## A. Preflight — read-only

```powershell
Set-Location D:\TechWorldWebsite
.venv/Scripts/python.exe -B scripts/test_client_preview.py
.venv/Scripts/python.exe -B scripts/test_client_preview_security.py
powershell -NoProfile -File scripts/client-preview/test-scripts-offline.ps1
git diff --check
git diff --exit-code -- compose.yaml
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
```

Require PowerShell 5.1+, repository Python, Docker Desktop Linux containers and
Compose supporting create/no-recreate/pull-never. Never read .env/private uploads,
use development Compose, broad down or global prune. After read-only Docker access
is approved, privately snapshot development resources before/after; compare IDs,
states, start times and mounts. No live preservation claim is made offline:

```powershell
docker context show
docker version
docker compose version
docker inspect techworldwebsite-web-1 techworldwebsite-db-1 techworldwebsite-redis-1 techworldwebsite-nginx-1 --format '{{.Id}} {{.Name}} {{.State.Status}} {{.State.StartedAt}} {{json .Mounts}}'
```

## B. Reviewed image preparation — approved acquisition writes files

Reviewed requirements.txt: eight ranges (Django, psycopg[binary], django-environ,
Pillow, WhiteNoise, django-ratelimit, Gunicorn, Redis). Complete Linux transitive
closure/hash lock/wheelhouse is absent. Windows packages cannot finalize it.
Native Pillow/psycopg-binary wheels must match reviewed CPython 3.12 Linux target
architecture/libc/libraries. Clients remain installed for dependency-image parity;
the preview never configures or contacts PostgreSQL/Redis. No database image needed.

Preserve every gate in [C6.2.1 image preparation](c6-2-1-validation-image.md).
Its supplied Python manifest digest is a review input, not independently verified
here. Never invent versions/hashes/RepoDigests or weaken the harness.

Exact candidate procedure requires a separately approved native WSL Linux Python
3.12 matching the target architecture, reviewed pip version and approved index
configured without repository .env. Stop if unavailable. Record Python patch,
platform, resolver/index provenance and requirements hash. Download needs separate
network/acquisition approval; these commands do not create Docker resources:

```powershell
Get-FileHash requirements.txt -Algorithm SHA256
wsl --cd /mnt/d/TechWorldWebsite --exec python3.12 -c "import sys,sysconfig; print(sys.version); print(sysconfig.get_platform())"
wsl --cd /mnt/d/TechWorldWebsite --exec python3.12 -m pip --version
if (Test-Path deploy/c621-validation/wheelhouse) { throw 'Review existing wheelhouse first' }
wsl --cd /mnt/d/TechWorldWebsite --exec python3.12 -m pip download --only-binary=:all: --dest deploy/c621-validation/wheelhouse -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Acquisition failed' }
.venv/Scripts/python.exe -B scripts/client-preview/prepare-lock.py deploy/c621-validation/wheelhouse deploy/c621-validation/requirements.lock.candidate
if ($LASTEXITCODE -ne 0) { throw 'Candidate generation failed' }
Get-Content deploy/c621-validation/requirements.lock.candidate
Get-Content deploy/c621-validation/requirements.lock.candidate.inventory
```

Review EVERY wheel METADATA/Requires-Dist, Linux markers, tags, versions, licenses,
advisories and SHA256 against independent approved provenance. Compare all eight
requirements and closure. Helper computes actual hashes and pins all downloaded
distributions, preserving psycopg binary extra; it does not certify compatibility
or provenance. Reject sdists/duplicate packages/unexpected files. After review:

```powershell
if (Test-Path deploy/c621-validation/requirements.lock) { throw 'Review existing lock first' }
Copy-Item -LiteralPath deploy/c621-validation/requirements.lock.candidate -Destination deploy/c621-validation/requirements.lock
```

Unchanged dependency build uses binary-only/no-index/mandatory hashes and pip
check. See [pip secure installs](https://pip.pypa.io/en/latest/topics/secure-installs/)
and [repeatability](https://pip.pypa.io/en/stable/topics/repeatable-installs/).

## C. Explicit build approval — creates images

Approve both builds separately from execution. Verify the C6.2.1 recipe's exact
reviewed Python base already exists locally. Record builder/BuildKit versions and
context hashes. Enforce builder network policy: pull=false does not prevent missing
base acquisition. Stop if immutable local base resolution cannot be guaranteed.

```powershell
$approvedPlatform = Read-Host 'Reviewed Linux platform, e.g. linux/amd64'
docker buildx build --platform $approvedPlatform --network=none --pull=false --load --tag codeventra-c621-validation:reviewed --file deploy/c621-validation/Dockerfile deploy/c621-validation
if ($LASTEXITCODE -ne 0) { throw 'Dependency build failed' }
$dependencyImage = docker image inspect codeventra-c621-validation:reviewed --format '{{.Id}}'
if ($LASTEXITCODE -ne 0 -or $dependencyImage -cnotmatch '^sha256:[a-f0-9]{64}$') { throw 'Missing dependency identity' }
$context = Join-Path $PWD ('preview-build-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -B scripts/client-preview/prepare-context.py $context
if ($LASTEXITCODE -ne 0) { throw 'Context preparation failed' }
docker buildx build --platform $approvedPlatform --network=none --pull=false --load --build-arg "PREVIEW_DEPENDENCY_IMAGE=$dependencyImage" --tag codeventra-client-preview:reviewed --file "$context/Dockerfile" $context
if ($LASTEXITCODE -ne 0) { throw 'Preview build failed' }
$AppImage = docker image inspect codeventra-client-preview:reviewed --format '{{.Id}}'
$NginxImage = Read-Host 'Reviewed already-local Nginx sha256 image/config ID'
docker image inspect $AppImage $NginxImage --format '{{.Id}} {{.Os}} {{.Architecture}} {{json .Config}}'
```

Privately review layers/environment: reject credentials, unexpected PYTHONPATH,
PYTHONHOME/preload hooks, unsafe PATH or any unreviewed environment. Neither image
may declare volumes. App clears inherited ENTRYPOINT, fixes CMD and UID/GID
10001:10002; Nginx entrypoint is explicitly nginx. Review Nginx provenance/modules/
libraries and non-root main-config operation. No unreviewed tag/digest supplied.

Curated context enumerates preview Python/templates/CSS/JS, rejects source symlinks
and defaults to deny in .dockerignore. Review all public content; no root context,
.env, private upload or development bind. Static assets collect during build;
root-owned code/dependencies must be readable. HOME/TMPDIR/worker files use /tmp.
Runtime writes only bounded /tmp and fresh socket volume. Directory must be
10001:10002 mode 2750; socket 10001:10002 mode 0660; ingress socket mount read-only.
Native imports, pip check/versions, volume initialization and UID/read-only behavior
need separately approved isolated runtime validation with no database access.
Pinned inputs alone do not establish byte-identical image reproduction.
Preview local image IDs do not replace C6.2.1's registry-reference gates.

## D. Isolated startup — creates Docker resources

After reviewed images and explicit isolated execution approval:

```powershell
powershell -NoProfile -File scripts/client-preview/start-preview.ps1 -AppImage $AppImage -NginxImage $NginxImage
if ($LASTEXITCODE -ne 0) { throw 'Startup failed; preserve evidence, do not share' }
```

Confirm START codeventra-client-preview. Script locks cooperating operations,
checks names/labels/images/port, records intent and random run token, uses explicit
empty env file and creates with no-recreate/no-build/pull-never. It records exact
IDs, verifies ownership, then starts web and ingress by immutable container IDs.
Partial failure preserves evidence/resources; no Compose up/down/automatic rollback.

## E. Runtime verification — inspect, local HTTP, preview-only exec

```powershell
powershell -NoProfile -File scripts/client-preview/check-preview.ps1
if ($LASTEXITCODE -ne 0) { throw 'Verification failed; do not share' }
```

Actual inspect JSON checks exact project/run/service ownership, container/image/
network IDs, volume name/CreatedAt/Mountpoint/driver fingerprint, unexpected
resources/endpoints, internal bridge, recorded built-in none network for web,
configured/live loopback-only 8765 publication, no PostgreSQL/Redis exposure,
exact mount sources/destinations/access and only expected tmpfs. Drive-source
normalization is narrow; unknown Docker Desktop path representations fail closed.
Enforces read-only roots, expected UID/GID, no privileged/additional capabilities,
ALL capabilities dropped, exact no-new-privileges options, no devices/host namespaces.

Exec observes socket/directory modes/owners and exec NoNewPrivs/CapEff, plus dummy
database/email, DEBUG=False and disabled proxy trust. Bounded local HTTP disables
proxies/redirects and checks pages/assets, hosts, admin/private denials, contact
POST/forms disabled. Snapshots stay in runtime/. PASS scopes performed checks;
missing prerequisites INDETERMINATE, violations FAIL. Browser/public HTTPS/image
provenance/absence of concurrent daemon mutation remain separate gates.

## F. Local browser verification

```powershell
Start-Process 'http://127.0.0.1:8765'
```

Check home/services/about/projects/contact/privacy/terms, mobile/desktop navigation,
assets, synthetic projects, disabled enquiries, no private content. No real database,
Redis, mail, admin/auth/session flows. Strict local or single-label trycloudflare
hosts; forwarded host/protocol never trusted. Never relax route/host/proxy controls.

## G. Explicit Cloudflare Tunnel approval — public exposure

After local gates and separate explicit public approval, dedicated foreground
PowerShell window using reviewed cloudflared:

```powershell
cloudflared tunnel --url http://127.0.0.1:8765
```

No DNS/token/firewall/router changes. Anyone with the link can view synthetic
content; noindex is not authentication. Stop if host/forwarding contract fails.

## H. Public HTTPS verification — approved public requests

```powershell
$PreviewUrl = Read-Host 'Assigned HTTPS Quick Tunnel origin'
if ($PreviewUrl -cnotmatch '^https://[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com$') { throw 'Unexpected origin' }
Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 "$PreviewUrl/" | Select-Object StatusCode
foreach ($case in @(@('/admin/','GET',404),@('/contact/','POST',405))) {
  try { $r = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -Method $case[1] "$PreviewUrl$($case[0])"; $status = [int]$r.StatusCode }
  catch { if (-not $_.Exception.Response) { throw }; $status = [int]$_.Exception.Response.StatusCode }
  if ($status -ne $case[2]) { throw "Public boundary failed: $($case[0])" }
}
Start-Process $PreviewUrl
```

Check seven pages/assets externally too. Public HTTPS/browser remains unverified.

## I. Client link sharing

Manually share only verified origin: "Temporary Codeventra Labs preview; synthetic
projects, enquiries disabled; link expires when preview closes." No automatic messages.

## J. Tunnel shutdown

Ctrl+C in that exact foreground tunnel window. Confirm assigned URL stops serving
preview. Do not kill unrelated cloudflared processes.

## K. Isolated shutdown — destructive, exact targets

```powershell
powershell -NoProfile -File scripts/client-preview/stop-preview.ps1
# Optional separately approved data deletion, including on a later invocation:
powershell -NoProfile -File scripts/client-preview/stop-preview.ps1 -DeleteDisposableData
```

Confirm STOP and, only for data deletion, DELETE codeventra-client-preview SOCKET
DATA. Every stop/remove revalidates ownership immediately before exact container/
network ID mutation. Already-cleaned resources allowed only for cleanup; discovered
replacements/extras/ambiguity refuse it. Volume retained by default; deletion checks
fingerprint/token immediately before name removal. Evidence retained; review/archive
before fresh start. Never blindly erase state.json to proceed.

Unavoidable races: Docker has no transactional inventory, conditional volume delete
by immutable ID or atomic inspect+mutate/multi-resource creation. Operation lock
excludes cooperating scripts only. Host/Docker admins, context and repository/state
files are trusted and must stay stable, with no concurrent resource mutation.
Volume fingerprint is not an immutable ID: name replacement after inspection cannot
be atomically prevented. If exclusive daemon access is uncertain, retain volume for
investigation. Tokens prevent accidental adoption, not malicious administrators.
Port probe cannot reserve 8765 until binding; binding failure fails startup.
See [Docker volume semantics](https://docs.docker.com/engine/storage/volumes/).

Future read-only cleanup checks:

```powershell
docker container ls -a --filter 'label=com.docker.compose.project=codeventra-client-preview'
docker network ls --filter 'label=com.docker.compose.project=codeventra-client-preview'
docker volume ls --filter 'label=com.docker.compose.project=codeventra-client-preview'
```

## Offline evidence and blockers

Passed: 11 preview tests; 6 executable health/policy/lock tests including 20 unsafe
metadata mutations; PowerShell syntax and mocked ownership/revalidation/cleanup;
37 Django security tests; 80 synthetic in-memory application tests; C6.2.1 suites
14/20/6; C6.1 probe 10 cases; git diff --check and unchanged root compose.yaml.
No real database/email/Docker/tunnel access occurred.

BLOCKED: reviewed platform/base/Nginx, full dependency lock/wheel provenance,
build/execution/public approvals, actual native/permission/health/Nginx/Windows
loopback/browser/HTTPS validation. Repository readiness is not runtime safety.
