"""Readable reconstruction of a tracked-changes ``.docx`` — C4 (ADR-F031).

Turns ``word/document.xml`` into a human/judge-readable per-paragraph view:
bare text = untouched run, ``[-x-]`` = ``w:del`` (deleted), ``[+y+]`` = ``w:ins``
(inserted). This is the "look at the produced redline, not the word count"
artifact (the maintainer's C4 requirement) — used by the golden-corpus tests
(Layer 2), the redline-quality judge (Layer 3), and the evidence dir (Layer 4).

Pure stdlib (``zipfile`` + ``xml.etree``). It operates only on **our generated
redline bytes** (trusted output we just authored via Adeu), so no untrusted-XML
guard is needed here — untrusted *uploads* are guarded by ``guard_ooxml`` at the
ingestion/redline-input boundary, never reaching this function.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _gather(node: ET.Element, tag: str) -> str:
    return "".join((t.text or "") for t in node.iter(_W + tag))


def reconstruct_redline(docx_bytes: bytes) -> list[str]:
    """Per-paragraph readable redline lines (skips blank paragraphs)."""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    lines: list[str] = []
    for p in root.iter(_W + "p"):
        seg: list[str] = []
        for child in p:
            local = child.tag.split("}")[-1]
            if local == "r":
                seg.append(_gather(child, "t"))
            elif local == "ins":
                seg.append(f"[+{_gather(child, 't')}+]")
            elif local == "del":
                seg.append(f"[-{_gather(child, 'delText')}-]")
        line = "".join(seg)
        if line.strip():
            lines.append(line)
    return lines


def reconstruct_redline_text(docx_bytes: bytes) -> str:
    """The reconstruction as one newline-joined string."""
    return "\n".join(reconstruct_redline(docx_bytes))


def bare_text(redline: str) -> str:
    """Strip tracked-change spans from a reconstruction, leaving only the unchanged
    (bare) text — what neither side touched. Used to assert recognisable boilerplate
    stays bare (the C8 surgical-craft check). Single shared definition (ADR-F041)."""
    no_ins = re.sub(r"\[\+.*?\+\]", "", redline, flags=re.DOTALL)
    return re.sub(r"\[-.*?-\]", "", no_ins, flags=re.DOTALL)


def docx_text(data: bytes) -> str:
    """Plain text of a ``.docx`` (one line per paragraph), via python-docx. Used by
    tests/eval to read the accept-to-clean result; python-docx is imported lazily so
    this module's reconstruction core stays import-light."""
    from docx import Document

    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
