"""Matter-level substrate shared by the cockpit and the intake flow.

INTAKE-4a (ADR-F088). Two modules, both deliberately small and free of any
product naming (maintainer ruling 2026-08-30 — nothing user-visible, in a
header, a subject line or a reference number carries our product name):

* :mod:`app.matters.reference` — the neutral ``ORG-AREA-NNNN`` matter
  reference: derivation of the short codes, the counter-backed allocator,
  and the strict parse/format helpers.
* :mod:`app.matters.stamping` — the pure email-stamping helpers the outbound
  leg (INTAKE-4b) writes and the inbound resolver reads: the idempotent
  subject tag, the ``References``/``In-Reply-To`` parsers, and plus-address
  tag parsing. We mint no ``Message-ID`` of our own — the provider assigns its
  own on send, so the machine-readable stamp is that provider-assigned id,
  persisted on ``intake_messages.provider_message_id``.
"""

from __future__ import annotations
