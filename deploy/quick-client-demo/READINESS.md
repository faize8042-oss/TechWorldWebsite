# Current layer pipeline repair ? 2026-10-31

This section supersedes older implementation diagnoses below. The preserved real-image
report records helper-layer-integrity-and-filesystem / invalid-data-or-integrity,
followed by filesystem-inspection / helper-runtime-or-incomplete-output. The second
failure is the wrapper rejecting incomplete output after the helper aborts. That
report has no finer evidence; its precise real-image trigger cannot be established
without rerunning the repaired audit. No Docker access was attempted in this session
because the documented Engine denial remains applicable. No image is certified.
The exact baseline and historical report remain untouched. Current report SHA256:
`0612f391d7953e297d721a56f105eccde3ed726916c3e174de6b70d5bd8326c3`.

Confirmed implementation defects reproduced with synthetic archives:

- Stored layer bytes were hashed against inspect RootFS.Layers (DiffIDs). Gzip or
  zstd blob digests differ from hashes of their uncompressed tar streams. The helper
  now verifies OCI stored blob names against SHA256, then hashes the entire decoded
  stream (including tar padding) against the ordered DiffIDs before parsing tar.
  Legacy digest/layer.tar and flat layer paths remain supported. Gzip uses stdlib;
  zstd uses Python 3.14 compression.zstd. Older interpreters fail closed on zstd.
  Decoding is bounded across layers and spooled inside the private ACL directory;
  no archive member is extracted, executed or imported.
- Verifying the config filename did not bind it to the pinned image identity.
  Config-image IDs now require equality with the saved config SHA256. For OCI
  manifest/index identities, hash-verified descriptors must connect the exact ID
  to that config and ordered stored layer paths and sizes. Missing identity blobs
  fail closed. RepoDigests and layer digests are never substituted for image IDs.
  Old fixtures incorrectly used the production ID for unrelated synthetic config
  bytes; fixtures now derive their own cryptographically correct identities.
- Unsafe drive paths, hardlink traversal and malformed dot whiteout targets now
  fail closed. Symlinks are never followed; Linux absolute/relative symlink targets
  remain valid metadata. Application/dependency aliases still require review and
  cannot satisfy regular-file evidence. PAX/GNU long-name metadata is handled by
  tarfile; special files and ambiguous ancestors retain mandatory findings.
- The wrapper preserves a finite sanitized Failure detail vocabulary and identifies
  helper aborts as helper-aborted-before-complete-evidence. It still requires all
  completion, counters, exit status and verdict evidence; image identity now has
  its own mandatory counter. Raw exceptions, stderr and private paths never enter
  the report. Missing archive members, stored-digest mismatch, DiffID mismatch,
  decompression failure, expansion limit and unsupported compression are distinct.

Existing whiteout/replacement logic was regression-tested: deletions affect lower
layers, opaque directories preserve same-layer additions, historical secrets remain
findings after deletion, and replacement invalidates retained dependency metadata.

Validation in this session: Python 3.14 and Windows PowerShell 5.1; 45 audit tests
passed, including complete mocked orchestration, raw/gzip/zstd, OCI index binding,
layer order, PAX/GNU, links, corruption, opaque whiteouts and redaction. Existing
C621 suites passed (14 + 6 + 20), configuration suite 37, preview suites 11 + 6,
application suite 80, and 10 socket scenarios. Baseline/probe checks run within the
audit suite; Compose contracts and preview lifecycle mocks passed separately.
Run script suites in separate processes with `python -m scripts.<module>`: the
standalone launch runner intentionally clears its environment and exits, so importing
all scripts via unittest discovery contaminates later tests and is unsupported.

Next real-image diagnostic (run once in the authorized Windows PowerShell from
D:\TechWorldWebsite, with Python 3.14 available as python.exe):

```powershell
powershell.exe -NoProfile -File .\deploy\quick-client-demo\audit-image.ps1 -Python python.exe
```

This performs inspect/history/save only, writes sanitized image-audit-report.txt,
and removes the private spool after ownership checks. It starts no container and
builds nothing. Exit 1 remains expected for unresolved manual gates even when static
inspection completes. Check Inspection: COMPLETE and Failure detail separately from
the final verdict. A missing identity blob requires a complete Docker save for the
same pinned ID; a digest mismatch requires investigating archive corruption/identity,
never changing the baseline or bypassing verification. Unsupported zstd requires a
trusted Python 3.14 build with stdlib zstd support.

