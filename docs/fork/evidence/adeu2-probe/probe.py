"""Empirical probe of adeu==2.4.0 native redlining vs LQ.AI's pinned word-diff shim.

A   native, ONE commented ModifyText, changes at both ends       -> atomic block?
B   native, same edit uncommented                                -> surgical fan-out?
C   LQ.AI shim (pinned raw offsets) on pristine doc              -> regression check
D   living redline round 2, native insert near round-1 regions   -> resolves? comment survives?
D2  round-2 target = round-1 DELETED text                        -> refusal + message
D3  LQ.AI shim on round-2 doc                                    -> raw-view duplication kills uniqueness?
E   LQ.AI shim pinned offsets on round-2 doc (AP-05)             -> mis-anchor?
H1  comment-only edit (target==new) on pristine                  -> comment, no tracked change?
H2  TWO-PASS RECIPE: uncommented surgical apply, then comment-only over updated clause
H4  recipe on the round-2 doc at the exact spot where D dropped its comment
F   validate_edits contract
G   settings.xml trackChanges
"""

import io
import sys
import zipfile
import structlog

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(30))  # WARNING+

from lxml import etree
from adeu import RedlineEngine, ModifyText
from adeu.diff import generate_edits_from_text
from adeu.redline.mapper import DocumentMapper
from adeu.redline.engine import BatchValidationError

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def regions(docx_bytes):
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    out = []
    for el in root.iter():
        tag = etree.QName(el).localname
        if tag == "ins":
            out.append(("ins", "".join(t.text or "" for t in el.iter(f"{{{W}}}t"))))
        elif tag == "del":
            out.append(("del", "".join(t.text or "" for t in el.iter(f"{{{W}}}delText"))))
    return out


def comments(docx_bytes):
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        for name in ("word/comments1.xml", "word/comments.xml"):
            if name in z.namelist():
                root = etree.fromstring(z.read(name))
                return [
                    "".join(t.text or "" for t in c.iter(f"{{{W}}}t"))[:50]
                    for c in root.findall(f"{{{W}}}comment")
                ]
    return []


def show(label, docx_bytes):
    rs, cs = regions(docx_bytes), comments(docx_bytes)
    print(f"  [{label}] regions={len(rs)} comments={len(cs)} {cs}")
    for i, (k, t) in enumerate(rs):
        t = t if len(t) <= 70 else t[:67] + "..."
        print(f"    {i:2d} {k:3s} |{t}|")


def save(engine):
    buf = engine.save_to_stream()
    return buf.getvalue() if hasattr(buf, "getvalue") else bytes(buf)


def raw_text(engine):
    full = engine.mapper.full_text
    if not full:
        engine.mapper._build_map()
        full = engine.mapper.full_text
    return full


def clean_text_of(docx_bytes):
    e = RedlineEngine(io.BytesIO(docx_bytes), author="viewer")
    return DocumentMapper(e.doc, clean_view=True).full_text


def pick_sentence(full, min_words=14):
    for raw in full.split(". "):
        s = raw.strip()
        if len(s.split()) >= min_words and "|" not in s and "\n" not in s and full.count(s) == 1:
            return s
    raise SystemExit("no suitable sentence")


def unique_span_after(full, offset, length=60):
    """A unique word-aligned span from a paragraph after `offset`."""
    for para in full[offset:].split("\n"):
        p = para.strip()
        if len(p) >= length and "|" not in p:
            span = p[:length].rsplit(" ", 1)[0]
            if full.count(span) == 1:
                return span
    raise SystemExit("no unique span found")


def shim_edits(engine, target, new, comment):
    full = raw_text(engine)
    n = full.count(target)
    if n != 1:
        raise AssertionError(f"shim uniqueness precondition failed: {n} raw-view matches")
    subs = generate_edits_from_text(full, full.replace(target, new))
    for i, sub in enumerate(subs):
        sub._resolved_start_idx = sub._match_start_index
        sub.comment = comment if i == 0 else None
    return subs


pristine = open(sys.argv[1], "rb").read()
e0 = RedlineEngine(io.BytesIO(pristine), author="LQ.AI probe")
S = pick_sentence(raw_text(e0))
w = S.split()
w[2], w[-3] = "ALPHAWORD", "OMEGAWORD"
S2 = " ".join(w)
print(f"target ({len(S.split())}w): |{S[:80]}...|")

print("\n=== A: native, commented ===")
eA = RedlineEngine(io.BytesIO(pristine), author="LQ.AI probe")
a, sk = eA.apply_edits([ModifyText(target_text=S, new_text=S2, comment="probe A rationale")])
print(f"  applied={a} skipped={sk}")
bytesA = save(eA)
show("A", bytesA)

print("\n=== B: native, uncommented ===")
eB = RedlineEngine(io.BytesIO(pristine), author="LQ.AI probe")
a, sk = eB.apply_edits([ModifyText(target_text=S, new_text=S2)])
print(f"  applied={a} skipped={sk}")
show("B", save(eB))

print("\n=== C: shim, pristine ===")
eC = RedlineEngine(io.BytesIO(pristine), author="LQ.AI probe")
subs = shim_edits(eC, S, S2, "probe C rationale")
a, sk = eC.apply_edits(subs)
print(f"  shim subs={len(subs)} applied={a} skipped={sk}")
show("C", save(eC))

