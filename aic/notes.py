"""Parse partner meeting notes into structured records: one per bullet, with meeting, topic and page.

Types are assigned by explicit textual markers only (no interpretation):
  decision  bullet starts with 'Decision:' / 'Resolved:' / 'Pass.' / 'Left open.' or contains 'Decision: hold'
  action    bullet under an 'Actions' heading
  score     bullet mentions a numeric score given by Riya ('scored', '/10', 'given it a')
  note      everything else
Rules and disagreements are left for the scorer/partners to interpret; the rubric's own citations
([Notes mN]) can be checked against these records by quote.
"""
import json
import re
from pathlib import Path
from typing import List

from . import text

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "notes.json"

MEETING = re.compile(r"^Meeting (\d+) - (.+)$")
PRESENT = re.compile(r"^Present:\s*(.+)$")
BULLET = re.compile(r"^\s+●\s+(.*)$")
CONT = re.compile(r"^\s{6,}(\S.*)$")
DECISION = re.compile(r"^(Decision:|Resolved:|Pass\.|Left open\.)|Decision: hold", re.I)
SCORE = re.compile(r"scored|/10\b|given it a \d", re.I)


def parse(doc: dict) -> List[dict]:
    recs: List[dict] = []
    meeting = title = topic = None
    present = None
    cur = None
    for p in doc["pages"]:
        for line in p["layout"].split("\n"):
            if not line.strip() or line.startswith("MESA MBA") or line.startswith("All In Capital"):
                continue
            m = MEETING.match(line.strip())
            if m:
                meeting, title, topic, present, cur = int(m.group(1)), m.group(2).strip(), None, None, None
                continue
            m = PRESENT.match(line.strip())
            if m and meeting:
                present = m.group(1).strip()
                continue
            m = BULLET.match(line)
            if m and meeting:
                cur = {"meeting": meeting, "meeting_title": title, "present": present, "topic": topic,
                       "text": m.group(1).strip(), "page": p["page"]}
                recs.append(cur)
                continue
            m = CONT.match(line)
            if m and cur is not None:
                cur["text"] += " " + m.group(1).strip()
                continue
            if meeting and not line.startswith(" "):
                topic, cur = text.collapse(line), None   # topic heading, e.g. 'Petalry (D2C skincare)'
    for i, r in enumerate(recs, 1):
        r["id"] = f"m{r['meeting']}.{i}"
        r["text"] = text.collapse(r["text"])
        if r["topic"] and r["topic"].lower().startswith("actions"):
            r["type"] = "action"
        elif DECISION.search(r["text"]):
            r["type"] = "decision"
        elif SCORE.search(r["text"]):
            r["type"] = "score"
        else:
            r["type"] = "note"
        r["speakers"] = sorted(set(re.findall(r"\b(Kushal|Aditya|Riya)\b", r["text"])))
    return recs


def build() -> dict:
    recs = parse(text.load("notes"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"records": recs}, indent=1, ensure_ascii=False))
    by_type = {}
    for r in recs:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    return {"records": len(recs), "meetings": len({r["meeting"] for r in recs}), "by_type": by_type}