Likely subsequent blockers are genuine mandatory findings: baked credentials/private
files, startup hooks, missing application/static/module/distribution files, config
mismatch, and independent startup/public-asset and dependency/provenance reviews.
Runtime ownership, dependency/native compatibility and public exposure remain
unverified. No services or tunnel were started. No PASS has been fabricated.

---

# Image audit repair and current status - 2026-10-31

This section supersedes historical audit implementation notes below. **Real-image
status remains FAIL / unverified**, not a claim that the image contains a secret.
No Docker Engine command was attempted in this repair session: prior documented
access denial is respected. The original image-audit-report.txt and verified-images.json
were preserved. All archive contents used in testing were synthetic.

## Confirmed root causes and repairs

- Windows PowerShell 5.1 retained the Docker inspect array inside another array.
  Both tag and pinned inspections now assign parsed JSON before array normalization.
  The pinned raw JSON and original baseline bytes go directly to the Python spool;
  JSON reserialization no longer changes shape or conceals duplicate keys.
  The Python loader rejects empty, nested, multiple selected records, duplicate keys,
  invalid UTF-8, nonstandard JSON constants and malformed required metadata.
- The reported helper-metadata exception caused the subsequent filesystem-inspection
  incomplete-output failure. These are cascading diagnostics, not two proven independent
  image faults. Missing/malformed evidence still fails closed with sanitized stages.
- Docker stdout and stderr were merged and decoded by PowerShell's native pipeline.
  A shared ProcessStartInfo runner now resolves one executable, quotes Windows argv
  including quotes and trailing backslashes, decodes UTF-8 explicitly, and drains both
  pipes concurrently. Capture is bounded (64 Mi characters stdout, 1 Mi stderr),
  including overflow/invalid-encoding paths; excess output fails closed. Image save
  streams its archive directly to Docker's --output file, never into report memory.
  Helper stderr is rejected; Docker warning text cannot contaminate JSON/JSONL.
  Probe output/launch diagnostics are also rejected instead of trusting a stale exit code.
- The report whitelist rejected the digits in the mandatory sha256 evidence counter.
  It now retains that counter and rejects unexpected output. Completion, exit status,
  verdict, findings, unique required counters and verified-layer totals must agree.
  Missing/partial output, zero exit without evidence, abnormal termination and
  contradictory verdicts cannot pass. Final verdict derives from validated results;
  catch, cleanup and report-write failures force exit 1. The provisional report verdict
  is removed from the completed report to avoid contradictory final results.
- Filesystem reconstruction mishandled root opaque whiteouts, removed same-layer
  retained metadata, retained stale replaced metadata and failed to hide descendants
  below implicit directories. Corrected deletion/replacement ordering preserves opaque
  parent directories and same-layer additions; non-directory ancestors fail review.
  Historical files remain scanned even when later deleted. Malformed whiteouts fail.
- Saved config digests were accepted as arbitrary substrings of member names.
  Only exact digest.json and blobs/sha256/digest names now satisfy verification.
  Member reads verify size; manifest/schema/path normalization and incremental outer
  member limits reject ambiguous/corrupt archives. Layer SHA256 verification remains
  mandatory before filesystem inspection. No tar member is extracted onto the host.
- JSON escaping could conceal quoted secret assignments in metadata/history strings.
  Decoded string values are now scanned as well as serialized structures. Findings
  expose only fixed categories/counts, never values, private paths or file contents.
- Private spool creation now applies its restricted current-user ACL atomically on
  Windows PowerShell 5.1/.NET Framework, validates owner and rejects reparse ancestors.
  Cleanup validates path, owner SID, marker, marker reparse status, every child's type
  and the exact six-name allowlist before deleting individual files. Unexpected entries
  refuse deletion and force FAIL. No recursive deletion is used. An I/O/ownership
  failure may intentionally leave a restricted spool for manual review.

## Files changed

- audit-image.ps1: orchestration, native capture, spooling, evidence protocol, verdict.
- inspect_image.py: extracted the entire embedded filesystem helper for direct tests;
  added strict parsing, integrity, reconstruction and decoded-value scanning fixes.
