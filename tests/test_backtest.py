"""Backtest blindness mechanics: vault round-trip, manifest gate on unsealing, outcome mapping."""
import json

import pytest

from aic import backtest


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "data/memos/blind").mkdir(parents=True)
    (root / "data/memos/sealed").mkdir(parents=True)
    (root / "data/backtest/raw").mkdir(parents=True)
    (root / "data/backtest/scores").mkdir(parents=True)
    (root / "data/memos/sealed/decisions.json").write_text(json.dumps({"memos": [{"anon_id": "MEMO-A"}]}))
    (root / "reports").mkdir()
    (root / "reports/x.md").write_text("leaky")
    for i in range(12):
        mid = f"MEMO-{chr(65 + i)}"
        (root / f"data/memos/blind/{mid}.json").write_text("{}")
        (root / f"data/backtest/raw/{mid}.json").write_text(json.dumps({"raw": i}))
        (root / f"data/backtest/scores/{mid}.json").write_text(json.dumps({"score": i}))
    monkeypatch.setattr(backtest, "ROOT", root)
    monkeypatch.setattr(backtest, "BLIND", root / "data/memos/blind")
    monkeypatch.setattr(backtest, "SEALED", root / "data/memos/sealed/decisions.json")
    monkeypatch.setattr(backtest, "RAW", root / "data/backtest/raw")
    monkeypatch.setattr(backtest, "OUT", root / "data/backtest/scores")
    monkeypatch.setattr(backtest, "MANIFEST", root / "data/backtest/scores_manifest.json")
    return root


def write_manifest(root):
    ids = [f"MEMO-{chr(65 + i)}" for i in range(12)]
    backtest.MANIFEST.write_text(json.dumps({
        "raw": {m: backtest._sha(backtest.RAW / f"{m}.json") for m in ids},
        "scores": {m: backtest._sha(backtest.OUT / f"{m}.json") for m in ids}}))


def test_unseal_refuses_without_manifest(sandbox):
    with pytest.raises(backtest.SealError, match="no scores manifest"):
        backtest.unseal()


def test_unseal_refuses_if_a_score_changed(sandbox):
    write_manifest(sandbox)
    (backtest.OUT / "MEMO-C.json").write_text(json.dumps({"score": "edited"}))
    with pytest.raises(backtest.SealError, match="MEMO-C: score changed"):
        backtest.unseal()


def test_unseal_refuses_if_not_all_twelve(sandbox):
    write_manifest(sandbox)
    m = json.loads(backtest.MANIFEST.read_text())
    del m["scores"]["MEMO-L"]
    backtest.MANIFEST.write_text(json.dumps(m))
    with pytest.raises(backtest.SealError, match="all 12"):
        backtest.unseal()


def test_unseal_reads_decisions_when_complete(sandbox):
    write_manifest(sandbox)
    assert backtest.unseal() == [{"anon_id": "MEMO-A"}]
    assert "unsealed_at" in json.loads(backtest.MANIFEST.read_text())


def test_vault_round_trip_hides_sealed_file(sandbox, tmp_path):
    v = tmp_path / "vault"
    moved = backtest.vault(v)
    assert "data/memos/sealed" in moved and "reports" in moved
    assert not backtest.SEALED.exists() and not (sandbox / "reports").exists()
    write_manifest(sandbox)
    with pytest.raises(backtest.SealError, match="still in the vault"):
        backtest.unseal()
    backtest.unvault(v)
    assert backtest.SEALED.exists() and (sandbox / "reports/x.md").read_text() == "leaky"


@pytest.mark.parametrize("decision,band,res", [
    ("INVESTED", "call", "agree"), ("INVESTED", "pass", "disagree"), ("INVESTED", "hold", "disagree"),
    ("PASSED", "pass", "agree"), ("PASSED", "hold", "agree"), ("PASSED", "call", "disagree"),
    ("INVESTED", "partner_review", "review"), ("PASSED", "partner_review", "review")])
def test_outcome_mapping(decision, band, res):
    assert backtest.outcome(decision, band) == res


def test_real_backtest_unsealed_after_scoring():
    """If the real backtest has run, decisions were read only after every score was hashed."""
    from pathlib import Path
    m = Path(backtest.__file__).resolve().parent.parent / "data/backtest/scores_manifest.json"
    if not m.exists():
        pytest.skip("backtest not run")
    man = json.loads(m.read_text())
    assert man["n"] == 12 and len(man["scores"]) == 12
    if "unsealed_at" in man:
        assert man["unsealed_at"] >= man["scored_at"]  # hash check in unseal() is the real guarantee
