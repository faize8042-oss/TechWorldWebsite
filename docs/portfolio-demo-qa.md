# Portfolio demonstration QA — 2 November 2026

Added four source-owned interactive tools to Projects, separate from existing
database-managed project records: StockPilot inventory planning, SlotDesk sample
appointments, ScopeQuote quotations, and ResolveDesk rule-based support triage.
Each includes the business problem, approach, working interaction and limits.
No client records, testimonials, deployments or business outcomes are invented.
Demo state is held in memory in the current browser page; no persistence, mail,
payment, customer record or real reservation is created.

Owner-confirmed location and public email added to the site: Lahore, Pakistan;
faize8042@gmail.com. SMTP credentials and destination configuration were unchanged.

## Executed verification

- 88 offline Django application tests passed, including three new demo route,
  catalog and missing-slug tests. System checks passed.
- JavaScript syntax check passed.
- Browser exercised all four tools against isolated source preview on loopback
  port 8091, using an in-memory SQLite DB, local cache and in-memory email.
- Inventory defaults: 4.4 days coverage, 50-unit reorder threshold, 87-unit order.
- Appointment: initial reservation accepted; duplicate date/time rejected.
- Quotation: PKR 25,000 subtotal, 10% discount, PKR 22,500 total. Additional item
  accumulated; reset cleared the session. HTML-looking service text remained
  literal text; no image element was inserted.
- Support: impact 3 × urgency 3 yielded P1; 1 × 1 yielded P4.
- All four demo pages checked at 390px width without horizontal overflow.
- Visual inspection covered desktop interaction and mobile page layout.

The preview was isolated from the existing Docker database and services. These
are scoped demonstration tools, not production inventory, booking, invoicing or
helpdesk systems. Multi-user concurrency, persistence, integrations and a full
authentication/authorization model are outside their implemented scope.