- scripts/test_image_audit_offline.py: synthetic helper and full wrapper regressions.
- READINESS.md: current diagnosis, validation and remaining requirements.

image-baseline.ps1 was inspected and its existing 16-case suite rerun. Baseline bytes
are unchanged (SHA256 b97660bbbe57611d1e676334a673ac3d2f46bdb96ba8f7001b175632decb809c).
Historical report bytes are unchanged (SHA256
66d30d67fac9acafea46859cc263c9e871d24623f5afffe3b16be7e0ca55c2e0).

## Offline validation

Tested on Windows PowerShell 5.1.26100.9711 and actual Python 3.14.0, including the
isolated -I -S -B interpreter, .NET Framework C# compiler, ACL creation and cleanup.

- Audit regressions: 37 tests; valid metadata/archive; malformed JSON/encoding/types;
  identity mismatch; missing/corrupt/truncated archive members; empty inventory;
  whiteouts/replacements; JSONL; secret redaction; sensitive paths; Python startup
  hooks; subprocess failures, premature exit, missing counters and contradictory output;
  native quoting/Unicode, simultaneous large streams, output overflow and invalid UTF-8;
  complete mocked pipeline and guarded cleanup. A test-only helper with synthetic
  review gates removed exercises PASS calculation; production gates remain intact.
- Existing C621 offline/image/harness suites: 40 tests passed.
- Existing preview and preview-security suites: 11 + 6 tests passed.
- Synthetic application suite: 80 passed, in-memory SQLite/local memory email/cache.
- Configuration suite: 37 passed with synthetic configuration.
- Existing baseline suite: 16 cases and PowerShell parsing passed.
- Existing C61 synthetic socket probe: 10 scenarios passed; Compose/probe contracts
  and preview PowerShell lifecycle mocks passed. Mock cleanup messages did not refer
  to real containers. No service, development DB, Redis or SMTP was contacted.
- Python AST/embedded probe compilation, PowerShell parsing and whitespace checks passed.

Reproduce the audit-specific tests from D:\TechWorldWebsite:

```powershell
python -m unittest scripts.test_image_audit_offline -v
powershell.exe -NoProfile -File .\deploy\quick-client-demo\test-image-baseline.ps1
powershell.exe -NoProfile -File .\deploy\quick-client-demo\audit-image.ps1 -Python python.exe -TestPythonOffline
```

## Failure stages and genuine remaining blockers

The full pipeline was inspected: report destination/write; Docker and Python command
resolution; isolated interpreter/stdlib probe; baseline validation; tag identity;
pinned identity; private spool ACL/path/I/O; history capture; image save; helper
source/write/launch; helper metadata, history, archive, layer integrity/filesystem and
final inventory; output/evidence validation; content policy; guarded cleanup; final
report/exit. Each prerequisite and incomplete-inspection path remains fail-closed.

A successful offline test is not real-image evidence. Exact real tag/pinned identity,
all eleven real layers, private contents and runtime archive format remain unverified
in this session. If an archive format or resource limit prevents complete inspection,
the helper must FAIL; no fallback skips layers or executes image code.

The pre-existing mandatory independent startup/public-asset and dependency-integrity,
native-compatibility/provenance review gates remain unresolved. There is currently no
review-attestation input or evidence available to satisfy them. Consequently the
production helper still returns FAIL even for clean synthetic static content, with:

```
Failure stage: content-policy
Error category: mandatory-security-findings-or-review-evidence-missing
```

This is an explicit remaining policy/evidence blocker, not an implementation failure
or an automatic reuse/exposure approval. Removing these gates to produce PASS would
weaken existing guarantees. Static heuristic scans cannot certify arbitrary public
assets or dependency provenance. No real PASS is claimed or manufactured.

