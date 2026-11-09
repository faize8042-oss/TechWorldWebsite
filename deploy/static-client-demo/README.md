# Codeventra Labs static client demo

Independent static export of the existing public design. No Django image, application process, database, Redis, SMTP, credentials, private uploads, or development mounts. The container serves only `site/`, with explicit URL allowlists; build scripts and manifests are not served. No Dockerfile or application build is used.

## Pages and source

Home, About, Services, Projects, Contact, Privacy and Terms use the corresponding public templates in `templates/core`, `templates/projects/project_list.html`, `templates/contact/contact.html`, and the existing navbar/footer. The ten CSS/JS files are copied byte-for-byte from the explicit list in `build.py`. The public `static/` tree contains no image assets; the current illustrations and brand mark are CSS/HTML. No media or private upload directory was inspected or copied.

Projects uses the existing empty-state design with a demo-specific explanation: database-backed portfolio records were not accessed, and no approved public portfolio export was found in the inspected source. No fictional projects, testimonials or clients are included. Contact retains the public layout with disabled fields and a clear demo notice, without a form or upload control. Nginx also rejects write methods and sets `form-action 'none'`. Legal pages carry a notice distinguishing the full website policy from demo behavior.

## Offline rebuild and checks

Run from `D:\TechWorldWebsite` (Python standard library; Node is needed for JS interaction checks):

```powershell
python deploy/static-client-demo/build.py
python deploy/static-client-demo/check.py
node deploy/static-client-demo/check-interactions.cjs
docker compose -f deploy/static-client-demo/compose.yaml config --quiet
```

The generated `site/` is ready to serve; rebuilding is optional. The builder reads only named public templates and ten allowlisted public CSS/JS assets, never imports Django, and refuses unexpected existing output files. `public-manifest.json` records SHA-256 hashes. Checks enforce the exact served-file list, hashes, internal links, fragments, CSS assets, navigation, disabled submissions, suspicious secret patterns, no backend references, and isolation settings. JS checks execute the actual scripts in a DOM model to verify theme persistence, mobile menu, Escape/focus, navigation clicks, outside clicks, resize, and footer year. No dependency installs or network access are required for these tests.

## Start (operator action)

```powershell
docker compose -f deploy/static-client-demo/compose.yaml up -d
```

Open **http://127.0.0.1:8765/**. Compose uses the independent project name `codeventra-static-client-demo` and the official `nginx:stable-alpine` image. It may need to download this image on first startup. It binds only loopback, runs as UID/GID 101, mounts only the generated public site and this demo's Nginx configuration read-only, and has no persistent volumes. The image tag is floating; record/pin a verified digest if reproducible distribution becomes necessary.

## Local verification after startup

```powershell
python deploy/static-client-demo/verify_http.py
docker compose -f deploy/static-client-demo/compose.yaml logs --tail 30 demo
```

The HTTP check only targets `127.0.0.1:8765`; it verifies every asset hash, security headers, blocked sensitive/backend paths, rejected write methods, and HEAD support. Visually inspect all pages at desktop, 768px and 375px widths, check for horizontal overflow, test mobile menu and Escape, switch both themes, and confirm the contact controls stay disabled.

## Shutdown

```powershell
docker compose -f deploy/static-client-demo/compose.yaml down
```

This targets only the named demo project. No development containers or volumes need to change.

## Verification status

Offline Python checks (5 groups), actual-script Node interaction checks, deterministic rebuild, JavaScript syntax checks, Python syntax checks and Compose configuration validation passed. Docker emitted a warning that its user config file was inaccessible; Compose validation still returned exit code 0. No containers or tunnel were started. Nginx runtime and HTTP checks remain pending operator startup. Browser visual review was blocked because computer use was not approved for Chrome; responsiveness is retained from the source CSS but has not been visually verified. This is a prepared local demo, not an approved public deployment.
