# Hosting cost plan

**Price check date:** 2026-10-28. Provider rates, product availability, taxes, account eligibility, and checkout totals can change; these figures are planning data, not a quote or guarantee. All Hetzner amounts below are current official Germany/Finland USD list prices excluding VAT.

## Candidate comparison

| Candidate | Published specs | Server/month | Primary IPv4/month | Provider backup/month | Core subtotal before off-site backup, domain, email, tax |
| --- | --- | ---: | ---: | ---: | ---: |
| Hetzner CX23 | 2 shared vCPU, 4 GB RAM, 40 GB NVMe | $6.49 | $0.60 | ~$1.30 (20% of server) | **~$8.39** |
| Hetzner CX33 | 4 shared vCPU, 8 GB RAM, 80 GB NVMe | $9.99 | $0.60 | ~$2.00 (20% of server) | **~$12.59** |
| DigitalOcean shared 2 vCPU / 4 GB example | 2 shared vCPU, 4 GB RAM; disk size must be confirmed in the configured plan | $0.052/hour, about **$37.96 per 730-hour month** | Pricing page currently says $0/hour for v5 IPv4 as an introductory line item, subject to change | Weekly 20% (~$7.59 at this compute estimate) or daily 30%; alternatively usage-based from $0.01/GiB/month | **~$45.55 with weekly backup**, before disk details, external backup, domain, email, or tax |

The original candidates' capacities are confirmed on Hetzner's official plan page. The official price adjustment lists CX23 at **$6.49/month** and CX33 at **$9.99/month**, excluding IPv4 and VAT in Germany/Finland. Hetzner lists Primary IPv4 at **$0.60/month** and backups at 20% of server price, yielding the subtotals above. However, Hetzner's current cost-optimized page marked CX23 and CX33 unavailable during this check. Availability must be rechecked at checkout. Plan listings, FX/currency billing, and eligibility may vary by account/location.

Sources: [Hetzner plan page](https://www.hetzner.com/cloud/cost-optimized/), [official price adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/), [IPv4 prices](https://docs.hetzner.com/general/infrastructure-and-availability/ipv4-pricing/), [backup and billing rules](https://docs.hetzner.com/cloud/billing/faq/), [DigitalOcean Droplet pricing](https://www.digitalocean.com/pricing/droplets). Sources checked 2026-10-28.

DigitalOcean's current official page shows a shared 2 vCPU/4 GB configuration at $0.052/hour. At an illustrative 730 hours, that is $37.96/month; applying the listed 20% weekly backup rate gives about $45.55/month. The page currently lists v5 public IPv4 at $0/hour as an introductory line item subject to change. The source check did not establish a matching disk size or a stable invoice price, so the total is a comparison estimate rather than a quote. Even before independent backup, domain, email, and tax it is above the budget. Its convenience, service options, and regions may still matter if the budget changes.

## Budget assessment

The CX33 base server, IPv4, and provider backup subtotal is about **$12.59/month before VAT/tax**. That leaves roughly $7.41 of a $20 cap for independent encrypted backup storage, domain amortization/renewal, email, and tax. Those extra costs have not been confirmed. Therefore, **the complete monthly total cannot yet be certified within $10–20**. A CX23 subtotal is about $8.39 before tax and leaves more room, but 4 GB RAM and 40 GB disk give less operational headroom and it is currently marked unavailable.

Recommended starting target: **CX33 if available and the checkout plus external-backup/domain/email total fits the approved cap**. The 8 GB memory and 80 GB disk give safer headroom for Django, PostgreSQL, Redis, Nginx, the OS, and temporary backup/build activity on one host. If the $20 ceiling is strict and independent backup storage makes CX33 exceed it, reconsider the plan with the actual values; do not omit off-server backups simply to claim budget compliance. CX23 is the fallback only if memory, disk, and recovery headroom are accepted. A local latency test from the intended audience should decide Germany versus Finland; do not infer regional latency from geography alone.

| Cost line | Planning status |
| --- | --- |
| VPS + IPv4 + provider backup | Official Hetzner list rates calculated above; verify current availability and checkout. |
| Independent off-server encrypted backup storage | Provider and cost not selected; obtain current quote, estimate by compressed database plus upload growth and retention. |
| Domain registration/renewal | Not verified; domain registration itself is not confirmed. Confirm registrar and renewal/tax total. |
| Email | Existing local SMTP configuration must not be assumed suitable. Confirm provider, sending limits, and monthly cost; a mailbox/email service may be free, paid, or bundled depending on provider. |
| VAT/taxes | Hetzner prices cited exclude VAT. Applicable tax depends on customer billing details and must be confirmed in checkout. |
| Extra storage/traffic | Current plan includes at least 20 TB EU egress per official Hetzner page; verify current allowance and overage terms. External storage/volume rates are not included. |
| Optional monitoring | No service selected or costed. Begin with host/container metrics and bounded logs, then price external alerting if needed. |

Provider snapshots/backups and independent off-server logical/file backups are separate protections. Provider backups do not replace an independently accessible backup copy. Domain, email, storage, taxes, and optional monitoring may push the total over the stated budget. No prices are invented for unverified categories.

## Capacity and scaling

For a low-traffic software-agency portfolio, shared CPU should be a reasonable initial candidate, subject to real load and memory measurements. Docker, PostgreSQL, Django workers, Redis, Nginx, OS page cache, and backup/build operations all compete for memory. The 4 GB CX23 has limited headroom; 8 GB CX33 is more comfortable. Disk must hold the OS, images and old releases, database, private/public uploads, logs, and temporary restore/build space; leave an alerting reserve and do not fill the filesystem with local backups.

Scaling path: measure first; resize the VPS while preserving backups; move PostgreSQL to a managed database or dedicated host when resource isolation/recovery warrants the cost; move media/private files to a suitably access-controlled object store; add a second stateless web host and load balancer if availability/traffic demands it. These steps introduce added costs and complexity and are not part of this phase.
