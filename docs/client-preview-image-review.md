# Client preview image prerequisite review — 2026-10-31

## Latest isolated-session recheck — 2026-10-31

This section supersedes earlier environment findings below. Verdict: BLOCKED.
No pull, build, run, Compose execution, container mutation or network acquisition
was performed. Existing development containers were not modified.

A. Nginx config image ID: UNVERIFIED for both nginx:stable-alpine and
nginx:1.28.1-alpine. B. Python config image ID: UNVERIFIED. Supplied digest
cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
is a repository reference, not an observed config image ID.

C. User reports Docker Desktop 4.94.0, Engine 29.8.2, desktop-linux and
linux/amd64. CLI 29.8.2 was observed, but Server was null: default named-pipe
access was denied. Explicit --context desktop-linux also failed reading context
meta.json (access denied). No access-control bypass was attempted. Consequently
IDs, platform, volumes, entrypoints, users, provenance and ABI remain unverified.
The intended build target is explicitly linux/amd64; it is not independently
confirmed by this session. Alpine Nginx and Debian Python need not share libc:
they are separate containers communicating over a Unix socket. Python native
wheels must match Python's own CPython/architecture/glibc, not Nginx's musl.

D. requirements.lock and wheelhouse are still absent. The eight direct ranges
remain required by the existing dependency-image contract. Observed Windows
metadata adds an overlooked Linux Python 3.12 transitive: typing-extensions
(psycopg 3.3.6 requires it below Python 3.13). For those observed versions the
known closure is Django, asgiref, sqlparse, psycopg, psycopg-binary,
typing-extensions, django-environ, Pillow, whitenoise, django-ratelimit,
gunicorn, packaging, plus redis and any dependencies required by its selected
version. Redis is not installed locally; its selected metadata is unavailable.
Windows-only tzdata is not required by the inspected Linux markers. Exact
Linux versions/closure cannot be certified from Windows installations or ranges.
No versions/hashes were invented or promoted. Requirements SHA256 is unchanged.
Repository/.venv wheel search found no usable wheels. Standard pip wheel cache
still contains only login, pandoradep and pi; none is a preview dependency.

techworld-django:local is NOT approved as a dependency source. Its actual metadata
and layers are inaccessible. The current development recipe copies the repository
with COPY . ., installs unpinned ranges globally and creates application/upload
directories. Current ignore rules cannot prove historical layers lack secrets or
state. FROM that image would inherit all layers, even if files were later deleted.
Selective dependency extraction would still require reviewed provenance, complete
metadata/hash inventory, native-library compatibility and path/hook review; it
does not supply the missing reviewed wheels. No export or extraction was done.

E. Remaining prerequisites: accessible authorized Docker session; inspect exact
base/Nginx/builder; reviewed Linux resolver and redis metadata; acquire/review the
complete binary wheel closure and hashes; offline resolver verification; enforce
builder base-resolution network policy. Runtime validation remains a later gate.
No Dockerfile or safety-policy change is justified by unavailable inputs.

F. Exact commands below are PREPARED ONLY. They are conditional on the named
prerequisites, not validated executable build inputs. In an authorized session,
retain this context for all subsequent Docker commands:

```powershell
$ErrorActionPreference = 'Stop'
$env:DOCKER_CONTEXT = 'desktop-linux'
$approvedPlatform = 'linux/amd64'
$Base = 'python@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2'
docker version
if ($LASTEXITCODE) { throw 'Engine unavailable' }
docker image inspect $Base python:3.12-slim nginx:stable-alpine nginx:1.28.1-alpine techworld-django:local --format '{{.Id}} {{json .RepoDigests}} {{.Os}}/{{.Architecture}} volumes={{json .Config.Volumes}} entrypoint={{json .Config.Entrypoint}} user={{json .Config.User}}'
if ($LASTEXITCODE) { throw 'Image metadata incomplete' }
```

Review full config/history privately using the existing F procedure; reject
unexpected hooks/environment/volumes. Select Nginx by its observed full config
ID; no such ID can be supplied yet. Do not substitute the Python manifest digest.

