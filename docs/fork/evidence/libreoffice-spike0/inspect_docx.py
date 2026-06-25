"""Spike 0 inspector — re-read a .docx two ways and report fidelity signals.

  1. Adeu semantic re-read (extract_text_from_stream, clean_view=False) — proves the
     fork's own parser can read it, and surfaces the per-change AUTHOR strings.
  2. Raw OOXML — counts w:ins / w:del, detects NESTED <w:ins><w:del> (the
     VibeLegalStudio multi-pass corruption), lists w:author byte-strings, and counts
     comments + their authors.

Usage: python inspect_docx.py <file.docx> [<file.docx> ...]
Exit code is non-zero if Adeu fails to parse any file OR nesting is detected.
"""

import io
import re
import sys
import zipfile

sys.path.insert(0, "/repo/api")

from adeu import extract_text_from_stream  # noqa: E402
from lxml import etree  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
AGENT_AUTHOR = "LQ.AI Commercial counsel"

problems = 0


def analyze(path: str) -> None:
    global problems
    print("=" * 72)
    print("FILE:", path)
    with open(path, "rb") as f:
        data = f.read()

    # --- 1. Adeu semantic re-read (the fork's own parser) ---
    try:
        cm = extract_text_from_stream(io.BytesIO(data), clean_view=False)
        chg_authors = sorted(
            {a.strip() for a in re.findall(r"\[Chg:\d+\s+\w+\]\s*([^\n\r<]+)", cm)}
        )
        n_chg = len(set(re.findall(r"\[Chg:(\d+)", cm)))
        n_com = len(re.findall(r"\[Com:\d+", cm))
        print("  [Adeu] re-read OK")
        print(f"  [Adeu] distinct Chg ids={n_chg}  Com refs={n_com}")
        print(f"  [Adeu] change authors: {chg_authors}")
        is_ours = AGENT_AUTHOR in chg_authors
        if any("LQ.AI" in a for a in chg_authors):
            print(f"  [Adeu] is_ours discriminator intact (exact match: {is_ours})")
    except Exception as e:  # noqa: BLE001
        print(f"  [Adeu] re-read FAILED: {e!r}")
        problems += 1

    # --- 2. Raw OOXML ---
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        root = etree.fromstring(z.read("word/document.xml"))
        ins = root.findall(".//" + W + "ins")
        dele = root.findall(".//" + W + "del")
        nested_ins_del = sum(1 for el in ins if el.findall(".//" + W + "del"))
        nested_del_ins = sum(1 for el in dele if el.findall(".//" + W + "ins"))
        authors = sorted(
            {el.get(W + "author") for el in (ins + dele) if el.get(W + "author")}
        )
        print(
            f"  [OOXML] w:ins={len(ins)} w:del={len(dele)} "
            f"NESTED(ins>del)={nested_ins_del} NESTED(del>ins)={nested_del_ins}"
        )
        print(f"  [OOXML] w:author values: {authors}")
        if nested_ins_del or nested_del_ins:
            print("  [OOXML] *** NESTED TRACKED CHANGES DETECTED (corruption) ***")
            problems += 1

        # Adeu writes comments1.xml; LibreOffice may rename to the canonical
        # comments.xml on save — match either.
        cparts = [n for n in names if re.match(r"word/comments\d*\.xml$", n)]
        if cparts:
            total = 0
            cauthors: set[str] = set()
            for cp in cparts:
                croot = etree.fromstring(z.read(cp))
                coms = croot.findall(".//" + W + "comment")
                total += len(coms)
                cauthors |= {c.get(W + "author") for c in coms if c.get(W + "author")}
            print(
                f"  [OOXML] comment part(s)={cparts} comments={total} "
                f"authors={sorted(cauthors)}"
            )
        else:
            print("  [OOXML] comments: (none)")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        analyze(p)
    print("=" * 72)
    print(f"PROBLEMS: {problems}")
    sys.exit(1 if problems else 0)
