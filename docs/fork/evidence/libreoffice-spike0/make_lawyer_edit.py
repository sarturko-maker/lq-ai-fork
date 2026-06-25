"""Spike 0 — a distinct-author 'lawyer' edit on top of the agent's redline.

Represents the lawyer editing in the editor: a NEW tracked change + comment by a
DIFFERENT author ("Jane Lawyer (Acme LLP)") added to fix1 (the agent's LQ.AI
redline). We then round-trip this through Collabora and confirm both authors
coexist + survive and the is_ours discriminator separates them.

Output: /work/fix5_lawyer_plus_agent.docx
"""

import io
import sys

sys.path.insert(0, "/repo/api")

from adeu import ModifyText, RedlineEngine  # noqa: E402

with open("/work/fix1_agent_redline.docx", "rb") as f:
    data = f.read()

eng = RedlineEngine(io.BytesIO(data), author="Jane Lawyer (Acme LLP)")
eng.apply_edits(
    [
        ModifyText(
            target_text="explore a potential business relationship",
            new_text="explore a potential strategic partnership",
            comment="Prefer 'strategic partnership' framing. -- JL",
        )
    ]
)
out = eng.save_to_stream()
b = out.getvalue() if hasattr(out, "getvalue") else bytes(out)
with open("/work/fix5_lawyer_plus_agent.docx", "wb") as f:
    f.write(b)
print(f"wrote /work/fix5_lawyer_plus_agent.docx ({len(b)} bytes)")
