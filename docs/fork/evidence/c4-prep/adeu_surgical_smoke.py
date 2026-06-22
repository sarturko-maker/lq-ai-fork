"""C2-prep / C4-review smoke: prove adeu==1.12.1 produces SURGICAL sub-sentence
tracked changes (only changed words wrapped in <w:ins>/<w:del>, unchanged words bare).

Reads the emitted word/document.xml and reconstructs each paragraph with the
tracked-change boundaries made visible: bare text = untouched run, [+...+] = w:ins,
[-...-] = w:del. A surgical redline keeps the sentence's unchanged head/tail BARE.
"""
import io
import zipfile

import adeu
from docx import Document
from lxml import etree
from adeu import ModifyText, RedlineEngine

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

print("adeu version:", getattr(adeu, "version", getattr(adeu, "__version__", "?")))


def make_docx(paragraphs):
    d = Document()
    for p in paragraphs:
        d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    buf.seek(0)
    return buf


def output_bytes(engine):
    for attr in ("get_document_bytes", "to_bytes", "get_bytes", "save_to_bytes", "export"):
        if hasattr(engine, attr):
            try:
                b = getattr(engine, attr)()
                if isinstance(b, (bytes, bytearray)):
                    return bytes(b)
                if isinstance(b, io.BytesIO):
                    return b.getvalue()
                if hasattr(b, "read"):
                    return b.read()
            except Exception as e:  # noqa: BLE001
                print(f"  ({attr} -> {e})")
    for docattr in ("doc", "document", "_doc"):
        doc = getattr(engine, docattr, None)
        if doc is not None and hasattr(doc, "save"):
            b = io.BytesIO()
            doc.save(b)
            return b.getvalue()
    raise RuntimeError("no output method; attrs=" + str([a for a in dir(engine) if not a.startswith("__")]))


def _text(run, tag):
    return "".join((t.text or "") for t in run.iter(W + tag))


def reconstruct(docx_bytes):
    xml = zipfile.ZipFile(io.BytesIO(docx_bytes)).read("word/document.xml")
    root = etree.fromstring(xml)
    out = []
    for p in root.iter(W + "p"):
        seg = []
        for child in p:
            ln = etree.QName(child).localname
            if ln == "r":
                seg.append(_text(child, "t"))
            elif ln == "ins":
                ins = "".join(_text(r, "t") for r in child.findall(W + "r"))
                seg.append(f"[+{ins}+]")
            elif ln == "del":
                d = "".join(_text(r, "delText") for r in child.findall(W + "r"))
                seg.append(f"[-{d}-]")
        line = "".join(seg)
        if line.strip():
            out.append(line)
    return out


def run_case(name, paragraphs, changes):
    print("\n" + "=" * 88)
    print(name)
    print("=" * 88)
    buf = make_docx(paragraphs)
    eng = RedlineEngine(buf, author="LQ.AI Commercial")
    res = eng.process_batch(changes, dry_run=False)
    if isinstance(res, dict):
        print("process_batch:", {k: res[k] for k in res if k in ("actions_applied", "actions_skipped", "edits_applied", "edits_skipped")})
    for line in reconstruct(output_bytes(eng)):
        print("  " + line)


CAP = ("The Vendor's aggregate liability arising out of or in connection with this Agreement "
       "shall not exceed the total fees paid by the Customer in the three (3) months preceding the claim.")

# Case 1 — ONE contiguous change, proposed as a WHOLE-SENTENCE ModifyText.
# Surgical expectation: head + tail stay BARE; only the middle is del/ins.
run_case(
    "CASE 1 — single contiguous change via one whole-sentence ModifyText (expect surgical)",
    [CAP],
    [ModifyText(
        target_text=CAP,
        new_text=CAP.replace(
            "the total fees paid by the Customer in the three (3) months preceding the claim",
            "the greater of the total fees paid by the Customer in the twelve (12) months preceding the claim or two times the annual fees",
        ),
        comment="Cap below 12-mo house floor: extend lookback + add 2x annual super-cap. Escalate to GC.",
    )],
)

# Case 2 — TWO separate changes in one sentence, proposed as TWO NARROW ModifyText edits.
# Surgical expectation: two small marks, the unchanged middle stays BARE.
run_case(
    "CASE 2 — two separate changes via two NARROW ModifyText edits (expect two surgical marks)",
    [CAP],
    [
        ModifyText(target_text="three (3) months", new_text="twelve (12) months",
                   comment="Below house floor (12-mo)."),
        ModifyText(target_text="preceding the claim.",
                   new_text="preceding the claim, save that liability for breach of confidentiality, data protection obligations or infringement of intellectual property rights shall be unlimited.",
                   comment="Carve out data/IP/confidentiality from the cap (deemed direct losses)."),
    ],
)

# Case 3 — the CAUTION: two separate changes via ONE whole-sentence ModifyText.
# Expectation: prefix/suffix trim leaves only ONE contiguous changed span, so the
# unchanged words BETWEEN the two edits get swept into the del/ins. Demonstrates why
# the agent must propose narrow edits (and why the surgical GATE matters).
run_case(
    "CASE 3 — two separate changes via ONE whole-sentence ModifyText (expect over-marking)",
    [CAP],
    [ModifyText(
        target_text=CAP,
        new_text=CAP.replace("three (3) months", "twelve (12) months").replace(
            "preceding the claim.",
            "preceding the claim, save that data-protection liability shall be unlimited.",
        ),
        comment="Whole-sentence rewrite (anti-pattern).",
    )],
)
print("\nSMOKE DONE")
