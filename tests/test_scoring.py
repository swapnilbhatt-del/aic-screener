"""Scoring engine tests: totals, caps, bands, close calls and validation, using a fake source (no seed needed)."""
import copy

import pytest

from aic import config, scoring
from aic.scoring import CRITERIA, ScoreError


class FakeSrc(scoring.Sources):
    def __init__(self, material=False, market_fail=False, founder_supported=False, sector="Fintech", stage="Pre-seed",
                 overlaps=()):
        self.company, self.memo = "X", None
        self.claims = {"c1": {"quote": "24 paying CA firms", "as_written": "24", "cite": "X/form p1"}}
        self.checks = {}
        if material:
            self.checks["xdoc.customers_paying"] = {"id": "xdoc.customers_paying", "status": "FAIL", "kind": "cross_document",
                                                    "material_field": "traction", "label": "paying", "inputs": []}
        if market_fail:
            self.checks["market.tam"] = {"id": "market.tam", "status": "FAIL", "kind": "formula", "label": "TAM", "inputs": []}
        self.research = {"R1": {"topic": "founder" if founder_supported else "market", "stance": "supports",
                                "url": "https://a.org/x", "accessed_date": "2026-11-19", "published_date": "2025",
                                "confidence": "high", "publisher": "p", "finding": "f", "quote": ""}}
        self.fund_rec = {"findings": [], "overlaps": list(overlaps)}
        self.fund = {"F1": {"topic": "portfolio", "stance": "context", "url": "https://b.org", "accessed_date": "2026-11-19",
                            "published_date": "2025", "confidence": "high", "publisher": "p", "finding": "overlap", "quote": ""}}
        self.form = {"sector_selected": {"value": sector, "page": 1}, "stage_selected": {"value": stage, "page": 1}}


EV = [{"ref": "claim:c1", "point": "p", "quote": "24 paying"}]


def raw(scores=None, t2=(True, True, False, False, False), gates=None):
    scores = scores or {k: 3 for k in CRITERIA}
    names = config.load()["criteria"]["T2"]["subparts"]
    crit = {k: {"score": scores[k], "unknown": scores[k] == 0, "confidence": "medium", "rationale": "r",
                "evidence": EV if scores[k] else []} for k in CRITERIA}
    crit["T2"]["score"] = sum(t2)
    crit["T2"]["unknown"] = sum(t2) == 0
    crit["T2"]["evidence"] = EV if sum(t2) else []
    crit["T2"]["subparts"] = {n: {"present": p, "evidence": EV if p else []} for n, p in zip(names, t2)}
    crit["M3"].update(public_line_fit="fit", observed_pattern_fit="partial")
    g = gates or {}
    return {"company": "X", "criteria": crit,
            "gates": {k: g.get(k, {"state": "clear", "reason": "r", "evidence": []}) for k in scoring.MODEL_GATES}}


def run(r, src=None):
    cfg = config.load()
    src = src or FakeSrc()
    errs, resolved = scoring.validate(r, src, cfg)
    if errs:
        raise ScoreError(" | ".join(errs))
    proposed = {k: r["criteria"][k]["score"] for k in CRITERIA}
    final, adj = scoring.apply_caps(proposed, src, cfg)
    pts = {k: cfg["criteria"][k]["weight"] * final[k] / 5 for k in CRITERIA}
    total = sum(pts.values())
    gates = {**scoring.code_gates(src, cfg), **{g: resolved[f"gate:{g}"] for g in scoring.MODEL_GATES}}
    band, why = scoring.band_for(total, gates, bool(scoring.material_contradictions(src)), cfg)
    return total, final, adj, band, gates


def test_totals_are_weighted_in_code():
    total, final, *_ = run(raw({k: 5 if k != "T2" else 0 for k in CRITERIA}, t2=(True,) * 5))
    assert final["F1"] == 4                     # founder evidence cap
    # founder 4/5 of 35 = 28; everything else full 65
    assert total == pytest.approx(28 + 65)


