# F3 live proof — auth_state derived honestly (shipped code, real provider data)

Ran the ACTUAL shipped bridge path — `construct_type(MessageReceivedEvent, payload)` →
`event.message` → `normalize_message()` — against the real captured AgentMail payload
(`docs/fork/evidence/intake-probe/events-captured.jsonl` line 13, which carries a genuine
`Authentication-Results: amazonses.com; spf=pass … dkim=pass … dmarc=pass …`), plus two variants.
Script: `f3_auth_state_live_proof.py` (run in a throwaway `lq-ai-mail-bridge` container over the
branch source; `PYTHONPATH=/app`).

```
(1) REAL captured provider message      -> auth_state='pass'      AR~='amazonses.com; spf=pass ...'
(2) FORGED envelope-from=dmarc=pass      -> auth_state='fail'      (attacker token before real dmarc=fail — rejected)
(3) EMPTY headers (no AR on the wire)    -> auth_state='unknown'   (honest; NEVER a fabricated 'pass')
```

Before F3 all three returned a hardcoded `"pass"` (the false "Sender check passed" chip; the model's
unauthenticated-sender caution was dead code). After F3: the real DMARC verdict is used when present,
a forged `envelope-from`/`helo` token can no longer upgrade a genuine fail (method-boundary anchor),
and a header-less message is honestly `"unknown"`. The api/worker side (F1/F4/F7) is covered by the
full containerised api suite (`-m "not provider"`) which runs the real app against a real Postgres;
a full demo-stack email→UI screenshot was not run to avoid a 6.6 GB api rebuild on the constrained
dev box (no migration, comprehensive test coverage) — a quick follow-up if a demo screenshot is wanted.
