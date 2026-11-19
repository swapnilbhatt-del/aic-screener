"""Parse the deal-memo pack into (a) blind, anonymised memo texts for scoring and (b) sealed decision records.

Blind copies drop: Decision, Stage (perfectly correlated with the decision in this pack), Source,
the whole 'Why we invested/passed' section, founder names, company names, identifying facts listed in
seed/curation/memo_redactions.yaml, and any remaining sentence containing a leak term.
Memo numbers alternate invested/passed, so blind IDs are shuffled.
"""
import json
import random
import re
from pathlib import Path
from typing import Dict, List

import yaml

from . import text

ROOT = Path(__file__).resolve().parent.parent
CURATION = ROOT / "seed" / "curation"
OUT = ROOT / "data" / "memos"
BLIND = OUT / "blind"
SEALED = OUT / "sealed"
SHUFFLE_SEED = 20261119

HEADER = re.compile(
    r"Memo (\d+): (.+?) Sector: (.+?) \| Stage: (.+?) \| Source: (.+?) \| Decision: (INVESTED|PASSED) (.*?)(?=Memo \d+: |$)")
SECTIONS = ["What it does.", "Founder assessment.", "Risks and open questions."]
WHY = re.compile(r"Why we (invested|passed)\.")


def _memo_text(doc: dict) -> str:
    t = text.collapse(" ".join(p["plain"] for p in doc["pages"]))
    return re.sub(r"===== PAGE \d+ =====", " ", t)


def parse(doc: dict) -> List[dict]:
    t = _memo_text(doc)
    memos = []
    for m in HEADER.finditer(t):
        no, name, sector, stage, source, decision, body = m.groups()
        body = body.strip()
        w = WHY.search(body)
        why = body[w.start():].strip() if w else ""
        body_main = body[: w.start()].strip() if w else body
        parts = {}
        for i, s in enumerate(SECTIONS):
            start = body_main.find(s)
            end = min([body_main.find(n) for n in SECTIONS[i + 1:] if body_main.find(n) > start] or [len(body_main)])
            parts[s.rstrip(".").lower().replace(" ", "_")] = body_main[start + len(s): end].strip() if start >= 0 else None
        pages = text.find_quote(doc, f"Memo {no}: {name}")
        memos.append({"memo_no": int(no), "company": name.strip(), "sector": sector.strip(), "stage": stage.strip(),
                      "source": source.strip(), "decision": decision, "sections": parts, "why": why,
                      "page": pages[0] if pages else None})
    return memos


def _sentences(s: str) -> List[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+", s) if x]


def blind_copy(memo: dict, all_names: List[str], cfg: dict) -> (dict, List[dict]):
    rules = cfg["memos"].get(memo["memo_no"], {}) or {}
    log = []
    out = {}
    for key, val in memo["sections"].items():
        if val is None:
            out[key] = None
            log.append({"section": key, "action": "missing section"})
            continue
        v = val
        for old, new, why in rules.get("replace", []):
            if old in v:
                v = v.replace(old, new)
                log.append({"section": key, "action": "replace", "old": old, "new": new, "why": why})
        for old, new in sorted((rules.get("names") or {}).items(), key=lambda kv: -len(kv[0])):
            if re.search(rf"\b{re.escape(old)}\b", v):
                v = re.sub(rf"\b{re.escape(old)}\b", new, v)
                log.append({"section": key, "action": "name", "old": old, "new": new})
        for nm in sorted(all_names, key=len, reverse=True):
            if nm.lower() in v.lower():
                v = re.sub(re.escape(nm), "the company" if nm == memo["company"] else "another company", v, flags=re.I)
                log.append({"section": key, "action": "company_name", "old": nm})
        kept = []
        for s in _sentences(v):
            low = f" {s.lower()} "
            hit = [t for t in cfg["leak_terms"] if t in low]
            if hit:
                log.append({"section": key, "action": "leak_sentence", "old": s, "terms": hit})
            else:
                kept.append(s)
        out[key] = " ".join(kept).strip()
    return out, log


def build() -> Dict[str, int]:
    doc = text.load("memos")
    memos = parse(doc)
    cfg = yaml.safe_load((CURATION / "memo_redactions.yaml").read_text())
    criteria = yaml.safe_load((CURATION / "memo_deciding_criteria.yaml").read_text())
    names = [m["company"] for m in memos] + ["ePlane"]
    order = [m["memo_no"] for m in memos]
    random.Random(SHUFFLE_SEED).shuffle(order)
    anon = {no: f"MEMO-{chr(65 + i)}" for i, no in enumerate(order)}

    BLIND.mkdir(parents=True, exist_ok=True)
    SEALED.mkdir(parents=True, exist_ok=True)
    sealed = []
    for m in memos:
        sections, log = blind_copy(m, names, cfg)
        (BLIND / f"{anon[m['memo_no']]}.json").write_text(json.dumps(
            {"anon_id": anon[m["memo_no"]], "sector": m["sector"], "sections": sections,
             "note": "Decision, stage, source, rationale, names and identifying facts removed."},
            indent=1, ensure_ascii=False))
        dc = []
        for crit, quote in criteria.get(m["memo_no"], []):
            found = text.find_quote(doc, quote)
            dc.append({"criterion": crit, "quote": quote, "pages": found, "verified": bool(found)})
        sealed.append({**{k: m[k] for k in ("memo_no", "company", "sector", "stage", "source", "decision", "why", "page")},
                       "anon_id": anon[m["memo_no"]], "deciding_criteria": dc, "redaction_log": log})
    (SEALED / "decisions.json").write_text(json.dumps(
        {"WARNING": "SEALED. Read only after every blind score file exists (Stage 5).", "memos": sealed},
        indent=1, ensure_ascii=False))
    return {"memos": len(memos), "blind_files": len(memos),
            "criteria_quotes": sum(len(s["deciding_criteria"]) for s in sealed),
            "criteria_quotes_unverified": sum(not d["verified"] for s in sealed for d in s["deciding_criteria"]),
            "redactions": sum(len(s["redaction_log"]) for s in sealed)}
