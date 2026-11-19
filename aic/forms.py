"""Deterministic parser for the fund's application-form PDFs (two-column label/value layout).

Every field carries the page it was read from. Values are re-spaced against the plain text of the
page (layout mode inserts gaps after ligature glyphs), and flagged if that re-spacing fails.
"""
import re
from typing import Dict, List, Optional, Tuple

from . import text

# Raw form label -> canonical key. Labels not listed are kept under their raw label.
CANONICAL = {
    "Company name": "company_name", "Website": "website", "Location": "location",
    "Incorporated": "incorporated", "One-line description": "one_liner",
    "Sector (as selected)": "sector_selected", "Stage (as selected)": "stage_selected",
    "Team size": "team_size", "Founder": "founder_1", "Founder 1": "founder_1", "Founder 2": "founder_2",
    "Time commitment": "time_commitment", "Prior startup experience": "prior_startup_experience",
    "Earlier co-founder": "earlier_cofounder", "Equity split": "equity_split",
    "What have you built?": "product", "Key risks": "key_risks",
    "Amount raising": "raise", "Valuation expectation": "valuation", "Existing investors": "existing_investors",
    "Use of funds": "use_of_funds", "Other investors in conversation": "other_investors",
    "How did you hear about us?": "source", "Anything else we should know?": "anything_else",
    "Customer acquisition": "customer_acquisition", "Patient acquisition": "customer_acquisition",
}

ROW = re.compile(r"^ (\S.*?)\s{2,}(\S.*)$")
LABEL_ONLY = re.compile(r"^ (\S.{0,40})$")
FREE_SECTION = "Anything else we should know?"


def _respace(value_layout: str, page_plain: str) -> Tuple[str, bool]:
    """Find the layout value inside the plain page text, ignoring whitespace; return plain spacing."""
    target = text.squash(value_layout)
    plain = text.normalise(page_plain)
    idx, keys = [], []
    for i, ch in enumerate(plain):
        if not ch.isspace():
            idx.append(i)
            keys.append(ch.lower())
    hay = "".join(keys)
    pos = hay.find(target)
    if pos < 0 or not target:
        return text.collapse(value_layout), False
    return text.collapse(plain[idx[pos]: idx[pos + len(target) - 1] + 1]), True


def parse_form(doc: dict) -> Dict[str, dict]:
    fields: List[dict] = []
    cur: Optional[dict] = None
    in_free = False
    for p in doc["pages"]:
        for line in p["layout"].split("\n"):
            if not line.strip():
                continue
            if in_free:
                cur["raw"].append(line)
                continue
            if text.collapse(line) == FREE_SECTION:
                cur = {"label": FREE_SECTION, "raw": [], "page": p["page"]}
                fields.append(cur)
                in_free = True
                continue
            m = ROW.match(line)
            if m:
                cur = {"label": m.group(1).strip(), "raw": [m.group(2)], "page": p["page"]}
                fields.append(cur)
                continue
            if line.startswith("   ") and cur is not None:
                cur["raw"].append(line)  # value continuation
                continue
            m = LABEL_ONLY.match(line)
            if m and cur is not None and len(cur["raw"]) == 1 and not line.startswith("  "):
                # label wrapped onto a second line, e.g. "Other investors in / conversation"
                cur["label"] = f"{cur['label']} {m.group(1).strip()}"
                continue
            cur = None  # section header or page furniture
    out: Dict[str, dict] = {}
    for f in fields:
        page_plain = doc["pages"][f["page"] - 1]["plain"]
        raw_value = " ".join(s.strip() for s in f["raw"])
        value, clean = _respace(raw_value, page_plain)
        if not clean:  # value may straddle a page break: try the whole document
            value, clean = _respace(raw_value, "\n".join(pg["plain"] for pg in doc["pages"]))
        key = CANONICAL.get(f["label"], f["label"])
        if key in out:
            key = f"{key}__{f['label']}"
        out[key] = {"label": f["label"], "value": value, "page": f["page"], "respaced": clean}
    return out


def parse_founder(value: str) -> dict:
    """'Dhruv Shah, CEO. Qualified ...' -> name, role, background. Purely positional; no inference."""
    v = re.sub(r"\s*(LinkedIn:\s*)?linkedin\.com/\S+", "", value).strip()
    m = re.match(r"^([^,.]+?)(?:,\s*([^.]+?))?(?:\.\s+|\s+Background:\s*|$)(.*)$", v)
    name, role, rest = (m.group(1), m.group(2), m.group(3)) if m else (v, None, "")
    rest = re.sub(r"^Background:\s*", "", rest.strip())
    li = re.search(r"linkedin\.com/\S+", value)
    return {"name": name.strip(), "role": (role or "").strip() or None, "background": rest.strip(),
            "linkedin": li.group(0).rstrip(".") if li else None}
