# C6.2.1 validation image preparation

Status: repository preparation only; **build blocked pending dependency inputs**.
No image was built, pulled, inspected or executed during preparation. No service
connections or migrations were performed. The Dockerfile is a proposal, not an
approved or verified image. Development Dockerfile and compose.yaml are unchanged.

## Reviewed inventory

Reviewed requirements.txt, application Python sources and migrations in config,
core, projects, contact and analytics, and scripts/c621/probe.py (including imports
inside functions). All eight runtime requirements are retained for parity:

| Requirement range | Use |
| --- | --- |
| Django >=5.2,<5.3 | Application, models, migrations, ORM and probe management commands |
| psycopg[binary] >=3.2,<4 | Probe connections and Django PostgreSQL backend; requires matching psycopg-binary wheel |
| django-environ >=0.12,<1 | config.settings imports environ |
| Pillow >=11,<13 | contact.models imports PIL; migration imports contact.models; ImageField checks |
| whitenoise >=6.9,<7 | Settings middleware and static storage strings |
| django-ratelimit >=4.1,<5 | contact.views decorator, loaded via URL configuration |
| gunicorn >=23,<24 | Development/production server command; retained although harness does not start it |
| redis >=5.0,<7.0 | Django RedisCache backend configured by string; no Redis connection in this preparation or harness |

The probe also uses Python standard-library modules and application modules.
Expected transitive dependencies include asgiref/sqlparse (Django), packaging
(Gunicorn), and potentially typing-extensions and other platform/version-specific
dependencies. This is **not** a complete resolved inventory. Determine the exact
closure from selected wheel metadata on the approved Python 3.12 Linux platform.
requirements-dev.txt adds pip-audit: exclude this development tool from the image.

## Dependency locking gate

There is no reviewed exact-version lock, wheelhouse, hash inventory, Linux target
architecture, or resolver/toolchain version in the repository. Version ranges and
installed Windows packages cannot establish Linux wheel resolution. Do not guess
versions, hashes or architecture. requirements.lock and wheelhouse are intentionally
absent: COPY must fail rather than fall back to mutable online resolution.

After separate authorization for dependency acquisition, select and record the
Linux target platform and verify Python 3.12 in the supplied base. Resolve all eight
requirements together using a reviewed, version-recorded resolver against an
approved package source. Record resolver version, index/provenance, Python patch
version, platform, base manifest/platform digests and source requirements hash.
Create deploy/c621-validation/requirements.lock with every direct and transitive
distribution pinned using == and SHA-256 hashes for the exact selected wheels.
Include psycopg and matching psycopg-binary, and all active environment-marker
dependencies. No URLs, editable/local paths, index options, floating constraints,
unreviewed extras, sdists or credentials. Preserve the binary extra or explicitly
record its complete equivalent closure. Review licenses/security and wheel metadata.

Place only those reviewed Linux CPython 3.12 compatible wheels in wheelhouse/.
Record a complete filename/version/SHA-256 inventory and verify it independently
against approved provenance. Compare the resolved closure to requirements.txt;
review changes whenever application requirements/imports change. Lock the resolver
tooling separately; do not add it to the runtime image. No network resolution or
native compilation occurs in the proposed Dockerfile. Missing wheels, hashes or
dependencies must fail. Hash locking fixes dependency bytes; it does not alone
guarantee bit-for-bit image reproduction (builder/version/timestamps also matter).

## Construction and isolation

Use deploy/c621-validation as the **entire build context**. Its deny-by-default
.dockerignore permits only Dockerfile, ignore rules, the lock and wheel files.
Do not copy application source, .env, credentials, uploads, databases, SQL data,
validation-results or repository root into that directory. There is no COPY . .
and no application command, collectstatic or migration at build time. Only the
installed virtual environment crosses from the dependency stage to the final image.
Review inherited base layers/config/history as well: context exclusions cannot
remove secrets that already exist in a base image or malicious wheel.

Both stages use the supplied reviewed Python reference:
`python@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2`.
It is treated as Python 3.12 based on the supplied review, not independently
verified here. pip installs only hashed binary wheels without an index under a
BuildKit RUN network=none restriction. The runtime uses numeric UID 10001/GID
10002, readable root-owned dependencies, HOME/TMPDIR=/tmp and disabled bytecode.
It declares no volumes, ports or application secrets. Numeric IDs need no passwd
entry. Actual permissions and native library loading still need runtime testing.

