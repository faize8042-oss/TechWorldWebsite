# C6.2.1 PostgreSQL security hardening

Repository implementation proposal, 2026-10-29. **Not production ready.** No SQL,
Docker daemon operation, migration, connection to a database, or infrastructure
change was performed. No environment files, credentials, validation-results, or
private uploads were read. All validation inputs were synthetic.

## 1. Current architecture and baseline

Verified clean branch `feature/codeventra-ui`, HEAD
`8e0f257d8977f36ffcf35436db39471f3f9f0917` before editing. C6.1 is the committed
baseline. `compose.yaml` remains unchanged. Only `deploy/compose.production.yaml`
is changed for deployment topology. PostgreSQL remains version 17, unpublished,
on internal `data`; Redis/web share `data`, Nginx uses `proxy`. Web and Nginx alone
mount the private Gunicorn socket. Web UID/GID 10001:10002, dropped capabilities,
read-only root, socket ownership checks, proxy marker validation, HTTPS gate,
disabled HSTS and disabled indexing remain intact.

The prior production proposal passed a shared `env_file` into web and interpolated
administrator passwords into Compose. These are removed. This is a breaking
production-template contract change; old C6.1 activation/harness inputs are not
compatible with the new secret contract. Historical C6.1 results remain historical;
the C6.1 harness must not be reused unchanged to validate C6.2.1.

## 2. Threat model and trust boundaries

A compromised web process must not own tables, perform schema DDL, create roles,
bypass RLS, or obtain migration/administrator/backup credentials. It necessarily
can read and change application data within its runtime DML grants. Database
permission boundaries complement the C6.1 socket boundary. Nginx has no database
secret. Host root, Docker administrators, secret custodians, approved migration
code, and provisioning operators remain trusted. A migration login able to SET
ROLE owner can change/drop application objects; treat its exposure as high impact.

Configuration checks validate declared identities and secret placement only.
They cannot establish actual role flags, ACLs, memberships, ownership, HBA rules,
or server identity without connecting. No connection is made by these checks.

## 3. Role architecture and permission matrix

Identifiers are deliberately fixed and reviewed, not substituted from shell input.
Database: `codeventra`; application schema: `public`. Changing identifiers requires
coordinated source/template review. Never use string replacement on untrusted names.
The type ACL loop uses PostgreSQL `format('%I', ...)` identifier quoting.

| Identity | Login | Database / schema | Tables / sequences | Membership and special flags |
| --- | --- | --- | --- | --- |
| `cv_init` | Yes | Initialization DB owner / controlled provisioning | Administrator only | PostgreSQL image initialization superuser; never Django or ordinary migrations |
| `cv_owner` | No | Owns public schema, not database | Owns application objects | No superuser, createdb, createrole, replication or bypassrls; no parent memberships |
| `cv_migrate` | Yes | CONNECT; schema access after SET ROLE | Owner DDL/DML after SET ROLE | NOINHERIT; only cv_owner membership, SET TRUE, INHERIT FALSE, ADMIN FALSE; no special flags |
| `cv_runtime` | Yes | CONNECT, public USAGE; no CREATE/TEMP | SELECT/INSERT/UPDATE/DELETE; sequences USAGE/SELECT | NOINHERIT; no memberships or special flags; no ownership, TRUNCATE, REFERENCES, TRIGGER or MAINTAIN |
| `cv_backup` | Yes | CONNECT, public USAGE; no CREATE/TEMP | SELECT only, including sequence state | NOINHERIT; no memberships or special flags; read-only default as defense in depth |

PUBLIC loses database privileges (including CONNECT/TEMP), schema privileges,
application table/sequence privileges and routine EXECUTE. Existing independent types, including standalone composites,
are explicitly reconciled. Owner defaults grant future table DML and sequence
USAGE/SELECT to runtime, SELECT to backup, type USAGE to both; global PUBLIC
routine EXECUTE/type USAGE defaults are revoked. Both global and public-schema
default grants for the three login roles are cleared before minimal grants are rebuilt,
so stale broad default grants do not survive reconciliation. No routine EXECUTE is granted
automatically: future migrations needing functions must grant specific safe
signatures in reviewed migrations. Global defaults matter: schema-only REVOKE
cannot undo global defaults. Defaults apply to the role creating objects, hence
**every migration connection must SET ROLE cv_owner**, including reconnects.

PostgreSQL 17 public schema may initially belong to `pg_database_owner`; upgraded
clusters may retain older PUBLIC CREATE grants. Neither is assumed safe. Fresh
provisioning explicitly assigns schema ownership and revokes PUBLIC. Database
ownership stays with the administrator so the owner role cannot create schemas
or extensions requiring database CREATE. Built-in pg_catalog objects stay outside
the application policy; inventory other databases, schemas and extension grants.

