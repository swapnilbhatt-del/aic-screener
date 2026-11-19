"""Blind-memo leakage tests and notes parsing. Seed-dependent; skip if data not built."""
import json
import re
from pathlib import Path

import pytest
import yaml

from aic import memos, notes, text

ROOT = Path(__file__).resolve().parent.parent
built = (text.TEXT_DIR / "memos.json").exists() and (ROOT / "seed" / "curation").exists()
pytestmark = pytest.mark.skipif(not built, reason="seed text/curation not present")


@pytest.fixture(scope="module")
def sealed():
    memos.build()
    return json.loads((memos.SEALED / "decisions.json").read_text())["memos"]


@pytest.fixture(scope="module")
def blind(sealed):
    return {p.stem: json.loads(p.read_text()) for p in sorted(memos.BLIND.glob("MEMO-*.json"))}


def test_twelve_memos_six_each(sealed):
    assert len(sealed) == 12
    assert sum(m["decision"] == "INVESTED" for m in sealed) == 6
    assert sum(m["decision"] == "PASSED" for m in sealed) == 6


def test_blind_ids_do_not_follow_memo_order(sealed):
    order = [m["anon_id"] for m in sorted(sealed, key=lambda m: m["memo_no"])]
    assert order != sorted(order)


def test_blind_files_have_no_decision_stage_or_source(blind):
    assert len(blind) == 12
    for b in blind.values():
        assert set(b) == {"anon_id", "sector", "sections", "note"}
        assert set(b["sections"]) == {"what_it_does", "founder_assessment", "risks_and_open_questions"}


def test_blind_text_has_no_leak_terms_names_or_companies(blind, sealed):
    cfg = yaml.safe_load((memos.CURATION / "memo_redactions.yaml").read_text())
    names = {n for m in cfg["memos"].values() for n in (m.get("names") or {})}
    companies = {m["company"] for m in sealed} | {"ePlane"}
    for b in blind.values():
        body = " ".join(v for v in b["sections"].values() if v)
        low = f" {body.lower()} "
        for t in cfg["leak_terms"]:
            assert t not in low, (b["anon_id"], t)
        for n in names | companies:
            assert not re.search(rf"\b{re.escape(n)}\b", body, re.I), (b["anon_id"], n)
        for w in ("INVESTED", "PASSED", "Why we", "Early round", "Pre-seed", "Warm intro"):
            assert w.lower() not in low, (b["anon_id"], w)


def test_deciding_criteria_quotes_verified(sealed):
    assert all(d["verified"] for m in sealed for d in m["deciding_criteria"])
    assert all(m["deciding_criteria"] for m in sealed)


def test_notes_records():
    recs = notes.parse(text.load("notes"))
    assert {r["meeting"] for r in recs} == {1, 2, 3, 4, 5}
    assert all(r["page"] and r["text"] for r in recs)
    decisions = [r for r in recs if r["type"] == "decision"]
    assert any("Decision: hold" in r["text"] for r in decisions)
    assert any("Tuesday or Thursday" in r["text"] for r in recs)