Acquisition command, after matching native Linux CPython 3.12/glibc/amd64 resolver
and credential-free index approval (no Docker invocation or source builds):

```powershell
$Index = Read-Host 'Approved credential-free HTTPS package index URL'
if ($Index -notmatch '^https://[^/@]+/') { throw 'Review index URL' }
if (Test-Path deploy/c621-validation/wheelhouse) { throw 'Review existing wheelhouse' }
wsl --cd /mnt/d/TechWorldWebsite --exec python3.12 -I -m pip --isolated --disable-pip-version-check --no-cache-dir download --index-url $Index --only-binary=:all: --dest deploy/c621-validation/wheelhouse -r requirements.txt
if ($LASTEXITCODE) { throw 'Acquisition failed' }
.venv/Scripts/python.exe -B scripts/client-preview/prepare-lock.py deploy/c621-validation/wheelhouse deploy/c621-validation/requirements.lock.candidate
if ($LASTEXITCODE) { throw 'Candidate generation failed' }
```

Review every actual METADATA/marker/tag/hash/provenance/license/advisory; promote
and run the offline hash-enforced dry-run from F below. This acquires all missing
dependencies including redis and typing-extensions without guessing their pins.
Only after that and builder policy verification, the exact build/ID commands are:

```powershell
docker buildx build --platform linux/amd64 --network=none --pull=false --load --tag codeventra-c621-validation:reviewed --file deploy/c621-validation/Dockerfile deploy/c621-validation
if ($LASTEXITCODE) { throw 'Dependency build failed' }
$dependencyImage = docker image inspect codeventra-c621-validation:reviewed --format '{{.Id}}'
if ($LASTEXITCODE -or $dependencyImage -cnotmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid dependency ID' }
$context = Join-Path $PWD ('preview-build-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -B scripts/client-preview/prepare-context.py $context
if ($LASTEXITCODE) { throw 'Context preparation failed' }
Get-ChildItem $context -Recurse -File -Force | Get-FileHash -Algorithm SHA256
# Review the curated public context before building.
docker buildx build --platform linux/amd64 --network=none --pull=false --load --build-arg "PREVIEW_DEPENDENCY_IMAGE=$dependencyImage" --tag codeventra-client-preview:reviewed --file "$context/Dockerfile" $context
if ($LASTEXITCODE) { throw 'Preview build failed' }
$AppImage = docker image inspect codeventra-client-preview:reviewed --format '{{.Id}}'
if ($LASTEXITCODE -or $AppImage -cnotmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid app ID' }
docker image inspect $dependencyImage $AppImage $NginxImage --format '{{.Id}} {{.Os}}/{{.Architecture}} volumes={{json .Config.Volumes}} entrypoint={{json .Config.Entrypoint}} user={{json .Config.User}}'
if ($LASTEXITCODE) { throw 'Image verification failed' }
```

--network=none controls RUN only. --pull=false does not forbid missing FROM
acquisition. Builder policy and exact local base availability remain prerequisites.

G. Exact isolated startup/check commands, after image review and execution approval:

```powershell
powershell -NoProfile -File scripts/client-preview/start-preview.ps1 -AppImage $AppImage -NginxImage $NginxImage
if ($LASTEXITCODE) { throw 'Startup failed' }
powershell -NoProfile -File scripts/client-preview/check-preview.ps1
if ($LASTEXITCODE) { throw 'Runtime checks failed' }
```

Use the preview-only pip check/native-import and version comparison commands in G
below with the recorded verified web container ID. No development exec, database,
Redis connection or tunnel is part of this recheck.

H. Rerun results: 11 preview + 6 preview security/lock + 6 dependency-image
tests passed (23 total). PowerShell syntax and mocked safety suite passed; its
stop/remove output described mocks only. git diff --check and unchanged root
compose.yaml checks passed before this documentation update. No broad audit run.

I. BLOCKED: useful offline investigation completed, but exact image identities
and a reviewed Linux dependency closure are unavailable. User-reported environment
verification does not grant this restricted process Docker access.

Status: BLOCKED; procedure reviewed, no acquisition/build/runtime approval implied.
Read with client-preview-runbook.md B–J and c6-2-1-validation-image.md; preserve
all their provenance, image, dependency, runtime and public-exposure gates.