Python 3.14's extraction-filter change applies to extract/extractall; this audit uses
read-only extractfile and never those extraction APIs. References:
[Python tarfile](https://docs.python.org/3.14/library/tarfile.html),
[Docker save](https://docs.docker.com/reference/cli/docker/image/save/),
[Docker history](https://docs.docker.com/reference/cli/docker/image/history/).
PowerShell 7/non-Windows execution is not certified; the private ACL creation targets
Windows PowerShell 5.1. OS policy blocking Add-Type, insufficient TEMP storage,
cleanup ownership anomalies and Engine access failure correctly prevent PASS.

Run this single command in the user's authorized Windows PowerShell environment.
It saves/reads the existing image, overwrites only the sanitized audit report and
removes only its verified private spool; it does not build or start anything:

```powershell
powershell.exe -NoProfile -File D:\TechWorldWebsite\deploy\quick-client-demo\audit-image.ps1 -Python python.exe
```

Read the report's Final verdict, failure stage/category and fixed finding names.
No containers, Docker volumes, services, public listeners or tunnels were created,
modified or deleted by this repair.

---

# Quick client demo: BLOCKED

## Baseline validation repair - 2026-10-31

Reproduced the reported failure offline in Windows PowerShell 5.1. The expression
`@(Get-Content ... -Raw | ConvertFrom-Json)` produces one item whose value is the
entire two-record array. The tag filter retains that array through property
enumeration; `$baseline[0].Id` then contains both Django and Nginx IDs. Comparing
that collection to the one expected ID fails. This is a parser/array handling
bug, not evidence of an image identity mismatch.

The baseline is valid UTF-8 with BOM (`EF BB BF`), with a top-level JSON array
of two objects. Exact-case `Id`, `RepoTags`, `Config`, `RootFS`, `Os` and
`Architecture` fields are present. The Django record has all required comparison
fields and eleven layer digests. No required fields are missing. Optional
configuration keys absent in the captured inspection remain absent; no metadata
was added. Its Id and Descriptor.digest match the script's exact 64-character
SHA256 suffix ending `62587cdf`. The baseline was preserved byte for byte.

The read-only `image-baseline.ps1` validator assigns the parsed JSON before
normalizing the array, then selects exactly one case-sensitive Django tag and
checks the full identity. Fixed report categories now distinguish
`baseline-format-error` (including encoding/type/digest-shape errors),
`baseline-missing-fields` (with only allowlisted field names),
`baseline-tag-selection-error`, and `baseline-identity-mismatch`.
Invalid expected identity and validator loading also fail closed. Raw parser
exceptions and baseline values are not included in reports. Docker tag/pinned
identity checks, content scanning, layer verification, cleanup policy, and
mandatory final FAIL gates are unchanged.

Offline validation: 16 baseline regression cases passed, covering the actual
BOM baseline, UTF-8 without BOM, malformed JSON/encoding/structure, missing
fields, duplicate/missing tags, malformed IDs and a different valid full ID.
Windows PowerShell parsed all three audit/validator/test scripts successfully.
The existing isolated Python policy/stdlib probe and embedded Python AST checks
also passed. Run the baseline suite with:

```powershell
powershell.exe -NoProfile -File .\deploy\quick-client-demo\test-image-baseline.ps1
```

The existing `image-audit-report.txt` is preserved as historical failure
evidence. It has not been changed to PASS or replaced by an offline test result.
No Docker access, containers, services, public exposure or tunnel operations
occurred. Remaining blockers: the full private image-content audit has not run,
and independent startup/public-asset and dependency/provenance reviews remain
required. A successful baseline check grants no reuse or exposure approval.

From `D:\TechWorldWebsite`, rerun the audit in the authorized operator session:

```powershell
powershell.exe -NoProfile -File .\deploy\quick-client-demo\audit-image.ps1 -Python python.exe
```

## Audit diagnosis and repair - 2026-10-31

### Interpreter handling follow-up

The `python-version` / `python-version-or-launch-failed` category combined
version rejection with executable launch errors. The old `>= (3,12)` check
already accepted Python 3.14; matching the Docker image's Python 3.12 was never
required. Offline reproduction found multiple `python.exe` applications on PATH:
`Get-Command` returned multiple sources, which became one invalid executable name.
The script now selects the first resolved application, or accepts an explicit
trusted executable path through `-Python`. This explains the reproduced failure;
the sanitized report alone cannot prove the cause on another machine.

The helper imports only the standard library. Its minimum is Python 3.6
(regular-expression Match subscripting and pathlib arguments to tarfile); the
shared policy accepts major version 3, minor 6 or later, including 3.12 and 3.14.
Use a maintained trusted Python installation. Unsupported major versions fail
closed. The isolated `-I -S -B` probe also exercises required stdlib functionality.
Probe code travels through stdin to avoid native `-c` quoting differences.
Version rejection now reports `python-version-unsupported`; launch or stdlib
failures report `python-launch-or-stdlib-probe-failed`. Native output stays private.

Run the offline regression test from `D:\TechWorldWebsite`:

```powershell
powershell.exe -NoProfile -File .\deploy\quick-client-demo\audit-image.ps1 -Python python.exe -TestPythonOffline
```

This tests the shared policy against 2.7, 3.5, 3.6, 3.12, 3.14, future Python 3
minors and 4.0, plus the actual interpreter's isolated stdlib probe and executable
resolution. It exits before report writes, Docker discovery or calls, and spool
creation. It passed on host Python 3.14.0, including multiple PATH installations.
PowerShell parsing also passed. These tests do not inspect an image. Identity,
all-layer scanning, inventory reconstruction, sanitized reporting, cleanup checks
and mandatory manual FAIL gates are unchanged.

The saved `image-audit-report.txt` records an incomplete FAIL, with no inspection
counts or cleanup record. It does not identify the original exception; the
exact failing operation cannot be recovered from that report. It remains
historical evidence and was not rewritten by this repair.

The script's expected Django ID is exactly the captured `Id` in
`verified-images.json`, its `Descriptor.digest`, and the digest recorded in
`docs/pre-deployment-validation.md`. Its SHA256 suffix has exactly 64 lowercase
hexadecimal characters, ending `62587cdf`. There is no extra trailing character
in these files. Do not trim or substitute an assumed ID. The captured descriptor
is an OCI image index: the saved configuration digest need not equal the index
ID. Keep tag and pinned-ID comparisons, baseline configuration/RootFS comparisons,
saved-config digest verification and every layer's diff-ID verification.

Other possible early stops include an unavailable Docker/Python executable,
Docker configuration or Engine access denial, a missing/invalid baseline or
changed tag, unsafe/unwritable report destination, TEMP location rejection,
Windows ACL/owner setup failure, spool I/O or insufficient disk space, Docker
history/save failure, and unsupported Python. During filesystem inspection,
malformed or unsupported save archives, duplicate/unsafe tar names, layer digest
mismatches, resource limits, missing fields, or helper exceptions also stop the
audit. These are possible causes, not findings about the historical failure.

The repaired script checks compatible host Python 3 explicitly and reports fixed failure
stages and error categories. Helper exceptions emit only allowlisted stage and
category strings; PowerShell records the enclosing failure separately. Raw
exception messages, native stderr, file paths and secret values remain private.
Cleanup failures and final report-write failures also have sanitized diagnostics.
A cleanup failure can require private manual TEMP review; never publish its files.

Filesystem inspection is mandatory. A completed static inspection still returns
FAIL and blocks reuse pending independent startup/public-asset and dependency/
provenance reviews. No failure is automatically converted to PASS. This repair
changes only the audit script and this document; captured metadata and the saved
report are preserved. No Docker commands, containers, development services or
Cloudflare Tunnel were executed or changed.

Offline validation passed: Windows PowerShell parser, embedded Python AST,
isolated helper missing-spool failure with fixed diagnostics and empty stderr,
and retained mandatory manual FAIL gates. No real image-content inspection was
performed by these checks.

From `D:\TechWorldWebsite`, rerun in the operator's authorized Windows PowerShell:

```powershell
powershell.exe -NoProfile -File .\deploy\quick-client-demo\audit-image.ps1 -Python python.exe
```

This rerun requires Docker Engine read access, trusted host Python 3.6+ (major 3) and
sufficient private TEMP storage. It inspects/saves the existing image without
creating or starting containers. Exit code 1 remains intentional even when static
inspection completes; read `Inspection: COMPLETE` versus the failure-stage lines.

## Current assessment after verified image metadata review - 2026-10-31

This section supersedes the historical attempts below. The supplied
`verified-images.json` is accepted as inspection evidence from the user's
authorized PowerShell session. Docker was NOT accessed again. Image metadata
is now available; missing metadata is no longer the blocker.

Verified supplied image IDs (linux/amd64 for both):

- Django: `sha256:69c0b8cdfa8a03b9517d6bd9a80bb1afc7c024ee355e78ac79effa3c62587cdf`.
  Configured user `appuser`, working directory `/app`, no declared volumes,
  no configured entrypoint, command runs Gunicorn with `config.wsgi:application`.
- Nginx: `sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5`.
  No configured user (root by default), working directory `/`, no declared
  volumes, inherited `/docker-entrypoint.sh`, command `nginx -g 'daemon off;'`.
  A demo would need an explicit non-root user and entrypoint override.

The supplied environment lists contain no obvious application credential
variables. This is a check of configuration metadata, not a secret/content
audit of the image filesystem or its layers.

### Remaining blocking evidence

The required private image-content/provenance verdict is still absent. The
existing Django Dockerfile uses `COPY . .`; current `.dockerignore` rules and
the image configuration cannot establish what the October 28 image actually
copied. Neither supplied inspection record establishes the absence of baked
development secrets, private uploads/data, executable Python startup hooks
(`.pth`, `sitecustomize`, `usercustomize`), or modified dependencies. It also
does not establish installed executable/dependency paths or a reviewed public
template/static inventory. Current source paths are not proof of image paths.

Network isolation, environment overrides and read-only mounts would not remove
baked files or stop Python import hooks from running. Pinning the image ID
establishes identity, not safe contents. A fresh demo key cannot fix that gap.
Per the user's stop condition, preparation stops here: no runnable Django,
Nginx, Compose configuration or lifecycle scripts have been generated, and no
demo secret has been created unnecessarily.

To unblock, supply a private review verdict tied to these exact image IDs:
confirm no baked development secrets/private data or unapproved execution
hooks, and identify reviewed Python/Gunicorn paths, dependencies, public
templates/static paths and runtime-readable ownership. Supply only the verdict
and non-secret inventory, never secrets or private contents. No repeat Docker
inspection is requested by this document.

### Application findings and offline checks for this attempt

Read current Dockerfile, ignore rules, requirements, standalone preview
settings/routes/boundary, public views and SEO context processor. Public core
views render templates without model queries. Existing standalone preview
settings demonstrate dummy DB, local-memory cache and dummy email without
normal settings imports. Existing preview is not a safe substitute as-is: it
accepts wildcard tunnel hosts, and boundary error responses bypass its final
noindex/no-store header assignment. Normal Gunicorn command must be overridden
to avoid importing development settings.

Offline checks performed with the workspace Windows Python, without importing
application modules or invoking Docker:

- Both supplied records parsed; exact SHA256 ID shape, linux/amd64, absent
  declared volumes and absence of obvious credential variable names checked.
- AST parsing passed for five inspected Python modules.
- Whitespace check for this readiness document passed.

These checks do not validate image execution or certify isolation. Previous
test totals below are historical and were not rerun for this attempt.

### Runtime gates and lifecycle commands

After the content gate is satisfied, implementation must still enforce a
separate `codeventra-quick-client-demo` project, pinned image IDs, no pull/build,
standalone DEBUG=False settings, fresh demo-only key, dummy DB/email and
in-memory cache, no PostgreSQL/Redis/SMTP, no private mounts, explicit GET/HEAD
route and static-asset allowlists, blocked POST and other mutating methods,
exact localhost hosts, universal noindex/no-store headers, and loopback-only
`127.0.0.1:8765`. Django should have no network and communicate through a
dedicated Unix socket with non-root Nginx on a separate internal ingress
network. Use read-only filesystems, dropped capabilities, no-new-privileges,
bounded temporary storage and demo-only mounts.

Remaining runtime verification: installed dependencies/executables and startup
hooks; Django system checks; Nginx syntax; numeric UID/GID ownership and socket
permissions; resolved Compose policy; no inherited/extra mounts or development
network attachments; actual loopback binding and egress isolation; GET/HEAD,
denied paths, malformed/encoded paths, invalid hosts, spoofed forwarded headers,
POST/other methods, error headers and absent side effects. Any future tunnel
needs separate approval and an exact reviewed hostname at both boundaries.

There are no safe exact startup/shutdown commands yet because the required
configuration and identity-guarded lifecycle implementation have not been
created. Do not run a placeholder Compose command or existing preview scripts.
Exact commands must be supplied with the completed, reviewed implementation
after this blocker is resolved. Runtime approval alone does not resolve an
unreviewed image-content gate.

No containers, networks, volumes or tunnel were created, so this attempt
requires no runtime shutdown or cleanup. Existing development files and
containers were left untouched; only this demo readiness document was updated.

---

## Historical record (superseded by the assessment above)

## Latest preparation attempt — 2026-10-31

The latest request contains a `USER-VERIFIED IMAGE INSPECTION:` heading with
no metadata beneath it. No verified image IDs or image configuration were
provided. Per the explicit instruction to stop if metadata is insufficient,
no runnable quick-demo Compose configuration or lifecycle scripts were generated.
Docker was not invoked again, including Compose configuration commands. The
user's normal PowerShell Engine access is acknowledged; it does not supply the
missing image evidence to this session.

Required non-secret evidence for BOTH existing local images remains: full
sha256 config image ID, OS/architecture, configured user, working directory,
entrypoint, command, declared volumes, and a private review verdict for inherited
environment/hooks and baked credentials, uploads or other development state.
For Django, also establish the Python/Gunicorn executable paths, available
dependencies, application/template/static paths and runtime-readable public
assets. Do not paste secret environment values or private file contents.
Image tags and the source Dockerfile alone cannot establish these facts.

Reinspected public views and existing preview files: core homepage, services,
about, privacy and terms render without model queries; normal projects query
the database and can reference uploads; contact POST persists submissions and
sends email. Existing preview templates already supply explicitly fictional
projects and a disabled contact page. They are useful source material, but the
existing preview image/build flow and wildcard tunnel-host policy must not be
substituted for the requested isolated reuse of existing images.

Offline verification rerun with the Windows .venv (not the images):

- Existing preview tests: 11 passed; preview security tests: 6 passed.
- Dependency-image offline contracts: 6 passed.
- C621 offline contracts and mocked harness: 34 passed.
- Synthetic launch application suite: 80 passed, using disposable in-memory
  SQLite, local-memory cache and local-memory email; no development database,
  Redis or SMTP was contacted.
- Preview PowerShell parser and mocked lifecycle safety checks passed. Printed
  stop/remove messages were mocks only; no real Docker operations occurred.
- Standalone preview Django system check: no issues; git diff --check passed.

These 137 Python tests exercise existing code only. There is no new runnable
quick-demo configuration to certify. Runtime validation has NOT passed.
Still unverified: image identity/content, Linux executables and dependencies,
Nginx syntax, non-root ownership, read-only mounts, Unix socket sharing and
permissions, absence of inherited volumes, network isolation, actual loopback
publication, HTTP boundary behavior and tunnel behavior.

No containers or tunnel were started and no Docker resources were created.
Rollback for this attempt requires no runtime action. Do not run existing
preview cleanup tooling or development Compose commands on its behalf. Only
this readiness document was changed by this attempt; existing work was preserved.
The historical notes below describe earlier attempts, not fresh Docker access.

Inspection date: 2026-10-31. No runnable quick-demo configuration was generated.
The requested safety contract requires stopping when safe implementation cannot
be established. Existing preview files and all prior user changes were preserved.

## Blocking evidence

Read-only `docker image inspect techworld-django:local nginx:stable-alpine`
failed: access denied reading Docker config.json and connecting to the Engine
named pipe. The supplied historical application image ID is not independently
verified. Image users, entrypoints, environment, baked files, static assets,
dependencies, architecture and inherited volumes remain unverified.

The source Dockerfile uses COPY . .; present ignore rules do not establish what
historical image layers contain. A read-only runtime filesystem or network_mode:
none would not prevent serving or reading secrets already baked into an image.
No credentials, dotenv, private uploads or development records were inspected.

Existing deploy/client-preview uses a separately prepared image, not the requested
existing application image. It cannot be substituted without image review. Both
its application and Nginx boundaries accept arbitrary syntactically valid single
label trycloudflare.com hosts. That policy does not meet this task's exact-host
requirement. Existing files were not weakened or altered.

## Source findings and intended isolation

Core homepage, services, about, privacy and terms views render templates without
database queries. Normal portfolio views query Project records and reference
uploaded cover images and external project links. Normal contact POST saves a
model (including private attachments) and sends SMTP mail. Normal settings load
dotenv and enable database-backed sessions/authentication and analytics; analytics
can write visit records. Rate limiting uses cache. Browser theme code uses
localStorage. These normal settings and routes must not be used for the demo.

Existing standalone preview settings avoid importing normal settings: dummy DB,
local-memory cache, dummy email, no sessions/authentication/analytics middleware,
synthetic portfolio and disabled contact form. Existing templates and CSS/JS
render locally in offline tests. TrustedProxyIPMiddleware is omitted by the
preview; normal production mode requires a trusted Unix transport marker and
must not be enabled blindly. Preview ignores forwarded protocol/host headers;
Nginx clears forwarded headers. Cloudflare HTTPS termination does not require
trusting arbitrary incoming X-Forwarded-Proto.

After image review, the intended new project is codeventra-quick-client-demo:
Django network_mode none, Unix socket shared only with separate Nginx, isolated
internal ingress network, only 127.0.0.1:8765 published, no development mounts or
environment, fresh demo key, non-root/read-only containers, dropped capabilities,
no-new-privileges and bounded temporary writable paths. Images must be pinned to
observed exact local IDs with pulls forbidden. Startup and cleanup must validate
project/run labels and recorded container/network/volume identities before any
mutation. Local hosts only initially; any tunnel hostname requires an exact
reviewed allowlist update at both boundaries. No wildcard tunnel acceptance.

## Actual validation

Using the existing Windows .venv Python, not the Docker image:

- scripts/test_client_preview.py: 11 tests passed.
- scripts/test_client_preview_security.py: 6 tests passed.
- Standalone preview Django system check: no issues.
- AST syntax parsing of preview and preview-helper Python files: passed.

These results validate existing preview behavior only, including its current
wildcard-host policy; they do not certify that policy for public exposure.
Docker Compose CLI reports v5.5.1. No new resolved Compose configuration exists
to validate. No Nginx or cloudflared executable was found on PATH. Nginx syntax,
Linux image execution, socket permissions, Docker networking, runtime ownership,
HTTP ingress and Cloudflare behavior remain unverified. No services were started.

## Next step and operational gates

There is no safe startup command yet. In an authorized Docker session, the next
read-only command is:

```powershell
docker image inspect techworld-django:local nginx:stable-alpine --format '{{.Id}} {{.Os}}/{{.Architecture}} user={{json .Config.User}} workdir={{json .Config.WorkingDir}} entrypoint={{json .Config.Entrypoint}} cmd={{json .Config.Cmd}} volumes={{json .Config.Volumes}}'
```

Then complete private image-content/provenance review without printing secrets,
implement the new isolated overlay and guarded lifecycle scripts, and validate
the resolved Compose and Nginx configurations before requesting startup approval.
Do not use the existing preview startup script for this quick-demo request.

Future local acceptance: GET/HEAD approved public pages, robots.txt and approved
static assets return 200; admin, health, API, authentication, operational, media
and private paths return 404; state-changing methods return 405; invalid Host
returns 400; forwarded header spoofing must not change trust or scheme. Every
response should carry noindex/no-store protections. Test path normalization too.

No tunnel command is approved or executable as part of this preparation. After
separate public-exposure approval and verification that `cloudflared --version`
reports 2026.10.7, the intended command is:

```powershell
cloudflared tunnel --url http://127.0.0.1:8765 --no-autoupdate
```

The generated URL must be HTTPS with exactly one DNS label under
trycloudflare.com, no userinfo, port, path, query or fragment. Keep public requests
denied until that exact hostname is reviewed and installed at both boundaries.
Verify the HTTPS certificate normally and repeat public/denied-route checks via
that exact URL. Tunnel startup itself requires separate approval.

Shutdown/rollback commands cannot be finalized until guarded lifecycle tooling
and recorded resource identities exist. Stop the separately owned tunnel first;
verify exact demo IDs, project/run labels and network attachments before stopping
or deleting only those demo resources. Never run docker compose down on the
development project techworldwebsite; never prune resources or remove development
volumes. This task created no Docker resources requiring rollback.

No development containers, databases, volumes, secrets, existing configuration or
existing preview files were modified. No tunnel was started, no new port exposed,
and no Docker run/build/pull/create/start/up/down operation was performed.
