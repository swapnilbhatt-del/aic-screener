"""Deterministic conversion of Indian-format amounts and counts. Values are computed here, never by a model."""
import re
from typing import Optional

LAKH = 1e5
CRORE = 1e7
LAKH_CRORE = 1e12

_NUM = r"(\d+(?:,\d{2,3})*(?:\.\d+)?)"

# Order matters: longest unit phrases first.
_INR_UNITS = [
    (r"lakh\s*crores?|lakh\s*cr|l\s*cr", LAKH_CRORE),
    (r"crores?|cr", CRORE),
    (r"lakhs?|lac|l", LAKH),
    (r"k|thousand", 1e3),
    (r"m|mn|million", 1e6),
    (r"", 1.0),
]
_COUNT_UNITS = [(r"m|mn|million", 1e6), (r"k|thousand", 1e3), (r"lakh", LAKH), (r"crore|cr", CRORE), (r"", 1.0)]


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def parse_inr(text: str) -> Optional[float]:
    """'INR 1.4 lakh Cr' -> 1.4e12; 'INR 9.8 L' -> 9.8e5; 'INR 78,000' -> 78000; '₹2 Cr' -> 2e7.
    Returns None if no amount is found. Only the first amount in the text is parsed."""
    t = text.replace("₹", "INR ").strip()
    for unit_re, mult in _INR_UNITS:
        pat = rf"(?:INR|Rs\.?)\s*~?\s*{_NUM}\s*(?:{unit_re})\b" if unit_re else rf"(?:INR|Rs\.?)\s*~?\s*{_NUM}(?![\d.,]*\s*(?:lakh|crore|cr|l|k|m)\b)"
        m = re.search(pat, t, re.I)
        if m:
            return _num(m.group(1)) * mult
    return None


def parse_count(text: str) -> Optional[float]:
    """'190M' -> 1.9e8; '~84K' -> 84000; '2.1M' -> 2.1e6; '1,600' -> 1600; '9 lakh' -> 9e5."""
    for unit_re, mult in _COUNT_UNITS:
        pat = rf"~?\s*{_NUM}\s*(?:{unit_re})\b" if unit_re else rf"~?\s*{_NUM}"
        m = re.search(pat, text, re.I)
        if m:
            return _num(m.group(1)) * mult
    return None


def parse_percent(text: str) -> Optional[float]:
    m = re.search(rf"{_NUM}\s*%", text)
    return _num(m.group(1)) / 100 if m else None


def fmt_inr(x: float) -> str:
    """Human-readable INR in Indian units."""
    if x >= LAKH_CRORE:
        return f"INR {x / LAKH_CRORE:,.2f} lakh Cr"
    if x >= CRORE:
        return f"INR {x / CRORE:,.2f} Cr"
    if x >= LAKH:
        return f"INR {x / LAKH:,.2f} L"
    return f"INR {x:,.0f}"
