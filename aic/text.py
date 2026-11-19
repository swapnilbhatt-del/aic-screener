"""PDF -> per-page text, plus whitespace-insensitive quote location.

Every downstream citation points at (doc_id, page). A quote counts as found on a page if, after
normalising ligatures and removing all whitespace, it is a substring of that page's text.
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed"
TEXT_DIR = ROOT / "data" / "text"

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
             "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-",
             " ": " "}


def normalise(s: str) -> str:
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return s


def squash(s: str) -> str:
    """Remove all whitespace after normalising: the comparison key for quotes."""
    return re.sub(r"\s+", "", normalise(s)).lower()


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", normalise(s)).strip()


def doc_paths() -> Dict[str, Path]:
    """doc_id -> PDF path. doc_ids: '<Company>/deck', '<Company>/form', 'memos', 'notes'."""
    out = {"memos": SEED / "memos" / "deal_memos.pdf", "notes": SEED / "notes" / "partner_meeting_notes.pdf"}
    for d in sorted((SEED / "applications").iterdir()):
        if d.is_dir():
            out[f"{d.name}/deck"] = d / "deck.pdf"
            out[f"{d.name}/form"] = d / "form.pdf"
    return out


def _slide_label(text: str, company: Optional[str]) -> Optional[str]:
    if not company:
        return None
    m = re.search(rf"\b{re.escape(company)}\s+(\d{{1,2}})\s*$", text, re.M)
    return m.group(1) if m else None


def extract(doc_id: str, path: Path) -> dict:
    r = PdfReader(str(path))
    company = doc_id.split("/")[0] if doc_id.endswith("/deck") else None
    pages = []
    for i, p in enumerate(r.pages, 1):
        plain = normalise(p.extract_text() or "")
        layout = normalise(p.extract_text(extraction_mode="layout") or "")
        pages.append({"page": i, "slide_label": _slide_label(plain, company), "plain": plain,
                      "layout": layout, "empty": not plain.strip()})
    return {"doc_id": doc_id, "source": str(path.relative_to(ROOT)), "n_pages": len(pages), "pages": pages}


def build_all() -> List[dict]:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    docs = []
    for doc_id, path in doc_paths().items():
        d = extract(doc_id, path)
        (TEXT_DIR / (doc_id.replace("/", "__") + ".json")).write_text(json.dumps(d, indent=1, ensure_ascii=False))
        docs.append(d)
    return docs


def load(doc_id: str) -> dict:
    return json.loads((TEXT_DIR / (doc_id.replace("/", "__") + ".json")).read_text())


def find_quote(doc: dict, quote: str) -> List[int]:
    """Pages on which the quote occurs (whitespace- and case-insensitive)."""
    q = squash(quote)
    if not q:
        return []
    return [p["page"] for p in doc["pages"] if q in squash(p["plain"]) or q in squash(p["layout"])]


def cite(doc: dict, page: int) -> str:
    p = doc["pages"][page - 1]
    return f"{doc['doc_id']} p{page}" + (f" (slide {p['slide_label']})" if p.get("slide_label") else "")
