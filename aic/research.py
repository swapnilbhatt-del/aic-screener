"""Stage 3: research cache. Findings are gathered by research agents (prompts/research.md) and written to
data/research/<Company>.json. This module writes the per-company briefs the agents work from, and validates
the cache in code. Reruns read the cache; nothing is re-fetched unless a human deletes the file.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "research"
BRIEFS = DIR / "briefs"
APPS = ROOT / "data" / "applications"

TOPICS = {"market", "competitor", "founder", "regulatory", "portfolio", "thesis", "company"}
STANCES = {"supports", "contradicts", "context"}
SOURCE_TYPES = {"government", "regulator", "company", "news", "research", "database", "other"}
CONF = {"high", "medium", "low"}
DATE_RE = re.compile(r"^(\d{4}(-\d{2}(-\d{2})?)?|unknown)$")
MAX_QUOTE_WORDS = 25
BRIEF_METRICS = {"market_tam_inr", "market_sam_inr", "market_som_inr", "market_headline_inr", "market_share_claim",
                 "competitor_named", "competition_claim", "regulatory_dependency", "credit_funding", "dependency",
                 "key_risk", "founder_name", "founder_role", "founder_credential", "founder_prior_startup",
                 "cofounder_departure"}


def write_briefs(companies: List[str]) -> None:
    """One brief per company: what the application claims that outside sources can test."""
    BRIEFS.mkdir(parents=True, exist_ok=True)
    for co in companies:
        app = json.loads((APPS / f"{co}.json").read_text())
        ff = app["form_fields"]
        lines = [f"# Research brief: {co}", "",
                 f"- One-liner (form): {ff.get('one_liner', {}).get('value', '')}",
                 f"- Location: {ff.get('location', {}).get('value', '')}",
                 f"- Sector selected: {ff.get('sector_selected', {}).get('value', '')}",
                 f"- Stage selected: {ff.get('stage_selected', {}).get('value', '')}",
                 f"- Incorporated: {ff.get('incorporated', {}).get('value', '')}",
                 "- Website and LinkedIn links in the application use reserved '.example' / '-example' addresses. "
                 "Do not fetch them; they do not resolve.", "",
                 "## Claims to test (claim id, document, as written, quote)", ""]
        for group in app["claims"].values():
            for c in group:
                if c["metric"] in BRIEF_METRICS and c.get("valid"):
                    comp = ""
                    if c.get("components"):
                        comp = " | inputs: " + " x ".join(x["as_written"] for x in c["components"])
                    ent = f" [{c['entity']}]" if c.get("entity") else ""
                    lines.append(f"- `{c['id']}` ({c['doc']} p{c['page']}) {c['metric']}{ent}: "
                                 f"\"{c['as_written']}\"{comp} -- quote: \"{c['quote'][:200]}\"")
        (BRIEFS / f"{co}.md").write_text("\n".join(lines) + "\n")


def _words(s: str) -> int:
    return len(s.split())


def validate(rec: dict, known_claim_ids: set = frozenset()) -> List[str]:
    errs = []
    for k in ("company", "accessed_date", "queries", "findings", "competitors", "conflicts", "not_found"):
        if k not in rec:
            errs.append(f"missing top-level {k}")
    if errs:
        return errs
    ids = set()
    for f in rec["findings"]:
        fid = f.get("id", "?")
        if fid in ids:
            errs.append(f"{fid}: duplicate id")
        ids.add(fid)
        for k in ("topic", "supports_claim", "stance", "finding", "url", "source_title", "publisher",
                  "published_date", "accessed_date", "source_type", "confidence"):
            if not f.get(k):
                errs.append(f"{fid}: missing {k}")
        if f.get("topic") not in TOPICS:
            errs.append(f"{fid}: bad topic {f.get('topic')}")
        if f.get("stance") not in STANCES:
            errs.append(f"{fid}: bad stance {f.get('stance')}")
        if f.get("source_type") not in SOURCE_TYPES:
            errs.append(f"{fid}: bad source_type {f.get('source_type')}")
        if f.get("confidence") not in CONF:
            errs.append(f"{fid}: bad confidence")
        url = f.get("url", "")
        if not re.match(r"^https?://[^/\s]+\.[^/\s]+", url):
            errs.append(f"{fid}: url not http(s)")
        if ".example" in url or "-example" in url:
            errs.append(f"{fid}: url is a reserved example address")
        if not DATE_RE.match(str(f.get("published_date", ""))):
            errs.append(f"{fid}: published_date must be YYYY[-MM[-DD]] or 'unknown'")
        try:
            date.fromisoformat(f.get("accessed_date", ""))
        except ValueError:
            errs.append(f"{fid}: accessed_date not ISO")
        if f.get("quote") and _words(f["quote"]) > MAX_QUOTE_WORDS:
            errs.append(f"{fid}: quote over {MAX_QUOTE_WORDS} words")
        if f.get("claim_ref") and known_claim_ids and f["claim_ref"] not in known_claim_ids:
            errs.append(f"{fid}: claim_ref {f['claim_ref']} not a known claim/check id")
    for c in rec["competitors"]:
        nm = c.get("name", "?")
        if not c.get("finding_ids"):
            errs.append(f"competitor {nm}: no finding_ids")
        for i in c.get("finding_ids", []):
            if i not in ids:
                errs.append(f"competitor {nm}: unknown finding {i}")
        if c.get("funded") and not c.get("funding"):
            errs.append(f"competitor {nm}: funded but no funding detail")
    for k in rec["conflicts"]:
        fids = k.get("finding_ids", [])
        if len(fids) < 2 or any(i not in ids for i in fids):
            errs.append(f"conflict '{k.get('topic')}': needs >=2 known finding ids")
        if not k.get("description"):
            errs.append(f"conflict '{k.get('topic')}': no description")
    for n in rec["not_found"]:
        if not n.get("question") or not n.get("queries_tried"):
            errs.append("not_found entry needs question and queries_tried")
    return errs


def known_ids(company: str) -> set:
    ids = set()
    p = ROOT / "data" / "claims" / f"{company}.json"
    if p.exists():
        ids |= {c["id"] for c in json.loads(p.read_text())["claims"]}
    p = ROOT / "data" / "checks" / f"{company}.json"
    if p.exists():
        ids |= {c["id"] for c in json.loads(p.read_text())}
    return ids


def validate_file(name: str) -> List[str]:
    rec = json.loads((DIR / f"{name}.json").read_text())
    return validate(rec, known_ids(name))


def summary(name: str) -> dict:
    rec = json.loads((DIR / f"{name}.json").read_text())
    by = {}
    for f in rec["findings"]:
        by.setdefault(f["topic"], {}).setdefault(f["stance"], 0)
        by[f["topic"]][f["stance"]] += 1
    return {"findings": len(rec["findings"]), "by_topic": by, "competitors": len(rec["competitors"]),
            "funded_competitors": sum(bool(c.get("funded")) for c in rec["competitors"]),
            "conflicts": len(rec["conflicts"]), "not_found": len(rec["not_found"]),
            "distinct_domains": len({re.sub(r"^https?://(www\.)?", "", f["url"]).split("/")[0] for f in rec["findings"]})}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "validate":
        e = validate_file(sys.argv[2])
        print(f"{sys.argv[2]}: {len(e)} errors")
        for x in e:
            print("  ", x)
        sys.exit(1 if e else 0)
    if len(sys.argv) == 2 and sys.argv[1] == "briefs":
        from .ingest import COMPANIES
        write_briefs(COMPANIES)
        print("briefs written")