The unchanged harness mounts curated source read-only at /work, runs migrations
only in its separately approved disposable database, and overrides the image CMD.
It preserves read-only Python roots, internal networking, no published ports,
dropped capabilities, no-new-privileges, 768 MiB/1 CPU/256 PID limits and bounded
tmpfs (/tmp 128 MiB, /run/secrets 1 MiB). No writable image paths are required.
PostgreSQL PGDATA remains /var/lib/postgresql/data on its bounded 512 MiB tmpfs.

Future build template, **not executed and not authorized by this preparation**:

```powershell
# Only after dependency review and separate build approval; set reviewed platform.
# docker buildx build --platform $approvedPlatform --network=none --pull=false --load `
#   --tag codeventra-c621-validation:reviewed `
#   --file deploy/c621-validation/Dockerfile deploy/c621-validation
```

Record builder/BuildKit versions, invocation and context hashes; ensure the exact
base is already local. --pull=false is not a guarantee against acquiring a missing
base: enforce build infrastructure network policy/local availability separately.
No execution approval is implied by eventual build approval.

## Digest verification and harness compatibility

The unchanged harness requires `repository@sha256:<64 lowercase hex>` for Python
and specifically `postgres:17@sha256:<64 lowercase hex>` for PostgreSQL. It uses
local image inspect before creation and Compose --no-build --pull never; it
rejects unexpected declared volumes and mismatched PGDATA. It accepts a locally
available derived image by repository digest **if the engine actually resolves that
exact reference locally**. It does not accept a bare sha256 image ID or tag alone.
A local build/load commonly has no RepoDigests. A config/image ID, layer digest,
OCI archive checksum and registry manifest digest are different identifiers:
never append an image ID to a repository name or fabricate a RepoDigest.

After separately approved build and image verification, inspect the candidate by
immutable reference and record Id, RepoDigests, OS/architecture, Config.User, Env,
Entrypoint/Cmd, Volumes and history. Compare to build provenance and wheel hashes;
inspect filesystem/SBOM for unexpected files and secrets without dumping secrets
into reports. Confirm Python 3.12, dependency versions, pip check, binary psycopg
imports and native-library loading using separately approved disposable runtime
tests with the harness UID, read-only root and bounded tmpfs. Import checks alone
do not prove PostgreSQL authentication, migrations or ACL behavior.

If no usable RepoDigest exists, stop. A separately approved controlled registry
publication/retrieval or reviewed OCI digest-preserving import workflow must make
the exact manifest reference locally resolvable, with provenance verification.
Registry publication/acquisition is not authorized now. Do not weaken the harness
regex, replace it with mutable tags, add pulls or substitute the base Python digest
for the derived validation image digest. Confirm exact-reference local resolution
before granting isolated execution approval.

Supplied PostgreSQL reference:
`postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3`.
The harness requires the corresponding `postgres:17@sha256:` spelling. Before use,
verify that this exact locally resolvable reference denotes the reviewed PostgreSQL
17 image with PGDATA=/var/lib/postgresql/data and UID/GID 999:999. Digest alone
does not prove major version or platform. No reference rewrite or daemon access
was attempted here. Failure to resolve/verify remains an execution blocker.

## Offline checks and remaining gates

Run `python -B -m unittest discover -s scripts -p test_c621_image_offline.py -v`
and the existing test_c621_harness_offline.py suite. These use source inspection
and mocks only; they do not import the application, connect to services or invoke
Docker. They check proposed construction and existing isolation/digest gates.

Remaining blockers: exact reviewed dependency closure/hashes/wheels; approved
platform and base metadata verification; approved build; derived-image immutable
reference availability/provenance; image filesystem, permissions and native import
verification; PostgreSQL 17 reference verification; separate isolated execution
approval and actual migration/connection/security testing. No production readiness
or live test success is claimed.

Preparation evidence (2026-10-31): 6/6 new image offline tests and 20/20 existing
harness offline tests passed. git diff --check passed. No Docker commands,
connections, migrations, staging, commits or deployment were performed. Existing
uncommitted C6.2.1 work was preserved. This task adds only the dedicated Dockerfile,
its context .dockerignore, this document and scripts/test_c621_image_offline.py.