def test_all_threes_is_sixty_with_t2_two():
    total, *_ = run(raw())
    # all criteria 3 except T2 = 2: 100*3/5 - 15*(1/5) = 60 - 3 = 57
    assert total == pytest.approx(57)


def test_pedigree_cap():
    s = {k: 3 for k in CRITERIA}
    s.update(F1=4, F2=2, F3=2)
    _, final, adj, *_ = run(raw(s))
    assert final["F1"] == 2 and any(a["rule"].startswith("pedigree_cap") for a in adj)
    s.update(F3=3)
    _, final, *_ = run(raw(s))
    assert final["F1"] == 4


def test_founder_evidence_cap_lifted_by_outside_support():
    s = {k: 5 if k.startswith("F") else 3 for k in CRITERIA}
    _, final, *_ = run(raw(s), FakeSrc(founder_supported=True))
    assert final["F1"] == 5
    _, final, *_ = run(raw(s), FakeSrc(founder_supported=False))
    assert all(final[k] == 4 for k in ("F1", "F2", "F3", "F4"))


def test_missing_is_zero_and_unknown_must_be_zero():
    r = raw()
    r["criteria"]["T3"].update(score=2, unknown=True)
    with pytest.raises(ScoreError, match="unknown criteria must score 0"):
        run(r)


def test_score_without_evidence_rejected():
    r = raw()
    r["criteria"]["F2"]["evidence"] = []
    with pytest.raises(ScoreError, match="no resolvable evidence"):
        run(r)


def test_unresolvable_ref_and_bad_quote_rejected():
    r = raw()
    r["criteria"]["F2"]["evidence"] = [{"ref": "claim:nope", "point": "p"}]
    with pytest.raises(ScoreError, match="does not resolve"):
        run(r)
    r = raw()
    r["criteria"]["F2"]["evidence"] = [{"ref": "claim:c1", "point": "p", "quote": "31 paying"}]
    with pytest.raises(ScoreError, match="quote not found"):
        run(r)


def test_t2_must_equal_subparts():
    r = raw()
    r["criteria"]["T2"]["score"] = 4
    with pytest.raises(ScoreError, match="T2: score 4"):
        run(r)


def test_anchor_rules_reject_not_override():
    r = raw()
    with pytest.raises(ScoreError, match="S2: anchor"):
        run(r, FakeSrc(material=True))
    with pytest.raises(ScoreError, match="M1: anchor"):
        run(r, FakeSrc(market_fail=True))
    s = {k: 3 for k in CRITERIA}
    s.update(S2=1, M1=1)
    run(raw(s), FakeSrc(material=True, market_fail=True))


def high():
    return {k: 5 for k in CRITERIA}


def test_band_call_and_integrity_cap():
    s = high()
    _, _, _, band, _ = run(raw(s, t2=(True,) * 5), FakeSrc(founder_supported=True))
    assert band == "call"
    s["S2"] = 1
    _, _, _, band, _ = run(raw(s, t2=(True,) * 5), FakeSrc(founder_supported=True, material=True))
    assert band == "partner_review"


def test_flag_routes_to_partner_review_and_hold_wins():
    s = high()
    _, _, _, band, _ = run(raw(s, t2=(True,) * 5), FakeSrc(founder_supported=True, stage="Series A"))
    assert band == "partner_review"
    _, _, _, band, g = run(raw(s, t2=(True,) * 5), FakeSrc(founder_supported=True, overlaps=[
        {"applicant": "X", "portfolio_company": "P", "strength": "direct", "basis": "same", "finding_ids": ["F1"]}]))
    assert band == "hold" and g["G1"]["state"] == "hold"


def test_adjacent_overlap_does_not_hold():
    _, _, _, band, g = run(raw(), FakeSrc(overlaps=[
        {"applicant": "X", "portfolio_company": "P", "strength": "adjacent", "basis": "near", "finding_ids": ["F1"]}]))
    assert g["G1"]["state"] == "clear" and g["G1"]["adjacent_overlaps"] == ["P"]