References: [PostgreSQL 17 privileges](https://www.postgresql.org/docs/17/ddl-priv.html),
[role membership and options](https://www.postgresql.org/docs/17/sql-grant.html),
[default privileges](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html),
[Django 5.2 assume_role](https://docs.djangoproject.com/en/5.2/ref/databases/#role).

## 4. Fresh empty database provisioning — future approved operation only

1. Approve immutable images, isolated target identity, secret custody, network/HBA
   policy, SCRAM authentication and backup/recovery arrangements. Use no trusted
   host/remote authentication for application roles. The image creates cv_init
   and codeventra using its dedicated administrator password file.
2. Confirm empty database, intended cluster/database, version and database owner.
   `deploy/postgres/fresh.sql` is a manual template, **not** an entrypoint mount.
   It checks session/database and emptiness, creates the four roles atomically
   with null passwords, assigns schema ownership and migration membership.
   Run through a controlled private psql session with `-X -v ON_ERROR_STOP=1`.
   A repeated run fails safely on existing roles; do not swallow duplicate errors.
3. Review and apply `deploy/postgres/grants.sql` in the same maintenance window.
   It verifies ownership, role flags/memberships, then reconciles ACLs/defaults
   transactionally. It is repeatable for this reviewed architecture, but is not a
   general repair script. Keep application logins passwordless until this passes.
4. Privately set independent SCRAM passwords with psql `\password cv_runtime`,
   `\password cv_migrate`, `\password cv_backup` under the approved credential
   ceremony. Do not use SQL password literals, shell variables expanded into
   commands, password URLs in arguments, psql `-v` secrets, command echo or history.
   Configure safe server/client logging; password hashes are sensitive too.
5. Supply protected runtime/migration/backup files through the secret manager;
   perform controlled migrations as below, then verify live permissions before
   admitting traffic. Initialization administrator never runs Django migrations.

No init scripts are automatically rerun by this proposal. PostgreSQL initialization
only applies to empty PGDATA; changing image environment on an existing volume
does not recreate users, change passwords or apply ACLs. Reconciliation is a
separately approved operation. Fresh provisioning is repeatable as a procedure
on a fresh isolated target, not idempotent adoption of an unknown cluster.

## 5. Existing database migration strategy — separate change approval

Never run fresh.sql on an existing database. Never automatically change ownership.
Before any SQL, obtain approval for read-only inventory and confirm cluster,
database, operator identity and maintenance window. `inventory.sql` is a read-only
review template and intentionally excludes password hashes/pg_authid. Capture
role flags/memberships, databases, schema/object owners, relation/routine/type ACLs,
defaults, RLS, extensions and policy dependencies; supplement it for other
schemas, large objects and objects outside public. Treat inventory as confidential.

Obtain verified logical and physical backups plus an independently tested restore;
record the old owner and ACL for every object and defaults/memberships to change.
Inventory active clients and scheduled jobs. Decide explicitly whether to adopt
objects in place or restore into a separately provisioned new target. Prefer a
rehearsed restore/cutover when ownership is complex. No REASSIGN OWNED or DROP OWNED
commands are supplied: they affect objects beyond a reviewed application list.

Prepare a signed per-object plan with correctly quoted identifiers, explicit
ownership changes, role creation if absent, approved membership/flag changes,
client credential cutover and reverse statements derived from the inventory.
Do not transfer extension-owned objects indiscriminately. Existing owner roles,
SECURITY DEFINER routines, custom types and non-public schemas need individual
review. Do not blindly apply grants.sql: it revokes ACLs and will stop if ownership
or role flags/memberships differ. Validate roles do not own objects elsewhere and
have no privileges from other roles, PUBLIC, foreign schemas or databases. The
checks in grants.sql are necessary preconditions, not exhaustive cluster audit.

After explicit operator approval, quiesce writers, execute only the approved
adoption steps, then use grants.sql after its preconditions hold. Test runtime,
migrations, backup/restore and ownership. Re-enable traffic only with signed
acceptance. Retain the prior deployment, protected credentials and backups under
a time-bounded recovery plan. Do not print secrets into the change record.

## 6. Django runtime connection configuration

Production starts with DEPLOYMENT_MODE=production and fixed
PRODUCTION_RUNTIME_FILE=/run/secrets/django_runtime. The loader skips dotenv
regardless of CODEVENTRA_SKIP_DOTENV. A JSON object contains string values only,
using the explicit RUNTIME_KEYS allowlist in config/production_database.py.
Required application settings include DATABASE_URL, SECRET_KEY, ALLOWED_HOSTS,
CSRF_TRUSTED_ORIGINS, REDIS_URL and SMTP/contact settings; optional keys are
listed in that module. Do not include DEBUG, deployment gates or privileged keys.

DATABASE_URL has structure `postgresql://cv_runtime:<URL-encoded-password>@db:5432/codeventra`.
The password placeholder is explanatory, never an actual credential template.
Only postgres/postgresql, exact cv_runtime/db/codeventra identity, an actual
password, port 5432 (or omitted), and no query/fragment are accepted. Django options
are pinned to `-c search_path=public`; runtime cannot request an owner role in the
URL. Ambient database/libpq/privileged variables and ambient application config
are rejected with value-free errors. The runtime settings identify cv_init as
initialization administrator and enforce runtime-secret-v1. Deployment system
checks enforce PostgreSQL, identity separation, credential presence and options.

Production never imports an application env_file. Development keeps its existing
dotenv behavior and DATABASE_URL handling unchanged. Only safe synthetic tests
use CODEVENTRA_SKIP_DOTENV; no actual environment file was accessed in this task.

## 7. Controlled schema migration workflow

Use an approved ephemeral operator runner on the private database network, with
no published ports, no proxy socket, no administrator secret, and no backup
secret. Do not add migration credentials to web, a shared env_file, or interpolation.
The operator-profile migration service never starts automatically; its default command prints the plan only.
Approve a runner manifest and digest separately; mount only the runtime JSON and
/run/secrets/django_migration, a protected JSON object containing DATABASE_URL for
cv_migrate (same db/host rules, no URL options). Its trust level exceeds web's.

First run normal runtime settings checks, review migrate --plan, backup and review
migration SQL/data operations. In the approved runner only, use:

```
python manage.py migrate --settings=config.migration_settings --plan --skip-checks
python manage.py migrate --settings=config.migration_settings --skip-checks
```

These are future commands, not executed here. The migration settings validate the
separate secret and use Django 5.2 OPTIONS.assume_role=cv_owner (explicit SET ROLE on each new
connection), with search_path pinned to public. This makes current_user
cv_owner while session_user remains cv_migrate. The runtime connection is not
opened merely by importing base settings. --skip-checks is intentional only here:
the web checks reject migration credentials, so Gunicorn cannot start under these
settings. Run the full normal production checks with runtime settings beforehand;
never use --skip-checks as a general workaround. Other migration-related commands
must be reviewed for equivalent settings/check behavior.

Before DDL, verify session_user/current_user, schema owner and target in the
approved live workflow; after DDL inventory owners and verify defaults on new
objects, including django_migrations, indexes, sequences, constraints and RunSQL/
RunPython results. Reject migrations that RESET ROLE, change ownership, grant
runtime DDL, install privileged extensions or use separate unreviewed connections.
Extensions, custom routines, RLS and non-public schemas require explicit reviewed
provisioning/grants; don't elevate the migration login to superuser. Remove the
runner and revoke its credential access after the window. No normal requests
use cv_migrate. Future SQL logging must not contain data/credentials.

## 8. Secrets and credential isolation

| Protected input | Recipient | Access model |
| --- | --- | --- |
| Compose interpolation file | Compose operator | Only approved image digests, secret file paths; no passwords/URLs. Keep outside repository; do not use a shared production environment file. |
| Administrator password file | db only | POSTGRES_PASSWORD_FILE points to /run/secrets/postgres_admin_password; no value interpolated into YAML. |
| Runtime JSON | web only; approved migration runner when needed | Only allowlisted Django settings and cv_runtime URL; no privileged identities or credentials. |
| Migration JSON | Explicit operator runner only | No service/mount in ordinary production Compose. |
| Backup password/service files | Backup runner only | No service/mount in ordinary production Compose; use protected PGPASSFILE and non-secret libpq service metadata. |
| Redis password + Redis config | redis only | Configuration file has requirepass and existing save/appendonly/maxmemory policy; password file for healthcheck, kept in sync. Runtime JSON has only authenticated Redis URL. |

Protected files must reside outside the repository and all image/build contexts.
Use a secret manager or protected host directory (0700, custody by deployment
operator); runtime file readable only by UID10001/restricted GID10002, administrator
file only by intended db bootstrap identity, and Redis files by intended Redis
identity. Validate actual Linux mount owner/mode (no world readability/writability)
and absence in other services. Local Compose secrets are bind-mounted files, not
an encrypted secret store; uid/gid/mode declarations are not reliable ownership
remapping for file sources. Prepare host permissions explicitly and fail deployment
review if mount access is broader than intended. Host/Docker root can read them.

Runtime secrets become web process environment/settings after allowlist loading;
they remain accessible to a compromised web process and trusted process inspectors.
They are not administrator/migration credentials. Never dump environment, Django
settings, Compose interpolated output, libpq exceptions, connection strings or
secret file contents to diagnostics. Django DEBUG remains False. Do not use
`docker compose config` with a shared secret environment; even future rendering
must use only public interpolation metadata. Turn off shell tracing/history for
credential ceremonies. Do not pass passwords as arguments, including backup URLs.

Redis formerly expanded its password into process arguments. It now receives a
protected full Redis config mount and a separate healthcheck password mount. The
config must contain the existing `save ""`, `appendonly no`, `maxmemory 128mb`,
`maxmemory-policy allkeys-lru` and correctly quoted `requirepass` directives; author
it through the secret manager, not shell concatenation. Verify config and health
password consistency privately. This small adjacent change is needed to remove
secret interpolation without moving password exposure into process arguments.
Redis config/auth startup is deferred to isolated validation too.

## 9. Backup role limitations

cv_backup can SELECT application tables and sequence state, but cannot nextval,
setval, DML, DDL, SET ROLE owner, or bypass RLS. default_transaction_read_only is
only defense in depth: it can be reset, so ACLs provide enforcement. Logical
backups contain sensitive data; encrypt output and control access/retention.

Use a compatible PostgreSQL 17 pg_dump client with protected PGPASSFILE (0600) and
non-secret connection metadata, normally `--schema=public --no-owner --no-acl`.
Do not put passwords in argv or URLs. This is not a full-cluster backup: role
passwords/globals, other schemas, large objects, extension data, replication and
physical/PITR recovery require separate reviewed procedures. Future RLS tables
can cause pg_dump failure with its default row_security=off; --enable-row-security
may silently produce only policy-visible data and is not an accepted complete
backup. Stop and design audited backup policies or another approved backup path;
do not grant BYPASSRLS/superuser to fix failures. Restore requires pre-provisioned
roles/schema and an approved owner-role restore session; runtime cannot restore
DDL. Test completeness and restore independently before production acceptance.

## 10. Credential rotation

Rotate each login separately through approved secret management and a private
administrative password ceremony. PostgreSQL has one active password per role;
coordinate the password change with atomic protected file replacement and
approved client reconnection/recreation. Update runtime URL only in runtime JSON,
migration URL only in its file, backup passfile only in backup custody, and Redis
config/password/runtime Redis URL together. Existing pooled sessions may remain
authenticated; approve explicit session termination if required. Plan interruption
and verify both old credential rejection and new credential success privately.
Administrator rotation on an existing volume requires an actual approved ALTER
ROLE/password ceremony; changing POSTGRES_PASSWORD_FILE alone does not rotate it.
No secret rotation was attempted. Never broaden role grants during rotation.

## 11. Rollback and recovery

Before changes, capture exact owners, ACLs, defaults, memberships, settings and
client configuration, plus tested backups. Fresh SQL and grants transactions fail
atomically individually; the two files are not one combined transaction. On
failure stop before assigning passwords/admitting traffic. Never delete/reuse an
existing volume to retry. Do not automatically undo grants by restoring PUBLIC.

For existing-database adoption, approve per-object reverse ownership/ACL statements
from inventory and assess new objects created since cutover. DDL/data migration
rollback requires explicit migration reversibility and recovery analysis; prefer
restore to a new independently approved target if needed. Retain new backups and
all incident evidence securely. Git rollback alone cannot reverse database ACLs,
passwords, ownership or data/schema changes. No automatic rollback script is
provided because the original ownership and data are unknown.

## 12. Offline tests and results

Executed with synthetic inputs only:

- `python -m unittest scripts.test_c621_offline -v`: 10 passed. Covers strict
  credential identity/allowlist, ambient and libpq rejection, malformed secret
  inputs/value-free failures, real production settings import with mocked secret
  reads and dotenv forbidden, migration settings and web rejection, SQL/grant
  templates/defaults and production Compose/network/socket source contracts.
- `python scripts/test_c621_django.py`: 37 SimpleTestCases passed; no database
  creation or connection. Synthetic development settings, skip-dotenv; expected
  Django warning about overriding DATABASES in tests. Production checks and
  C6.1 middleware/socket contracts preserved.
- `python scripts/test_c61_probe.py`: ten synthetic procfs probe scenarios passed.
- `scripts/test-c6-1-compose-generation.ps1`: three PowerShell offline groups
  passed, plus its ten synthetic Python probe scenarios. Loads pure harness
  functions only, never executes the Docker harness body.
- `git diff --check`: passed at final review. Development compose and C6.1
  socket/proxy implementation files unchanged against baseline. No staged files.

Source checks do not parse/execute SQL or render Compose with Docker. Test imports
are configuration-only, not proof of PostgreSQL syntax, privileges or connectivity.
No claim is made about existing infrastructure. An initial synthetic import test
caught and corrected migration URL parsing before the final passing run.

## 13. Deferred disposable Docker validation — NOT RUN

This is a design for a separately approved harness, not an authorization to run it.
Use a new reviewed harness; do not run the C6.1 harness unchanged. No daemon,
container, image build, volume or database actions are permitted in this task.

1. Generate a cryptographically random run ID, project `cv-c621-<run-id>` and
   exact ownership label `com.codeventra.validation.run=<run-id>`. Generate only
   synthetic credentials into a protected temporary directory; no existing env
   files or infrastructure credentials. Pin reviewed images. Refuse external
   volumes/networks, explicit shared container names, fixed host bindings, existing
   volume names, host database endpoints, unexpected mounts or missing labels.
2. Render a self-contained manifest with fresh project-scoped PostgreSQL/socket/
   media volumes, internal data network and isolated proxy network. No source
   production/dev volumes, private uploads or host Docker socket. The DB has no
   published port. Require labels on all created containers/networks/volumes/images
   and check collisions before creation; stop on any pre-existing resource. Do
   not reuse a previous run's project or volumes.
3. Confirm all created resources carry both exact run label and expected Compose
   project label. Provision fresh DB with reviewed SQL, set synthetic passwords
   via protected credential channels and verify role flags, membership options,
   database/schema/object owners, PUBLIC ACLs and default ACLs using dedicated
   operator session. Do not persist hashes or password-bearing SQL in evidence.
4. Start an approved migration runner with only runtime/migration mounts. Check
   session_user=cv_migrate and current_user=cv_owner. Migrate the actual Django
   models; verify all application objects and django_migrations are owner-owned.
   Create a future table with identity/serial sequence using a new migration
   connection, then verify default grants (including type/function restrictions).
5. Authenticate as runtime: require SELECT/INSERT/UPDATE/DELETE success and
   sequence nextval/currval success. Require setval, CREATE TABLE/SCHEMA, TEMP,
   ALTER/DROP/TRUNCATE, CREATE ROLE, SET ROLE owner/migrate/init, role grants,
   replication and privilege escalation attempts to fail. Exercise owner-based
   ALTER/rename/index/data migration and reconnect; recheck grants afterward.
6. Authenticate as backup: require SELECT table/sequence and pg_dump success on
   complete scoped data; require DML, nextval/setval, DDL, SET ROLE and role grant
   denial, including after resetting default_transaction_read_only. Add an RLS
   negative fixture and require explicit backup failure rather than partial data
   acceptance. Restore a dump into another fresh isolated labeled target as
   owner, verify row counts, sequences and ACL/ownership recovery.
7. Start real application using runtime JSON; verify session_user/current_user
   cv_runtime through a protected synthetic probe and database-backed routes.
   Check web environment/mount metadata without dumping values; administrator,
   migration and backup secret paths must be absent/unreadable. Verify db/Redis
   cannot reach the C6.1 Unix mount; repeat C6.1 proxy spoofing/socket tests.
   Test invalid/shared secret inputs, migration settings web refusal, file
   permissions, credential rotation and Redis config/auth startup.
8. Record assertion names, exit codes, non-secret ownership/ACL metadata only;
   never raw settings, environment, database errors or secret contents. Cleanup
   enumerates exact run + Compose project labels and matches an in-memory owned
   resource inventory. Reject any mismatch. Remove only exact owned resources,
   never broad prune, down -v against another project or wildcard deletion. Check
   zero remaining owned resources; retain redacted evidence and cleanup failures.
   Treat failed cleanup as a stop requiring operator action, not permission to
   delete unrecognized resources.

## 14. Remaining production blockers

Actual PostgreSQL role/ACL/default/type/sequence/migration semantics, Compose
secret mounts/permissions, Redis startup, web startup, negative privilege tests,
backup completeness/restore and credential rotation are unvalidated. Existing
ownership/ACLs/roles/data were not inspected. SQL templates must receive DBA
review and PostgreSQL 17 disposable execution before adoption. Runtime DML includes
all public application tables (including Django metadata); a compromised runtime
can corrupt application data. Future sensitive table exceptions require reviewed
migrations/defaults. Fixed roles assume a dedicated application database/cluster
policy; other databases' PUBLIC CONNECT rights and pg_hba need separate review.

C6.1's existing domain/TLS, immutable image/dependency review, socket/upload volume
permissions, SMTP, database-backed route tests and unimplemented integration
scenarios still block production. Production approval requires disposable harness
approval, a separate existing-target inventory approval, reviewed backup/rollback
and ownership adoption plan, private secret custody/rotation approval, controlled
migration approval, and explicit deployment approval. Nothing here authorizes
access to existing infrastructure or claims production readiness.


## C6.2.1 security review remediation

Repository remediation only; none of these SQL templates were executed.

Existing routine reconciliation uses PostgreSQL 17 `ALL ROUTINES`, covering
functions and procedures. The approved routine EXECUTE allowlist is empty:
PUBLIC and all explicit non-owner grantees (including legacy roles) lose EXECUTE
and grant options. CASCADE removes dependent delegated grants. Existing callers,
SECURITY DEFINER entry points, extensions and migration RunSQL operations may
break; inventory signatures, prokind, owners, ACLs and dependencies before any
separately approved application. Custom exceptions require explicit reviewed,
signature-specific grants and matching regression coverage; there are none now.
Owner implicit authority and administrator authority cannot be removed by ACLs.

Type inventory now includes owner, ACL, type kind, element and relation linkage.
Reconciliation includes standalone composite types (`typtype=c`, `relkind=c`),
plus independent base/domain/enum/range/multirange types. Generated array types
and automatic table/view row types are inventoried but excluded from direct type
ACL changes: PostgreSQL does not support independently managing their ACLs like
standalone composites; relation access is governed by relation ACLs. Type USAGE
controls creating dependencies, not every use of already stored values. There is
no ALL TYPES IN SCHEMA shorthand. Every explicit non-owner type grantee is
revoked with CASCADE, then only runtime/backup USAGE is restored without grant
option. This includes removal of stale migration-role grants.

Owner routine defaults use ROUTINES (FUNCTIONS is equivalent in ALTER DEFAULT
PRIVILEGES and already included procedures). Global and schema defaults are both
cleared for known roles; unexpected routine/type default grantees abort the whole
transaction for inventory instead of surviving silently. Other schemas, creators,
role memberships and extension dependencies still need operator review. Django
migration connections must assume cv_owner before DDL, including reconnects;
cv_migrate NOINHERIT alone does not activate owner defaults. Existing migration
settings retain assume_role=cv_owner and web rejection of migration credentials.
Data migrations that call custom routines require a separately reviewed grant.

Before Django conversions, production accepts only ASCII decimal EMAIL_PORT
(1..65535), HSTS_SECONDS (0..2147483647), and ANALYTICS_RETENTION_DAYS
(1..2147483647). Existing defaults remain; the current C6.1 check still requires
HSTS disabled. Invalid errors name the setting and suppress exception chaining.
SMTP flags accept case-insensitive true/false or 1/0, with exactly one of TLS
(STARTTLS) or SSL (implicit TLS) enabled. Both transports remain valid; neither
plaintext nor conflicting modes are accepted. Port is validated independently
because provider secure ports vary. Existing SMTP credential checks remain.

Production REDIS_URL is required: redis://:PASSWORD@redis:6379/0 or
redis://default:PASSWORD@redis:6379/0, with percent-encoded credentials as needed,
no query/fragment or control characters. Errors omit URL/password. This is the
approved internal-network password-authentication contract, not Redis TLS.
Development parsing and unauthenticated local defaults remain unchanged. Redis
service configuration is unchanged and matching server authentication remains an
isolated-validation blocker; these checks do not establish server compatibility.
Administrator/runtime secret separation, internal networks and C6.1 Unix-socket
controls are unchanged.

References: [PostgreSQL 17 GRANT](https://www.postgresql.org/docs/17/sql-grant.html)
and [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html).
Offline source assertions do not prove executable SQL or effective ACL semantics.


Remediation offline verification (2026-10-29): C6.2.1 unittest suite 14/14;
Django config SimpleTestCases 37/37; C6.1 synthetic procfs probe 10/10;
PowerShell offline Compose generation/topology/diagnostics regressions passed.
Actual production settings imports reject eight synthetic invalid configurations,
including value-bearing markers and missing Redis, without displaying secrets.
Static checks cover routines, standalone versus relation composites, inventory,
defaults, validation ordering, network isolation and secret separation.
`git diff --check` passed. No SQL, migrations, Docker or live service tests ran.

## 13. Isolated C6.2.1 validation harness (prepared; execution unapproved)

Entry point: `scripts/validate-c6-2-1.ps1`. Supporting controller and synthetic
container probes are in `scripts/c621/`; offline fault-injection tests are in
`scripts/test_c621_harness_offline.py`. Preparation does not establish that the
SQL or container workflow passes. No Docker command, PostgreSQL connection,
migration, real environment file, private upload, or validation-results access
is authorized by the preparation task.

### Prerequisites and approval

Offline preflight requires Windows PowerShell 5.1+ (or PowerShell 7), Python 3.11+
on PATH, and the reviewed repository files including the existing C6.2.1
remediation. It parses the PowerShell wrapper and staged Python sources, checks
required files, rejects symlink escapes and validates an exact generated manifest.
It does not parse PostgreSQL grammar or query an engine, registry or daemon.

A future execution additionally requires **separate operator approval**, a local
Linux-container Docker engine with Compose v2 installed system-wide, sufficient
memory for 512 MiB PostgreSQL tmpfs plus Django, and two reviewed images already
present locally. Supply `postgres:17@sha256:<approved-64-hex-digest>` with the
standard official image postgres UID/GID 999:999 and a reviewed digest-pinned
Python 3.11+ image containing all `requirements.txt` dependencies (Django 5.2,
psycopg 3 and the application dependencies). The Python image must support
UID/GID 10001:10002 and contain no baked-in credentials or service configuration.
The harness never builds or pulls images. Image preparation/acquisition is a
separate reviewed activity. Docker contexts, user Docker configuration and ambient
Compose/libpq/application variables are ignored; only the local standard engine
socket/named pipe is selected. Remote contexts are unsupported.

The operator must review the manifest generator, SQL, migration code and exact
source hashes before execution. The run applies **all repository Django migrations**
only to its disposable database. Reviewed migrations and images are trusted code;
network/container isolation does not protect against a compromised host daemon.
The execution flag plus the exact, case-sensitive approval phrase constitute the
operator confirmation. Neither is implied by running preflight.

Offline commands (safe under the current authorization):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate-c6-2-1.ps1 -PreflightOnly
python -m unittest discover -s scripts -p test_c621_harness_offline.py -v
```

Future approved execution template (not executed during preparation):

```powershell
# Set these two variables to separately reviewed, locally present image references.
# $approvedPostgresImage = 'postgres:17@sha256:<approved-64-hex-digest>'
# $approvedPythonImage = '<approved-python-image>@sha256:<approved-64-hex-digest>'
.\scripts\validate-c6-2-1.ps1 -ExecuteIsolatedValidation `
  -OperatorConfirmation 'APPROVE DISPOSABLE C6.2.1 VALIDATION' `
  -PostgresImage $approvedPostgresImage -PythonImage $approvedPythonImage `
  -TimeoutSeconds 600
```

Omitting the execution flag defaults to preflight. Conflicting flags, missing
confirmation, unpinned images, wrong PostgreSQL major, unsafe manifests, source
escapes, resource name collisions or failed isolation verification stop the run.
`TimeoutSeconds` is bounded to 60–3600 seconds. Individual validation subprocesses
are capped at 60 seconds and the remaining validation deadline. Cleanup receives
a separate total 120-second grace period with at most 20 seconds per operation.
Read-only readiness and cleanup discovery repeat; each immutable-ID removal is attempted at most once. Other mutations never retry.

### Expected resources and credential boundaries

Each run receives a UUID-based `cv-c621-<32-hex>` Compose project name. It creates
exactly four containers (`-db`, `-web`, `-migrate`, `-audit`) and one `-net` internal
network. Every container/network carries `labs.codeventra.c621.run=<run-id>` and
Compose's project label. There are no published ports, external networks, named
volumes or persistent database storage. PostgreSQL data and secrets use tmpfs;
the manifest overrides the image's PGDATA volume with tmpfs. Unexpected persistent
volume mounts, host port bindings or network attachments fail verification.
No production/development Compose manifest is loaded or changed.

A new host temporary directory holds an explicit allowlist of application Python
sources/migrations, SQL fixtures, the generated JSON Compose manifest, empty
interpolation file and sanitized status. It does not mount the repository root,
uploads, validation-results, `.env`, the Docker socket or any existing data.
The three Python containers are UID/GID 10001:10002, have read-only roots, dropped
capabilities, no-new-privileges and a read-only mount of this curated source.
Web is a validation process, not the Gunicorn/Nginx deployment; existing C6.1
controls and the production manifests are left unchanged.

Independent random synthetic passwords are generated in controller memory.
Only stdin carries secrets into container-local tmpfs, never Docker argv, Compose
interpolation, host secret files or saved diagnostics. DB receives only its
administrator password; web receives only runtime JSON; migrate receives runtime
and migration JSON; the explicitly trusted audit runner receives all four database
identities to make authenticated positive and negative assertions. Audit is never
web. PostgreSQL statement/error-statement logging is suppressed for this synthetic
run. Raw process output, Docker errors, SQL exceptions, environments, settings,
connection URLs and container logs are never printed or retained.

Secret directories must be 0700 and files 0600 with intended container ownership;
probes check the actual Linux tmpfs mode and UID and reject unexpected secret files.
The bootstrap verifies administrator file mode/UID before releasing initialization.
These checks validate this harness's tmpfs custody, **not production bind-mounted
secret file permissions**; production secret-manager/mount validation remains a
separate acceptance requirement.

### Implemented live coverage (deferred)

* Fresh PostgreSQL 17 provisioning, repeated fresh-provision refusal, reviewed
  ACL reconciliation, role flags and exact membership options.
* Migration login DDL denial before SET ROLE, owner identity after SET ROLE,
  RESET ROLE denial and raw reconnect behavior.
* Existing and future table/sequence grants, runtime CRUD, restricted table
  privileges, schema/table/temp DDL denial, role creation/elevation/SET ROLE denial.
* Existing routine ACL reconciliation and future function/procedure EXECUTE denial;
  SECURITY DEFINER procedure execution only after an explicit reviewed grant,
  including execution while runtime lacks direct INSERT, and denial of internal
  transaction control by a SECURITY DEFINER procedure.
* Existing standalone composite ACL reconciliation, future composite USAGE grants,
  no PUBLIC type access and no stale migration type grant; effective defaults
  checked using newly created objects.
* Authenticated backup SELECT on tables and sequence state, denied nextval/setval,
  write/DDL/escalation/routine access even after disabling the read-only default.
* Deliberate SQL transaction error after CREATE TABLE followed by rollback absence
  assertion using a separate connection.
* Actual Django production/migration settings with synthetic files, all migrations
  as cv_migrate assuming cv_owner, reconnect role initialization, catalog ownership
  of schema/relations/types/routines, runtime ORM create/read/update/delete, and
  runtime migrate denial using an absent recorder table so DDL is genuinely tried.
* Web secret/env separation, expected secret file inventory/modes/owners, actual
  container network/port/volume isolation and label-guarded cleanup verification.

Redis is deliberately **not included**. The synthetic runtime JSON supplies a
parser-compatible authenticated REDIS_URL which is never connected. Live Redis
URL compatibility and unauthenticated rejection are not covered by this harness;
use a separately approved disposable Redis extension before Redis acceptance.
The existing offline settings tests cover URL validation only.

### Cleanup, diagnostics and limitations

Cleanup discovers resources using the exact UUID run label and Compose project
label. Each container/network must have one full 64-hex immutable Docker ID.
Inspection by that ID verifies both labels, then a second ID inspection rechecks
identity and ownership immediately before removal **by ID**, never by name.
Missing, changed, ambiguous or foreign identity fails closed. Name replacement
cannot redirect removal to the replacement's different ID. Volumes are never
removed; unexpected run-labelled volumes require operator review. No Compose down,
prune, broad removal or deletion of unrelated resources is used.

Creation state starts UNRESOLVED before invoking Compose and becomes COMPLETED
only after a successful CLI return. Python subprocess.run kills and waits for its
direct CLI process on timeout; this does not cancel daemon-side requests or prove
Compose descendants stopped. Any exception/nonzero result during creation leaves
creation unresolved, even if the current inventory is empty.

Cleanup performs at most six discovery/reconciliation rounds, one second apart,
within the total 120-second cleanup deadline (20 seconds per command maximum).
It discovers and removes later-appearing owned IDs, containers before networks,
and requires three consecutive empty inventories plus COMPLETED creation and no
inspection/removal errors for PASS. An unresolved creation always produces
`cleanup=INDETERMINATE`, nonzero exit and operator intervention, regardless of
empty polling results. Completed creation with cleanup errors produces
`FAIL_OPERATOR_ACTION_REQUIRED`. A failed removal is not retried.

Polling alone never proves the daemon cannot create resources later. Successful
Compose return is the supported completion boundary assumed here, not an offline
proof of Docker daemon quiescence. Docker does not offer atomic compare-labels-
and-delete through these CLI operations: a privileged actor could change network
labels between final inspection and deletion. Full-ID targeting avoids name reuse,
but absolute protection against hostile daemon/privileged concurrent mutation is
not claimed. These runtime semantics and Compose compatibility remain unverified.

For INDETERMINATE, retain the run ID, manifest, source hashes and sanitized status;
an operator must separately establish that the creator/descendants and daemon-side
creation requests have finished or been cancelled, then inventory exact run-owned
resources and approve ID-and-label-verified cleanup. Restoring daemon access and
observing empty inventories alone does not resolve uncertain creation. Do not
use global prune or remove resources belonging to another run.

The printed temporary `status.json` location contains only run/project identifiers,
phase, creation state, cleanup result, discovery round count, verified immutable IDs, error counts and source hashes. No raw exception or process output is saved. The curated source and generated
manifest are retained for review without generated credentials. Do not interpret
`validation=PASS` alone as success: `cleanup=PASS` and exit code zero are also
required. No diagnostic directory under validation-results is used.

Daemon loss, forced process termination, host failure or cancellation can prevent
finally cleanup. The operator must retain the printed run identity/status location,
restore engine access, review exact ownership labels/names and perform a separately
approved exact-resource cleanup. Never substitute a global prune or an existing
project's `down -v`. Credentials disappear with tmpfs/container destruction; a
failed cleanup can leave synthetic credentials in the owned live containers.
A killed process before the final status write can leave no status file; the
unique manifest in its temporary run directory still identifies the run.

Offline tests use a fake Docker adapter and synthetic sources. They establish
control flow and safety contracts, not actual Docker/Compose API compatibility,
SQL syntax/ACL semantics, SCRAM, Django migrations, Linux image UID behavior or
live secret custody. Those checks remain unrun pending approval. This harness
also does not validate HTTP/TLS/socket behavior, production HBA/TLS, RLS/backup
completeness/restore, existing-cluster adoption, or arbitrary malicious migrations.
It does not replace C6.1 regression validation or production acceptance.

Preparation verification (2026-10-29): PowerShell `-PreflightOnly` passed;
13 harness offline safety/fault-injection tests passed; 14 existing C6.2.1 offline
contracts passed; 37 Django SimpleTestCases passed without database setup; the
10 C6.1 synthetic socket probes and PowerShell Compose-generation/topology/
diagnostic regressions passed. `git diff --check` passed. `compose.yaml` matches
baseline `8e0f257`. No live Docker/PostgreSQL/Django migration/Redis validation ran.
Image-declared persistent volumes and unexpected PGDATA are rejected before
container creation. Source hashes describe the exact copied bytes; SQL execution
uses those same copied fixtures rather than rereading the working repository.


### Harness safety remediation resource budget (2026-10-29)

| Container | Memory | CPUs | PID limit | tmpfs bounds |
| --- | --- | --- | --- | --- |
| PostgreSQL | 1536 MiB | 2 | 256 | data 512 MiB; socket 16 MiB; secrets 1 MiB; /tmp 128 MiB |
| web, migrate, audit (each) | 768 MiB | 1 | 256 | secrets 1 MiB; /tmp 128 MiB |

These are Compose service mem_limit/cpus/pids_limit settings, independent of
Swarm deploy configuration. tmpfs consumes the container memory budget; the DB
budget leaves room for PostgreSQL buffers/processes beyond its disposable data.
Python budgets allow ordinary Django imports/migrations without deliberately
starving them. Aggregate configured memory is 3840 MiB; allow additional engine
and host headroom. Large migrations/datasets may exhaust these budgets; adjust
only after review rather than removing limits. Static assertions verify every
service and tmpfs bound; enforcement and workload sizing need separately approved
runtime validation. Internal networking and no published ports are unchanged.

Offline evidence establishes controller behavior under injected faults, not actual
engine semantics or production readiness. Probe code and PowerShell approval gates
were reviewed and require no changes for these three findings.

Remediation verification (2026-10-29): 20 harness offline tests, 14 C6.2.1
contract tests, 37 Django SimpleTestCases without database setup, 10 C6.1
synthetic procfs cases, and PowerShell C6.1 generation/topology/diagnostics checks
passed. PowerShell syntax/default offline preflight passed. Static limit/identity/
approval/isolation contracts passed; git diff --check passed. Development
compose.yaml remains identical to baseline 8e0f257. No live services were invoked.
