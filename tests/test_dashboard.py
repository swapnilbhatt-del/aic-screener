"""Dashboard: untrusted text cannot become markup; every company has the required panels."""
import json
import re

import pytest

from aic import dashboard

EVIL = '</script><script>alert(1)</script><img src=x onerror=alert(2)> '


def fake():
    return {"generated": "t", "config_version": "v", "thresholds": {"call": 70, "pass": 55}, "groups": {},
            "companies": [{"company": "X", "one_liner": EVIL, "criteria": [{"rationale": EVIL}]}],
            "backtest": None, "reports": []}


def test_untrusted_text_cannot_break_out_of_the_data_block():
    html = dashboard.render(fake())
    assert html.count("</script") == 2                       # only our own two closing tags
    assert "<script>alert" not in html and "<img src=x" not in html
    block = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1)
    assert json.loads(block)["companies"][0]["one_liner"] == EVIL   # data survives intact, as data


def test_template_renders_text_only_and_blocks_network():
    t = dashboard.TEMPLATE
    assert "innerHTML" not in t and "outerHTML" not in t and "insertAdjacentHTML" not in t and "eval(" not in t
    assert "default-src 'none'" in t                          # no external requests
    assert 'protocol==="https:"||x.protocol==="http:"' in t     # only http(s) links are created
    assert 'rel="noopener noreferrer"' in t or 'a.rel="noopener noreferrer"' in t


def test_pdf_link():
    assert dashboard.pdf_link("Pumpwise/deck p6 (slide 7)") == "../seed/applications/Pumpwise/deck.pdf#page=6"
    assert dashboard.pdf_link("https://x.org") == ""


@pytest.mark.skipif(not (dashboard.DATA / "scores" / "Pumpwise.json").exists(), reason="no scores")
def test_every_company_has_all_panels():
    d = dashboard.collect()
    assert len(d["companies"]) == 10
    for c in d["companies"]:
        assert len(c["criteria"]) == 12 and c["gates"] and c["band"] in ("call", "partner_review", "hold", "pass")
        assert set(c["history"]) == {"outcomes", "corrections", "outbox", "holds", "replies"}
        assert c["history"]["outcomes"], c["company"]
        assert c["checks_total"] > 0 and isinstance(c["discrepancies"], list)
        for cr in c["criteria"]:
            for e in cr["evidence"]:
                assert e["cite"] or e["url"], (c["company"], cr["id"])


@pytest.mark.skipif(not (dashboard.DATA / "scores" / "Pumpwise.json").exists(), reason="no scores")
def test_publish_variant_follows_page_contract():
    html = dashboard.render(dashboard.collect(), publish=True)
    head = html[:8192]
    assert "<title>AIC Screener</title>" in head
    for bad in ("<!doctype", "<html", "<head>", "<body>", "</body>", "Content-Security-Policy", 'id="theme"',
                "localStorage", ".pdf#page"):
        assert bad not in html, bad
    assert ':root:not([data-theme="light"])' in html and ':root[data-theme="dark"]' in html
    assert "max(16px,env(safe-area-inset-left,0px))" in html
    assert html.count("</script") == 2


@pytest.mark.skipif(not (dashboard.DATA / "scores" / "Pumpwise.json").exists(), reason="no scores")
def test_publish_variant_has_no_backtest():
    html = dashboard.render(dashboard.collect(), publish=True)
    d = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1))
    assert d["backtest"] is None
    # Passed memo companies and the decisions appear only in the backtest. (Invested ones such as Wint, Giva,
    # SuperK, Jai Kisan may appear via the fund's public portfolio in research; that is public information.)
    for name in ("Petalry", "HopBox", "CampusCredit", "AeroDrop", "Coinlane", "Prepnest", "INVESTED", "PASSED"):
        assert name not in html, name