## A–E. Findings and blockers

Docker image inventory and metadata could not be obtained: engine named-pipe
access denied; Docker also reported config.json access denied. No local image,
Nginx candidate, Python version, architecture, libc or RepoDigest is verified.
WSL distribution enumeration also failed with E_ACCESSDENIED. Do not bypass these
access controls. Run the read-only commands below in an authorized Docker session.

No platform is approved. Candidate: Linux CPython 3.12, architecture matching the
exact pinned Python base and local Nginx. linux/amd64 is only an example, not an
observed fact. Establish libc and Python patch from trusted base provenance;
image inspect alone does not establish native ABI compatibility.

The dependency Dockerfile requires exactly
python@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
in both stages. This supplied reference is not locally verified. Do not replace
it or manufacture a repository digest. No Nginx ID is known.

deploy/c621-validation contains only Dockerfile and .dockerignore: no lock or
wheelhouse. Searches of deploy, scripts and .venv found no wheels or dependency
lock/hash inventory. The standard pip wheel cache contains only login 0.0.6,
pandoradep 0.3.0 and pi 0.1.2 universal wheels; none satisfies a declared direct
dependency or establishes its closure. Opaque HTTP cache bodies were not treated
as reviewed wheels. No private uploads, dotenv contents or backup trees were read.

All eight ranges in requirements.txt remain required. asgiref, sqlparse and
packaging are expected transitives; exact closure and marker dependencies must
come from actual selected metadata. Windows installed packages are not a Linux
closure. Pillow and psycopg-binary need matching CPython/platform/libc wheels.
Requirements SHA256:
4a213e81f8193c3872f6c099f0552f8afdd25e17b767804b317c12089fc8fc53.

Current Dockerfile cannot build with the available reviewed inputs: required
COPY inputs are absent, base resolution is unverified, and no dependency image
exists as verified evidence. No Dockerfile or working script change is justified.

Remaining blockers: authorized Docker metadata access; base/Nginx provenance and
platform review; matching native Linux 3.12 resolver with recorded pip/index;
approved acquisition; complete reviewed wheels, hashes, licenses/advisories and
closure; builder policy preventing base acquisition; explicit build approval.
Execution/native imports/permissions/Nginx/Windows loopback checks and separate
public exposure approval follow successful builds. Preview image IDs do not
satisfy the separate C6.2.1 registry-reference harness gate.

## F. Exact command procedure

Commands below were NOT executed unless expressly recorded in H. Each block is
separate; stop on failure. Do not paste all blocks as one unattended procedure.

Read-only, in an authorized Docker session (no pulls):

```powershell
Set-Location D:\TechWorldWebsite
$ErrorActionPreference = 'Stop'
docker context show
docker version
docker compose version
docker image ls --no-trunc --digests
if ($LASTEXITCODE) { throw 'Docker access unavailable' }
$Base = 'python@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2'
docker image inspect $Base --format '{{.Id}} {{json .RepoDigests}} {{.Os}}/{{.Architecture}} {{json .Config}} {{json .RootFS}}'
if ($LASTEXITCODE) { throw 'Exact base unavailable locally; acquisition needs separate approval' }
$NginxImage = Read-Host 'Existing local Nginx full sha256 config ID selected from inventory'
if ($NginxImage -cnotmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid identity' }
docker image inspect $NginxImage --format '{{.Id}} {{json .RepoDigests}} {{.Os}}/{{.Architecture}} {{json .Config}} {{json .RootFS}}'
if ($LASTEXITCODE) { throw 'Nginx unavailable' }
docker image history --no-trunc $Base
docker image history --no-trunc $NginxImage
docker buildx version
docker buildx ls
wsl --cd /mnt/d/TechWorldWebsite --exec python3.12 -I -c "import sys,sysconfig,platform; print(sys.version); print(sysconfig.get_platform()); print(platform.machine()); print(platform.libc_ver())"
if ($LASTEXITCODE) { throw 'Matching resolver unavailable' }
wsl --cd /mnt/d/TechWorldWebsite --exec python3.12 -I -m pip --version
if ($LASTEXITCODE) { throw 'pip unavailable' }
```

