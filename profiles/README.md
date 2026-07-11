# Shipped agent profiles (ADR-F067 D4, B-7a)

Each `<name>/profile.yaml` is a declarative, shipped bundle — practice-area
config, module bindings, sub-agent roster, and HITL defaults — loaded read-only
at API boot by `app/profiles/`. Doctrine lives in the sibling `doctrine.md`,
read verbatim (byte-parity with the seeded `practice_areas.profile_md`).

An admin materialises a profile onto a real practice area via
`POST /api/v1/profiles/{name}/apply` (create/patch the area + adopt the Library
entries + write bindings + set the roster) — copy-not-link; the admin owns the
rows afterward. The guided wizard over this endpoint is B-7b.
