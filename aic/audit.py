"""Prompt audit (case Task 1: "Check every place your build calls an AI model. Look at exactly what each call sends, and
trim it to what that step needs.") Computed from the live request builders, so it cannot drift from what is sent.

For each kind of call: what it sends, how much was available vs how much is sent, and how many email addresses and
phone numbers the redaction step replaced with ID tokens before sending (aic/llm.redact, applied to every call).

  python -m aic.audit
"""
import json
import sys
from pathlib import Path

from . import config, llm, runner

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _size(*paths: Path) -> int:
    return sum(p.stat().st_size for p in paths if p.exists())


def _pii(text: str) -> int:
    return llm.redact([text])[1]


def _req_chars(req: dict) -> int:
    return len(req["system"]) + sum(len(m["content"]) for m in req["messages"])


def build(cfg=None) -> dict:
    cfg = cfg or config.load()
    cos = runner.companies()
    rows = []

    def add(call, what, sends, available_fn, request_fn, note):
        avail = sent = pii = n = 0
        for co in cos:
            try:
                req = request_fn(co)
            except Exception:
                continue
            n += 1
            sent += _req_chars(req)
            pii += _pii(req["system"] + "".join(m["content"] for m in req["messages"]))
            avail += available_fn(co)
        if n:
            rows.append({"call": call, "what": what, "sends": sends, "applications": n,
                         "available_chars": round(avail / n), "sent_chars": round(sent / n),
                         "trimmed_pct": round(100 * (1 - sent / avail), 1) if avail else None,
                         "pii_found": pii, "pii_sent": 0, "note": note})

    text = lambda co, *docs: _size(*[DATA / "text" / f"{co}__{d}.json" for d in docs])
    add("extraction", "Pull every claim out of the deck and form",
        "Page text only (no layout copy), page numbers and slide labels",
        lambda co: text(co, "deck", "form"), lambda co: runner.build_request("extraction", co),
        "Layout copies of each page are dropped; the model needs the words, not their positions.")
    add("research", "Check claims on the web",
        "A short research brief (claims to test, founder names, competitors named); no documents",
        lambda co: text(co, "deck", "form") + _size(DATA / "claims" / f"{co}.json"),
        lambda co: runner.build_request("research", co),
        "Search results come back as findings with URL and access date; whole web pages are never passed on.")
    add("scoring (full card)", "Score the 12 criteria",
        "Validated claims, check results, research findings and the parsed form; no PDFs, no web pages",
        lambda co: text(co, "deck", "form") + _size(DATA / "claims" / f"{co}.raw.json", DATA / "checks" / f"{co}.json",
                                                    DATA / "research" / f"{co}.json", DATA / "research" / "_fund.json",
                                                    DATA / "applications" / f"{co}.json"),
        lambda co: runner.build_request("scoring", co),
        "Claims replace documents and findings replace web pages. Fund research is shared across companies.")
    crits = list(cfg["criteria"])
    add("scoring (one criterion)", "Score one criterion (fine-tuning format)",
        "Only the inputs that criterion needs (config finetune.criterion_inputs); claim quotes dropped",
        lambda co: len(json.dumps(runner.build_request("scoring", co)["messages"][0]["content"])),
        lambda co: max((runner.build_criterion_request(co, k, cfg) for k in crits), key=_req_chars),
        "Largest of the 12 per-criterion requests, compared with the full-card request.")
    blind = sorted((DATA / "memos" / "blind").glob("MEMO-*.json"))
    if blind:
        sent = [len(p.read_text()) for p in blind]
        full = _size(DATA / "text" / "memos.json")
        rows.append({"call": "backtest (blind memo scoring)", "what": "Score a past deal memo without its outcome",
                     "sends": "One anonymised memo at a time: 3 sections (what it does, founder assessment, risks); "
                              "names, decision, stage, source and rationale removed",
                     "applications": len(blind), "available_chars": round(full) if full else None,
                     "sent_chars": round(sum(sent) / len(sent)),
                     "trimmed_pct": round(100 * (1 - (sum(sent) / len(sent)) / full), 1) if full else None,
                     "pii_found": sum(_pii(p.read_text()) for p in blind), "pii_sent": 0,
                     "note": "Relevant passages of one memo, not every memo (available = all 12 memos' text)."})
    return {"calls": rows,
            "redaction": "Every model call passes through llm.redact: email addresses and phone numbers become stable ID "
                         "tokens such as [email:1d4c122b] before anything leaves the machine. Founder names stay, because "
                         "research has to search for them."}


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