Privately review history/config for credentials, unsafe environment/hooks and
volumes; require matching Linux architectures and trusted Nginx provenance,
modules/libraries and non-root operation with deploy/client-preview/nginx.conf.
Do not publish raw metadata. Record the approved platform, base Python patch/libc,
resolver/pip version and index before proceeding. If these cannot be established,
stop. No exact pull command can be supplied for an unidentified Nginx image.

Separate acquisition approval required. This uses a clean native Linux resolver
environment matching the reviewed target; pip isolated mode ignores user config
and environment. Enter the approved credential-free package index explicitly.

```powershell
$Index = Read-Host 'Approved credential-free HTTPS package index URL'
if ($Index -notmatch '^https://[^/@]+/') { throw 'Review index URL' }
if (Test-Path deploy/c621-validation/wheelhouse) { throw 'Review existing wheelhouse first' }
Get-FileHash requirements.txt -Algorithm SHA256
wsl --cd /mnt/d/TechWorldWebsite --exec python3.12 -I -m pip --isolated --disable-pip-version-check --no-cache-dir download --index-url $Index --only-binary=:all: --dest deploy/c621-validation/wheelhouse -r requirements.txt
if ($LASTEXITCODE) { throw 'Acquisition failed' }
.venv/Scripts/python.exe -B scripts/client-preview/prepare-lock.py deploy/c621-validation/wheelhouse deploy/c621-validation/requirements.lock.candidate
if ($LASTEXITCODE) { throw 'Candidate generation failed' }
Get-Content deploy/c621-validation/requirements.lock.candidate
Get-Content deploy/c621-validation/requirements.lock.candidate.inventory
Get-ChildItem deploy/c621-validation/wheelhouse/*.whl | Get-FileHash -Algorithm SHA256
```

Mandatory review pause: independently compare every wheel hash to approved source
provenance; inspect METADATA/Requires-Dist and WHEEL tags; review all markers,
extras, licenses/advisories and eight ranges. The generator hashes bytes but does
not verify provenance, dependency closure or platform compatibility. Reject any
missing/unexpected dependency, sdist, duplicate or incompatible wheel. Only after
this review, repository-only promotion and offline resolver verification:

```powershell
if (Test-Path deploy/c621-validation/requirements.lock) { throw 'Review existing lock first' }
Copy-Item deploy/c621-validation/requirements.lock.candidate deploy/c621-validation/requirements.lock
wsl --cd /mnt/d/TechWorldWebsite --exec python3.12 -I -m pip --isolated --disable-pip-version-check --no-cache-dir install --dry-run --ignore-installed --no-index --only-binary=:all: --find-links=deploy/c621-validation/wheelhouse --require-hashes -r deploy/c621-validation/requirements.lock
if ($LASTEXITCODE) { throw 'Offline closure verification failed' }
```

This requires a reviewed pip supporting --dry-run. Review native wheel tags/libc
separately; resolver success does not prove shared-library loading.

Explicit build approval required for BOTH builds. Require exact local base and
builder network policy first: --network=none controls RUN, not FROM resolution;
--pull=false alone cannot guarantee no acquisition. No builder creation/bootstrap
is authorized by the read-only block above.

