"""Research cache validator tests (synthetic records) and, when the cache exists, validation of every file."""
import copy
import json

import pytest

from aic import research

GOOD = {
    "company": "X", "researched_by": "subagent", "accessed_date": "2026-11-19",
    "queries": [{"q": "x competitors india", "tool": "WebSearch"}],
    "findings": [
        {"id": "R1", "topic": "competitor", "supports_claim": "'no direct competitors'", "stance": "contradicts",
         "finding": "A funded rival offers the same product.", "quote": "short quote", "url": "https://news.site.org/a",
         "source_title": "t", "publisher": "p", "published_date": "2025-03", "accessed_date": "2026-11-19",
         "source_type": "news", "confidence": "high"},
        {"id": "R2", "topic": "market", "supports_claim": "TAM input", "stance": "supports", "finding": "f",
         "url": "https://gov.in/report", "source_title": "t", "publisher": "p", "published_date": "unknown",
         "accessed_date": "2026-11-19", "source_type": "government", "confidence": "medium"},
        {"id": "R3", "topic": "market", "supports_claim": "TAM input", "stance": "contradicts", "finding": "f",
         "url": "https://research.org/r", "source_title": "t", "publisher": "p", "published_date": "2024",
         "accessed_date": "2026-11-19", "source_type": "research", "confidence": "medium"}],
    "competitors": [{"name": "Rival", "funded": True, "funding": "USD 5M Seed 2024", "named_in_application": False,
                     "finding_ids": ["R1"]}],
    "conflicts": [{"topic": "market size", "finding_ids": ["R2", "R3"], "description": "sources differ"}],
    "not_found": [{"question": "founder background", "queries_tried": ["name company"]}],
}


def test_good_record_passes():
    assert research.validate(GOOD) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda r: r["findings"][0].update(url="www.no-scheme.com"), "url not http"),
    (lambda r: r["findings"][0].update(url="https://acme.example/x"), "reserved example"),
    (lambda r: r["findings"][0].update(url="https://linkedin.com/in/a-example"), "reserved example"),
    (lambda r: r["findings"][0].pop("url"), "missing url"),
    (lambda r: r["findings"][0].update(accessed_date="19/11/2026"), "accessed_date not ISO"),
    (lambda r: r["findings"][0].update(published_date="March 2025"), "published_date"),
    (lambda r: r["findings"][0].update(stance="maybe"), "bad stance"),
    (lambda r: r["findings"][0].update(topic="gossip"), "bad topic"),
    (lambda r: r["findings"][0].update(quote=" ".join(["w"] * 26)), "quote over 25"),
    (lambda r: r["findings"][1].update(id="R1"), "duplicate id"),
    (lambda r: r["competitors"][0].update(finding_ids=["R9"]), "unknown finding"),
    (lambda r: r["competitors"][0].update(funding=None), "funded but no funding"),
    (lambda r: r["conflicts"][0].update(finding_ids=["R2"]), "needs >=2"),
    (lambda r: r["not_found"][0].update(queries_tried=[]), "queries_tried"),
    (lambda r: r.pop("conflicts"), "missing top-level conflicts"),
])
def test_validator_rejects(mutate, expect):
    r = copy.deepcopy(GOOD)
    mutate(r)
    errs = research.validate(r)
    assert any(expect in e for e in errs), errs


def test_claim_ref_must_be_known_when_ids_given():
    r = copy.deepcopy(GOOD)
    r["findings"][0]["claim_ref"] = "deck.nope"
    assert any("claim_ref" in e for e in research.validate(r, {"deck.comp"}))
    r["findings"][0]["claim_ref"] = "deck.comp"
    assert research.validate(r, {"deck.comp"}) == []


CACHED = sorted(p.stem for p in research.DIR.glob("*.json")) if research.DIR.exists() else []


@pytest.mark.skipif(not CACHED, reason="no research cache")
@pytest.mark.parametrize("name", CACHED)
def test_cached_research_is_valid(name):
    assert research.validate_file(name) == []
