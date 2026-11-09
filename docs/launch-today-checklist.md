> Final execution sequence and current packaging updates: [deployment handoff](deployment-handoff.md).
> This supplements the earlier evidence below; no runtime success is claimed.

# Launch gates — 2026-10-31

Repository preparation is complete for this run. Public launch is BLOCKED.

- VERIFIED: 80 Django tests with synthetic settings, SQLite memory database,
  local cache and memory email; system check clean. No existing database used.
- VERIFIED: 14 C6.2.1 contracts, 20 mocked harness tests, 6 image contracts,
  10 C6.1 socket probe cases; three JavaScript syntax checks.
- IMPLEMENTED BUT UNVERIFIED: production resource limits, SMTP egress network,
  Unix socket deployment, role SQL, private persistent storage, TLS template.
- BLOCKED P0: reviewed exact dependency closure/hashes/Linux wheels and immutable
  app/proxy images; validation-image build and isolated PostgreSQL security proof.
- BLOCKED P0: domain ownership/DNS, VPS, TLS/renewal, secret provisioning, fresh DB,
  role grants, migration rehearsal, storage permissions, backup restore proof.
- BLOCKED P1: SMTP delivery, browser/mobile visual QA, live CSRF/rate limiting,
  static collection and proxy runtime checks. No real email sent here.
- NOT STARTED P2: measured live performance, search-console submission.

Before opening traffic, complete every P0 and public-functionality P1 gate in
[operator runbook](launch-operator-runbook.md). Keep indexing disabled until the
confirmed HTTPS site and approved public content pass smoke tests. HSTS stays zero
until HTTPS is stable; subdomains/preload stay disabled.

No Docker, deployment, DNS, real migrations or infrastructure actions are authorized
by this checklist. Do not reuse development volumes or credentials.