```powershell
$approvedPlatform = Read-Host 'Reviewed matching Linux platform'
Get-ChildItem deploy/c621-validation -Recurse -File | Get-FileHash -Algorithm SHA256
docker buildx build --platform $approvedPlatform --network=none --pull=false --load --tag codeventra-c621-validation:reviewed --file deploy/c621-validation/Dockerfile deploy/c621-validation
if ($LASTEXITCODE) { throw 'Dependency build failed' }
$dependencyImage = docker image inspect codeventra-c621-validation:reviewed --format '{{.Id}}'
if ($LASTEXITCODE -or $dependencyImage -cnotmatch '^sha256:[a-f0-9]{64}$') { throw 'Missing dependency identity' }
$context = Join-Path $PWD ('preview-build-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -B scripts/client-preview/prepare-context.py $context
if ($LASTEXITCODE) { throw 'Context preparation failed' }
Get-ChildItem $context -Recurse -File -Force | Get-FileHash -Algorithm SHA256
docker buildx build --platform $approvedPlatform --network=none --pull=false --load --build-arg "PREVIEW_DEPENDENCY_IMAGE=$dependencyImage" --tag codeventra-client-preview:reviewed --file "$context/Dockerfile" $context
if ($LASTEXITCODE) { throw 'Preview build failed' }
$AppImage = docker image inspect codeventra-client-preview:reviewed --format '{{.Id}}'
if ($LASTEXITCODE -or $AppImage -cnotmatch '^sha256:[a-f0-9]{64}$') { throw 'Missing app identity' }
docker image inspect $dependencyImage $AppImage $NginxImage --format '{{.Id}} {{.Os}}/{{.Architecture}} {{json .Config}}'
if ($LASTEXITCODE) { throw 'Image verification failed' }
```

Review curated public context before its build; review image IDs/config/history
before execution. No declared volumes; app UID/GID 10001:10002, empty entrypoint,
expected CMD/environment. Nginx runtime validation remains required.

## G. Startup, runtime checks and tunnel

Separate isolated execution approval, with reviewed IDs retained from F:

```powershell
powershell -NoProfile -File scripts/client-preview/start-preview.ps1 -AppImage $AppImage -NginxImage $NginxImage
if ($LASTEXITCODE) { throw 'Startup failed; preserve evidence' }
powershell -NoProfile -File scripts/client-preview/check-preview.ps1
if ($LASTEXITCODE) { throw 'Runtime checks failed; do not share' }
Start-Process 'http://127.0.0.1:8765'
```

After check-preview.ps1 passes, the same execution approval must cover these
preview-only exec checks. Obtain the exact web ID from the script's recorded
runtime evidence; never substitute a development container. Re-run the policy
check immediately before exec and require exclusive daemon access.

```powershell
$WebId = Read-Host 'Exact verified preview web container ID from runtime evidence'
if ($WebId -cnotmatch '^[a-f0-9]{64}$') { throw 'Invalid container ID' }
docker container inspect $WebId --format '{{.Id}} {{.Image}} {{json .Config.Labels}}'
if ($LASTEXITCODE) { throw 'Missing preview container' }
# Compare ID/image/project/run/service labels to recorded evidence before continuing.
powershell -NoProfile -File scripts/client-preview/check-preview.ps1
if ($LASTEXITCODE) { throw 'Runtime identity/policy failed' }
docker exec $WebId python -m pip check
if ($LASTEXITCODE) { throw 'Installed dependency closure failed' }
docker exec $WebId python -c "import sys,importlib.metadata as m; import django,psycopg,psycopg_binary,environ,PIL,whitenoise,django_ratelimit,gunicorn,redis; print(sys.version); print(sorted((d.metadata['Name'],d.version) for d in m.distributions()))"
if ($LASTEXITCODE) { throw 'Native imports failed' }
```

Compare installed versions against the reviewed lock. Complete runbook F browser gates before public
exposure. No PostgreSQL/Redis connection or database image is needed.

Separate public-exposure approval, reviewed cloudflared, dedicated foreground
PowerShell window:

```powershell
cloudflared tunnel --url http://127.0.0.1:8765
```

Perform runbook H public HTTPS checks before sharing. Tunnel shutdown: press
Ctrl+C in that exact window and confirm its assigned URL no longer serves preview.
Do not kill unrelated processes. No cleanup command is part of this procedure.

## H. Offline verification

23 Python tests passed: 11 preview, 6 preview security/lock, 6 dependency-image
offline tests. PowerShell syntax and mocked safety tests passed; their printed
stop/remove messages describe mocks only. git diff --check passed. Full prior
174-test/security audit was not repeated. No downloads, builds, container runtime,
cleanup, database access, emails or tunnels occurred.

## I. Git

Existing dirty worktree preserved, no staging/commits/pushes. This review adds only
this document; working scripts and Dockerfiles unchanged. Use git status --short
for the complete existing modified/untracked inventory.
