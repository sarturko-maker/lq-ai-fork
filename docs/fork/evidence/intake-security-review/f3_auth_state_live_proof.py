"""Live proof of F3: run the SHIPPED bridge path (construct_type -> normalize_message)
against the REAL captured provider payload, a forgery variant, and an empty-headers one."""
import copy, json
from agentmail import MessageReceivedEvent
from agentmail.core.unchecked_base_model import construct_type
from app.normalize import normalize_message

lines = [l for l in open("/probe/events-captured.jsonl") if l.strip()]
real = json.loads(lines[12])            # {at, py_type, payload}
payload = real["payload"]

def auth_state(pl):
    event = construct_type(type_=MessageReceivedEvent, object_=pl)
    msg = getattr(event, "message", None)
    env = normalize_message(msg, inbox_id="oscar-lq")
    return env["message"]["auth_state"], env["message"]["headers"].get("Authentication-Results", "")[:60]

# (1) real captured message (genuine dmarc=pass on the wire)
s, ar = auth_state(payload)
print(f"(1) REAL captured provider message      -> auth_state={s!r}   AR~={ar!r}")

# (2) forgery: attacker sets envelope-from local-part to 'dmarc=pass', real verdict is fail
forged = copy.deepcopy(payload)
hdrs = forged["message"]["headers"]
# find the AR key case-insensitively
ark = next(k for k in hdrs if k.lower() == "authentication-results")
hdrs[ark] = ("amazonses.com; spf=fail (no) client-ip=1.2.3.4; "
             "envelope-from=dmarc=pass@evil.com; helo=mail.evil.com; "
             "dmarc=fail header.from=victim.com;")
s, ar = auth_state(forged)
print(f"(2) FORGED envelope-from=dmarc=pass      -> auth_state={s!r}   (must be 'fail')")

# (3) empty headers (the first-probe shape) -> honest unknown, never a fake pass
empty = copy.deepcopy(payload)
empty["message"]["headers"] = {}
s, _ = auth_state(empty)
print(f"(3) EMPTY headers (no AR on the wire)    -> auth_state={s!r}   (must be 'unknown', never 'pass')")