print("\n=== D: round 2, native insert (target spans round-1 insertion) ===")
eD = RedlineEngine(io.BytesIO(bytesA), author="LQ.AI probe")
clean = DocumentMapper(eD.doc, clean_view=True).full_text
i = clean.find("ALPHAWORD")
tgt = clean[i : i + 60].rsplit(" ", 1)[0]
print(f"  comments before: {len(comments(bytesA))}")
a, sk = eD.apply_edits([ModifyText(target_text=tgt, new_text=tgt + " XRAYWORD", comment="probe D comment")])
bytesD = save(eD)
print(f"  applied={a} skipped={sk}  comments after: {len(comments(bytesD))}  <-- comment drop if unchanged")

print("\n=== D2: round 2, target = deleted text ===")
eD2 = RedlineEngine(io.BytesIO(bytesA), author="LQ.AI probe")
rawD2 = raw_text(eD2)
j = rawD2.find(S.split()[2])  # original word replaced in round 1
tgt2 = rawD2[j : j + 50].rsplit(" ", 1)[0]
a, sk = eD2.apply_edits([ModifyText(target_text=tgt2, new_text="SHOULD-NOT-LAND")])
print(f"  applied={a} skipped={sk} detail={eD2.skipped_details[:1]}")

print("\n=== D3: shim on round-2 doc (raw-view duplication) ===")
eD3 = RedlineEngine(io.BytesIO(bytesA), author="LQ.AI probe")
try:
    shim_edits(eD3, tgt, tgt + " YANKEEWORD", "probe D3")
    print("  uniqueness held (unexpected)")
except AssertionError as ex:
    print(f"  {ex}  <-- shim falls back to wholesale on round-2 docs")

print("\n=== E: shim pinned raw offsets on round-2 doc (AP-05) ===")
eE = RedlineEngine(io.BytesIO(bytesA), author="LQ.AI probe")
rawE = raw_text(eE)
cleanE = DocumentMapper(eE.doc, clean_view=True).full_text
edit_end = rawE.find("OMEGAWORD") + len("OMEGAWORD")
T3 = unique_span_after(rawE, edit_end)
d_raw, d_clean = rawE.find(T3), cleanE.find(T3)
print(f"  T3=|{T3[:50]}...| raw_off={d_raw} clean_off={d_clean} delta={d_raw - d_clean}")
subs = shim_edits(eE, T3, "PINPROBE " + T3, "probe E")
a, sk = eE.apply_edits(subs)
cleanAfter = clean_text_of(save(eE))
k = cleanAfter.find("PINPROBE")
if k >= 0:
    landed_next = cleanAfter[k + len("PINPROBE ") : k + len("PINPROBE ") + 25]
    print(f"  applied={a} skipped={sk}; PINPROBE precedes |{landed_next}|; intended |{T3[:25]}|")
    print(f"  MIS-ANCHORED: {landed_next != T3[:25]}")
else:
    print(f"  applied={a} skipped={sk}; PINPROBE not found in clean view (dropped or mangled)")

print("\n=== H1: comment-only edit (target==new), pristine ===")
eH1 = RedlineEngine(io.BytesIO(pristine), author="LQ.AI probe")
a, sk = eH1.apply_edits([ModifyText(target_text=S, new_text=S, comment="probe H1 comment-only")])
bytesH1 = save(eH1)
print(f"  applied={a} skipped={sk} regions={len(regions(bytesH1))} comments={comments(bytesH1)}")

print("\n=== H2: TWO-PASS RECIPE, pristine (uncommented apply, then comment-only) ===")
eH2 = RedlineEngine(io.BytesIO(pristine), author="LQ.AI probe")
a1, s1 = eH2.apply_edits([ModifyText(target_text=S, new_text=S2)])
a2, s2 = eH2.apply_edits([ModifyText(target_text=S2, new_text=S2, comment="probe H2 rationale")])
print(f"  pass1 applied={a1} skipped={s1}; pass2 applied={a2} skipped={s2} details={eH2.skipped_details[:2]}")
show("H2", save(eH2))

print("\n=== H4: RECIPE on round-2 doc at the D spot (where the comment dropped) ===")
eH4 = RedlineEngine(io.BytesIO(bytesA), author="LQ.AI probe")
a1, s1 = eH4.apply_edits([ModifyText(target_text=tgt, new_text=tgt + " XRAYWORD")])
tgt_new = tgt + " XRAYWORD"
a2, s2 = eH4.apply_edits([ModifyText(target_text=tgt_new, new_text=tgt_new, comment="probe H4 rationale")])
bytesH4 = save(eH4)
print(f"  pass1 applied={a1} skipped={s1}; pass2 applied={a2} skipped={s2} details={eH4.skipped_details[:2]}")
print(f"  comments: {len(comments(bytesA))} -> {len(comments(bytesH4))} {comments(bytesH4)}")

print("\n=== F: validate_edits ===")
eF = RedlineEngine(io.BytesIO(pristine), author="LQ.AI probe")
try:
    r = eF.validate_edits([ModifyText(target_text=S, new_text=S2), ModifyText(target_text="ZZZ NOT PRESENT QQQ", new_text="x")])
    print(f"  returned {type(r).__name__} len={len(r)}: {[x[:110] for x in r]}")
except BatchValidationError as ex:
    print(f"  RAISED; failed={ex.failed} errors={[x[:110] for x in ex.errors][:3]}")
print(f"  _mutated_since_load={eF._mutated_since_load}")

print("\n=== G: settings.xml ===")
with zipfile.ZipFile(io.BytesIO(bytesA)) as z:
    st = z.read("word/settings.xml").decode("utf-8", "replace") if "word/settings.xml" in z.namelist() else ""
print(f"  w:trackChanges present after native apply: {'trackChanges' in st}")

print("\nprobe done")
