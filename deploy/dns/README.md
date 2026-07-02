# deploy/dns — DNS + email records for a hosted tenant

Record templates for bringing a tenant online (SAAS-3, ADR-F060). The zone must
be hosted at **Hetzner DNS** so the ACME **DNS-01** challenge token
(`HETZNER_DNS_API_TOKEN`) can create the `_acme-challenge` TXT records Caddy asks
for. Replace `example.com`, `staging`, the IPs, and the DKIM selector/key.

## A/AAAA — the app + status page

| Type | Name | Value | TTL | Purpose |
|---|---|---|---|---|
| A | `staging` | `<node-ipv4>` | 300 | The tenant stack (Caddy edge). |
| AAAA | `staging` | `<node-ipv6>` | 300 | IPv6 for the same. |
| A | `status` | `<status-host-ipv4>` | 300 | Uptime Kuma (separate host, `deploy/status/`). |
| AAAA | `status` | `<status-host-ipv6>` | 300 | IPv6 for the status host. |

For a **wildcard** prod tenant, add `A *.tenant` / `AAAA *.tenant` → the node, and
set `LQ_AI_PUBLIC_HOST=*.tenant.example.com`. DNS-01 issues the wildcard cert
regardless of a literal wildcard A record, but the app is only reachable at names
that actually resolve to the node.

## CAA — constrain who may issue (recommended)

| Type | Name | Value | Purpose |
|---|---|---|---|
| CAA | `@` | `0 issue "letsencrypt.org"` | Only Let's Encrypt may issue certs for this zone. |
| CAA | `@` | `0 issuewild "letsencrypt.org"` | Same for wildcard certs (DNS-01). |

## Email — SPF / DKIM / DMARC (deliverability of auth + notification mail)

The app's SMTP is optional (`smtp_host`-gated); when enabled, use a **dedicated
sending subdomain** (e.g. `mail.example.com`) via a fully-EU sender (Scaleway TEM
or Brevo) so auth/reset/verify mail is not marked spam. Provision alongside DNS
and run a deliverability smoke test in the bring-up proof (SAAS-HOSTING §5).

| Type | Name | Value (template) | Purpose |
|---|---|---|---|
| TXT | `mail` | `v=spf1 include:<provider-spf-host> -all` | SPF — only the provider may send as this subdomain. |
| TXT | `<selector>._domainkey.mail` | `v=DKIM1; k=rsa; p=<public-key>` | DKIM — provider-issued signing key (copy verbatim from the console). |
| TXT | `_dmarc.mail` | `v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com; adkim=s; aspf=s` | DMARC — policy + aggregate reports; start `p=quarantine`, tighten to `reject`. |

## Notes

- **No Cloudflare proxy** in front (orange cloud OFF / DNS-only if the zone ever
  lives at Cloudflare): its 120 s proxy-read-timeout silently kills SSE agent
  streams. Caddy is the only proxy (ADR-F060 D2).
- Keep TTLs low (300 s) during bring-up so a fix propagates fast; raise once stable.