def test_sector_outside_public_line_flags():
    _, _, _, _, g = run(raw(), FakeSrc(sector="Other (Healthcare)"))
    assert g["G2c"]["state"] == "flag"


def test_model_flag_needs_evidence():
    r = raw(gates={"G5": {"state": "flag", "reason": "lends", "evidence": []}})
    with pytest.raises(ScoreError, match="gate G5: flag without evidence"):
        run(r)


@pytest.mark.parametrize("total,expected", [(75, 70), (65, 70), (64.9, None), (60, 55), (50, 55), (49.9, None), (70, 70)])
def test_close_call_inclusive(total, expected):
    assert scoring.close_call(total, config.load()) == expected


def test_flag_below_pass_stays_pass_with_flag():
    s = {k: 1 for k in CRITERIA}
    _, _, _, band, g = run(raw(s, t2=(True, False, False, False, False)), FakeSrc(stage="Series A"))
    assert band == "pass" and g["G3"]["state"] == "flag"


def test_low_band():
    s = {k: 1 for k in CRITERIA}
    _, _, _, band, _ = run(raw(s, t2=(True, False, False, False, False)))
    assert band == "pass"


def test_t2_channel_rule_normalises_and_marks_unknown():
    cfg = config.load()
    src = FakeSrc()
    r = raw(t2=(False, True, False, False, False))
    errs, resolved = scoring.validate(r, src, cfg)
    assert not errs
    proposed = {k: r["criteria"][k]["score"] for k in CRITERIA}
    adj = scoring.normalise_t2(resolved, src, cfg, proposed)
    assert proposed["T2"] == 0 and resolved["T2"]["unknown"] is True and adj[0]["to"] == 0
    src.claims.update({f"ch{i}": {"metric": "cac_channel_inr", "valid": True, "value": 100 + i, "entity": e,
                                  "quote": "q", "as_written": "x"} for i, e in enumerate(["paid social", "referrals"])})
    r = raw(t2=(False, False, False, False, False))
    errs, resolved = scoring.validate(r, src, cfg)
    proposed = {k: r["criteria"][k]["score"] for k in CRITERIA}
    scoring.normalise_t2(resolved, src, cfg, proposed)
    assert proposed["T2"] == 1 and resolved["T2"]["subparts"]["cac_by_channel"]["present"] is True


# ---- produced scores (seed-dependent) -------------------------------------
import json as _json
from pathlib import Path as _P
_SC = sorted((_P(scoring.OUT)).glob("*.json"))


@pytest.mark.skipif(not _SC, reason="no scores produced")
@pytest.mark.parametrize("path", _SC, ids=lambda p: p.stem)
def test_every_score_cites_evidence(path):
    r = _json.loads(path.read_text())
    cfg = config.load()
    assert r["total"] == pytest.approx(sum(cfg["criteria"][k]["weight"] * c["final"] / 5 for k, c in r["criteria"].items()))
    for k, c in r["criteria"].items():
        if c["final"] == 0:
            assert c["unknown"] or c["proposed"] == 0
            continue
        assert c["evidence"], (path.stem, k)
        for e in c["evidence"]:
            if e["type"] == "external":
                assert e["url"].startswith("http") and e["accessed_date"], (path.stem, k)
            else:
                assert e.get("cite"), (path.stem, k, e["ref"])
    assert r["founder_subtotal"] + r["path_subtotal"] + r["thesis_subtotal"] + r["structure_subtotal"] == pytest.approx(r["total"])
    if r["integrity_cap"]["applies"]:
        assert r["band"] != "call"


def test_outcomes_are_undecided_in_db():
    from aic import db
    if not db.DEFAULT_DB.exists():
        pytest.skip("no db")
    conn = db.connect()
    rows = conn.execute("SELECT company, human_decision FROM outcomes").fetchall()
    assert rows and all(d is None for _, d in rows)
