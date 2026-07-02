# Security Policy

This is the security policy for **LQ.AI Oscar Edition**
([sarturko-maker/lq-ai-fork](https://github.com/sarturko-maker/lq-ai-fork)), a hard fork of
[LegalQuants/lq-ai](https://github.com/LegalQuants/lq-ai) (see `docs/adr/F001-fork-charter.md`).
This policy covers the fork only — it does not speak for upstream, and upstream's advisories are
not a substitute for reporting against this repo (see Scope below).

## Reporting a vulnerability

**Do not file security vulnerabilities as public GitHub issues.** Public reports give attackers a head start; coordinated disclosure protects users while we develop a fix.

To report a vulnerability:

- **GitHub Security Advisory:** report privately through this repo's [Security Advisories](https://github.com/sarturko-maker/lq-ai-fork/security/advisories/new) feature (encrypted in transit and at rest within GitHub's infrastructure). This is currently the **only** reporting channel.
- **Email:** not yet available. A dedicated security-contact email (with a published GPG key) will be stood up before the first hosted tenant goes live (SAAS milestone, ADR-F058); this policy will be updated when it exists. Until then, use the GitHub Security Advisory link above.

Please include:

- A description of the vulnerability and its potential impact.
- Reproduction steps or proof-of-concept code.
- The version(s) and configurations affected.
- Any suggested fix or mitigation, if you have one.
- Your contact information for follow-up (or note if you prefer anonymity).

## Response commitments

We commit to:

- **Acknowledge receipt within 72 hours** of the initial report.
- Provide an **initial assessment within 7 business days** including our preliminary view on severity and timeline.
- Address **critical vulnerabilities within 30 days** of confirmation, **high-severity within 60 days**, **medium-severity within 90 days** of confirmation.
- Coordinate public disclosure timing with the reporter.
- Credit the reporter in the published advisory unless anonymity is preferred.

For vulnerabilities being actively exploited in the wild, we accelerate; please flag this in your initial report.

## Coordinated disclosure

The project follows coordinated disclosure: we ask reporters to give us reasonable time to develop and ship a fix before public disclosure. We will work with you to set a disclosure date that balances user safety with researcher interests.

Because this is a public repository whose `main` branch is deployed continuously (SAAS-1's push-to-main image pipeline), a merged fix is effectively a public disclosure the moment it lands: `main` is also the attacker's changelog. Where practical, we patch, deploy the hosted fleet, and push the fix in the same window rather than merging a fix days ahead of deploying it.

After a fix ships, we publish:

- A **GitHub Security Advisory** describing the vulnerability, affected versions, and remediation.
- A **CVE** (where applicable) coordinated through MITRE.
- **Reporter credit** in the advisory acknowledgments section.

## Scope

**In scope** for security disclosures:

- The LQ.AI Oscar Edition codebase: `api/`, `gateway/`, `web/`, `scripts/`.
- Official deployment artifacts: `docker-compose.yml` (self-host), `docker-compose.prod.yml` (hosted, ADR-F058 Mode 2), and the container images we publish (`ghcr.io/sarturko-maker/lq-ai-{api,gateway,web}`).
- Cryptographic implementations and key handling.
- Authentication, authorization, session management, and audit logging.
- The Inference Gateway's Tier Derivation, Anonymization Layer, and provider-routing logic.
- Documentation that could mislead operators about security posture.
- Vulnerabilities affecting the operator-hosted SaaS deployments of this project (ADR-F058 Mode 2) follow this same channel — see the note below.

**Out of scope** (please report elsewhere):

- Vulnerabilities in third-party LLM providers (Anthropic, OpenAI, Vertex, etc.) — report directly to the provider.
- Vulnerabilities in dependencies — report upstream; we'll respond to advisories that affect us (also tracked via `.github/dependabot.yml`).
- **Operator-modified deployments**: configurations, forks, or code changes made by a self-hosting operator that diverge from this repo's shipped defaults are the operator's responsibility, not ours.
- Social engineering attacks against maintainers or community members.
- Theoretical attacks without a demonstrable exploit path against the project's threat model.

## What we will not do

- We will not pursue legal action against good-faith security researchers who follow this policy.
- We will not retaliate against reporters or ban them from the community.
- We will not require non-disclosure agreements or other restrictive agreements as a condition of accepting reports.

## Safe harbor

If you make a good-faith effort to comply with this policy during your security research, we will consider your activities authorized and we will not pursue civil or criminal action against you. We will work with you to understand and resolve issues quickly.

This safe-harbor commitment does not authorize:

- Activities that compromise the privacy or safety of users beyond what is necessary to demonstrate the vulnerability.
- Activities that disrupt or degrade the availability of services or other users' deployments.
- Accessing data beyond what is needed to demonstrate the vulnerability.
- Public disclosure before the coordinated disclosure timeline agreed upon with the maintainer.
- Targeting infrastructure or accounts belonging to a specific operator-hosted tenant of this project (a customer's dedicated stack); this policy covers the open-source project and the maintainer's own hosted infrastructure — a tenant's operator may have separate disclosure terms.

## Past advisories

Past security advisories and reporter acknowledgments are listed at:
[GitHub Security Advisories page — URL becomes active when first advisory is published](https://github.com/sarturko-maker/lq-ai-fork/security/advisories).

## Questions about this policy

For questions about this policy (rather than vulnerability reports), GitHub Discussions in the `Help` category is appropriate. For sensitive policy questions, use the GitHub Security Advisory channel above until a dedicated email exists.

---

*This policy is adapted in part from the [disclose.io](https://disclose.io) Core Terms project. Updates to this policy follow the project's standard documentation cadence; substantive changes will be announced in advance through GitHub Discussions.*
