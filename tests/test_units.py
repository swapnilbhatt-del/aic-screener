import pytest

from aic.units import parse_inr, parse_count, parse_percent, fmt_inr


@pytest.mark.parametrize("s,expected", [
    ("INR 1.4 lakh Cr", 1.4e12),
    ("INR 9.4 lakh Cr", 9.4e12),
    ("INR 17 lakh Cr", 17e12),
    ("INR 9.8 L", 9.8e5),
    ("INR 9.4 L annualised", 9.4e5),
    ("INR 78,000", 78000),
    ("INR 2 Cr", 2e7),
    ("INR 6,750 Cr", 6.75e10),
    ("INR 91,200 Cr", 9.12e11),
    ("GMV of about INR 9 lakh in the last three months", 9e5),
    ("INR 25 lakh in total", 25e5),
    ("About INR 85,000 outstanding", 85000),
    ("INR 48K a month", 48000),
    ("₹2 Cr", 2e7),
    ("INR 1.2 L monthly purchases", 1.2e5),
    ("INR 14,500", 14500),
    ("INR 2,400 a year", 2400),
])
def test_parse_inr(s, expected):
    assert parse_inr(s) == pytest.approx(expected)


def test_parse_inr_none():
    assert parse_inr("no amount here") is None


@pytest.mark.parametrize("s,expected", [
    ("190M Indian households", 190e6), ("~84K firms", 84000), ("2.1M B2B-trading SMEs", 2.1e6),
    ("1,600 workers", 1600), ("~300K manufacturing MSMEs", 300e3), ("12M kirana stores", 12e6),
    ("45,000 seats", 45000), ("9 lakh", 9e5),
])
def test_parse_count(s, expected):
    assert parse_count(s) == pytest.approx(expected)


def test_parse_percent():
    assert parse_percent("Gross margin 48% after COGS") == pytest.approx(0.48)
    assert parse_percent("1.8% fee") == pytest.approx(0.018)


def test_fmt_inr():
    assert fmt_inr(1.14e12) == "INR 1.14 lakh Cr"
    assert fmt_inr(3.5e8) == "INR 35.00 Cr"
    assert fmt_inr(9.8e5) == "INR 9.80 L"
