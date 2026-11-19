"""Stage 2: deterministic checks. python -m aic.checks

Every check records stated vs recomputed values, each input with its citation, and a status:
  PASS / FAIL        numeric comparison within config tolerance (or a bound for '<', 'under', '+')
  FAIL (curated)     text contradiction chosen by the analyst; the quotes are shown, a human confirms
  UNCHECKABLE        an input the formula needs is not disclosed (recorded, never imputed)
Kinds: formula (deck's own arithmetic), cross_document (deck vs form), assumption_vs_observed
(a market/plan assumption vs the company's own observed data), internal (other self-consistency).
"""
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from . import config, text

ROOT = Path(__file__).resolve().parent.parent
CLAIMS = ROOT / "data" / "claims"
OUT = ROOT / "data" / "checks"

COMPANIES = ["CAPilot", "CareCorner", "EarnWise", "GrainKind", "Pumpwise",
             "RentRoute", "Settlr", "StockSathi", "Talkbook", "Yatrika"]

# Market sizes that measure throughput rather than revenue (user default, 2026-11-19).
VOLUME_MARKETS = {"Settlr"}

# metric -> material field (config.integrity_cap.material_fields)
MATERIAL = {
    **{m: "traction" for m in ("customers_paying", "customers_onboarded", "customers_live", "customers_trial",
                                "customers_pilot", "customers_repeat", "users_registered", "users_paying",
                                "seats_paid", "units_live", "transactions_count", "gmv_month_inr",
                                "volume_month_inr", "volume_cumulative_inr")},
    **{m: "revenue" for m in ("mrr_inr", "arr_inr", "revenue_month_inr", "revenue_gross_inr", "revenue_net_inr",
                               "revenue_cumulative_inr")},
    "team_size": "team", "founder_credential": "credentials",
    "raise_inr": "raise", "valuation_post_inr": "raise",
}
CROSS_METRICS = list(MATERIAL) + ["cac_inr", "payback_months", "gross_margin_pct", "ltv_cac", "nrr_pct",
                                  "arpu_month_inr", "repeat_rate_pct", "contribution_margin_pct"]
CROSS_METRICS.remove("founder_credential")
# A figure given in one document but stated without a number in the other is itself a discrepancy.
ONE_DOC_IS_FAIL = {"raise_inr"}

BOUND_UPPER = re.compile(r"^\s*(<|under|less than|below)", re.I)
BOUND_LOWER = re.compile(r"(\+|over|more than|at least)\s*$|^\s*(>|over|more than)", re.I)


class MissingInput(LookupError):
    pass


@dataclass
class Input:
    label: str
    value: Optional[float]
    as_written: str = ""
    cite: str = ""
    quote: str = ""
    claim_id: str = ""

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items() if v not in ("", None) or k == "value"}


def const(label: str, value: float, why: str) -> Input:
    return Input(label=label, value=value, as_written=str(value), cite=f"constant: {why}")


class Ctx:
    def __init__(self, company: str):
        self.company = company
        self.claims = json.loads((CLAIMS / f"{company}.json").read_text())["claims"]

    def find(self, metric=None, doc=None, contains=None, entity=None, page=None, numeric=True) -> List[dict]:
        out = []
        for c in self.claims:
            if not c.get("valid"):
                continue
            if metric and c["metric"] != metric:
                continue
            if doc and c["doc"] != doc:
                continue
            if page and c["page"] != page:
                continue
            if contains and text.squash(contains) not in text.squash(c["as_written"]):
                continue
            if entity and text.squash(entity) not in text.squash(c.get("entity") or ""):
                continue
            if numeric and c.get("value") is None:
                continue
            out.append(c)
        return out

    def get(self, label, metric=None, doc=None, contains=None, entity=None, page=None, aw=None) -> Input:
        cands = self.find(metric, doc, contains, entity, page)
        if aw is not None:
            cands = [c for c in cands if text.squash(aw) == text.squash(c["as_written"])]
        if not cands:
            raise MissingInput(f"{label}: no claim (metric={metric}, doc={doc}, contains={contains}, aw={aw})")
        c = cands[0]
        return Input(label=label, value=c["value"], as_written=c["as_written"], cite=c.get("cite", ""),
                     quote=c["quote"], claim_id=c["id"])

    def qualifier(self, inp: Input) -> str:
        c = next((c for c in self.claims if c["id"] == inp.claim_id), {})
        return " ".join(x for x in (c.get("qualifier") or "", inp.as_written) if x)


@dataclass
class Check:
    company: str
    id: str
    kind: str
    label: str
    status: str
    stated: Optional[Input] = None
    recomputed: Optional[float] = None
    inputs: List[Input] = field(default_factory=list)
    formula: str = ""
    diff_pct: Optional[float] = None
    direction: str = ""
    bound: str = ""
    within_stated_precision: Optional[bool] = None
    material_field: Optional[str] = None
    curated: bool = False
    note: str = ""

    def as_dict(self):
        d = dict(self.__dict__)
        d["stated"] = self.stated.as_dict() if self.stated else None
        d["inputs"] = [i.as_dict() for i in self.inputs]
        return d


def _decimals(s: str) -> int:
    m = re.search(r"\d+(?:,\d+)*(?:\.(\d+))?", s)
    return len(m.group(1)) if m and m.group(1) else 0


def compare(stated: float, recomputed: float, tol: float, bound: str = "") -> dict:
    """bound: '' (equality within tol), 'upper' (stated is a ceiling, e.g. '< 4 months'), 'lower' ('40,000+')."""
    if bound == "upper":
        return {"status": "PASS" if recomputed < stated else "FAIL", "diff_pct": None,
                "direction": "" if recomputed < stated else "exceeds stated ceiling"}
    if bound == "lower":
        return {"status": "PASS" if recomputed >= stated else "FAIL", "diff_pct": None,
                "direction": "" if recomputed >= stated else "below stated floor"}
    if stated == 0:
        diff = math.inf if recomputed else 0.0
    else:
        diff = (recomputed - stated) / abs(stated)
    status = "PASS" if abs(diff) <= tol + 1e-12 else "FAIL"
    direction = ""
    if status == "FAIL":
        ratio = stated / recomputed if recomputed else math.inf
        if ratio == 0:
            direction = "stated is zero; recomputed is not"
        elif ratio >= 1:
            direction = f"stated is {ratio:.2f}x the recomputed value"
        else:
            direction = f"stated is {1 / ratio:.2f}x lower than the recomputed value"
    return {"status": status, "diff_pct": round(diff * 100, 2), "direction": direction}


def bound_of(ctx: Ctx, inp: Input) -> str:
    q = ctx.qualifier(inp)
    if BOUND_UPPER.search(q) or BOUND_UPPER.search(inp.as_written):
        return "upper"
    if BOUND_LOWER.search(inp.as_written):
        return "lower"
    return ""


class Runner:
    def __init__(self, company: str, tol: float):
        self.ctx = Ctx(company)
        self.company = company
        self.tol = tol
        self.checks: List[Check] = []

    def formula(self, id, label, kind, stated: Callable[[], Input], inputs: Callable[[], Sequence[Input]],
                fn: Callable[..., float], formula: str, note: str = "", bound: Optional[str] = None):
        try:
            s = stated()
            ins = list(inputs())
        except MissingInput as e:
            self.checks.append(Check(self.company, id, kind, label, "UNCHECKABLE", note=f"{e}. {note}".strip()))
            return
        if any(i.value is None for i in ins) or s.value is None:
            self.checks.append(Check(self.company, id, kind, label, "UNCHECKABLE", stated=s, inputs=ins,
                                     formula=formula, note=f"an input has no number. {note}".strip()))
            return
        r = float(fn(*[i.value for i in ins]))
        b = bound if bound is not None else bound_of(self.ctx, s)
        cmp = compare(s.value, r, self.tol, b)
        prec = None
        if not b:
            d = _decimals(s.as_written)
            scale = s.value / float(re.sub(r"[^\d.]", "", re.search(r"\d+(?:,\d+)*(?:\.\d+)?", s.as_written).group(0)))
            prec = round(r / scale, d) == round(s.value / scale, d) if scale else None
        self.checks.append(Check(self.company, id, kind, label, cmp["status"], stated=s, recomputed=round(r, 4),
                                 inputs=ins, formula=formula, diff_pct=cmp["diff_pct"], direction=cmp["direction"],
                                 bound=b, within_stated_precision=prec, note=note))

    def curated(self, id, label, a: Callable[[], Input], b: Callable[[], Input], verdict: str, note: str,
                material_field: Optional[str] = None, kind="cross_document"):
        try:
            ia, ib = a(), b()
        except MissingInput as e:
            self.checks.append(Check(self.company, id, kind, label, "UNCHECKABLE", note=str(e)))
            return
        self.checks.append(Check(self.company, id, kind, label, verdict, inputs=[ia, ib], curated=True,
                                 material_field=material_field, note=note))

    # ---- generic checks -------------------------------------------------
    def market_formulas(self):
        for c in self.ctx.claims:
            if c["metric"] not in ("market_tam_inr", "market_sam_inr", "market_som_inr", "market_share_claim"):
                continue
            comps = c.get("components") or []
            if len(comps) < 2:
                continue
            tag = c["metric"].split("_")[1].upper() if c["metric"] != "market_share_claim" else "share"
            basis = "volume" if self.company in VOLUME_MARKETS else "revenue"
            ins = [Input(label=x.get("label") or x["as_written"], value=x["value"], as_written=x["as_written"],
                         cite=c.get("cite", ""), quote=c["quote"], claim_id=c["id"]) for x in comps]
            stated = Input(label=f"{tag} as stated", value=c["value"], as_written=c["as_written"],
                           cite=c.get("cite", ""), quote=c["quote"], claim_id=c["id"])
            self.formula(f"market.{tag.lower()}", f"{tag} ({basis} basis): product of stated inputs", "formula",
                         lambda s=stated: s, lambda i=ins: i, lambda *v: math.prod(v),
                         " x ".join(i.as_written for i in ins))

    def cross_documents(self):
        for m in CROSS_METRICS:
            deck = self.ctx.find(m, "deck")
            form = self.ctx.find(m, "form")
            deck_txt = self.ctx.find(m, "deck", numeric=False)
            form_txt = self.ctx.find(m, "form", numeric=False)
            if not deck and not form:
                continue
            mf = MATERIAL.get(m)
            if m in ONE_DOC_IS_FAIL and ((deck and not form and form_txt) or (form and not deck and deck_txt)):
                have, lack = (deck, form_txt) if deck else (form, deck_txt)
                self.checks.append(Check(
                    self.company, f"xdoc.{m}", "cross_document", f"{m}: one document gives no figure", "FAIL",
                    inputs=[self._inp(have[0]), self._inp(lack[0])], material_field=None,
                    note=f"omission, not a contradiction: {lack[0]['doc']} states it without a number"))
                continue
            if not deck or not form:
                continue
            # Compare headline values: the largest figure each document gives for the metric.
            d = max(deck, key=lambda c: c["value"])
            f = max(form, key=lambda c: c["value"])
            di, fi = self._inp(d), self._inp(f)
            bf, bd = bound_of(self.ctx, fi), bound_of(self.ctx, di)
            if bf:
                cmp = compare(fi.value, di.value, self.tol, bf)
                stated, other = fi, di
            elif bd:
                cmp = compare(di.value, fi.value, self.tol, bd)
                stated, other = di, fi
            else:
                cmp = compare(di.value, fi.value, self.tol)
                stated, other = di, fi
                if cmp["status"] == "FAIL":
                    cmp["direction"] = f"deck {di.as_written} vs form {fi.as_written}"
            self.checks.append(Check(self.company, f"xdoc.{m}", "cross_document", f"{m}: deck vs form",
                                     cmp["status"], stated=stated, recomputed=other.value, inputs=[di, fi],
                                     formula="headline (largest) value in each document", diff_pct=cmp["diff_pct"],
                                     direction=cmp["direction"], bound=bf or bd, material_field=mf))

    def credentials(self):
        cl = [c for c in self.ctx.claims if c["metric"] == "founder_credential" and c.get("valid")]
        founders = sorted({c.get("entity") for c in cl if c.get("entity")})
        for f in founders:
            deck = [c for c in cl if c["entity"] == f and c["doc"] == "deck"]
            form = [c for c in cl if c["entity"] == f and c["doc"] == "form"]
            if not deck or not form:
                self.checks.append(Check(self.company, f"xdoc.credentials.{_slug(f)}", "cross_document",
                                         f"credentials of founder {_initials(f)}: only in one document",
                                         "UNCHECKABLE", material_field="credentials"))
                continue
            dt, ft = " ".join(c["as_written"] for c in deck), " ".join(c["as_written"] for c in form)
            miss_d = sorted(t for t in credential_tokens(dt) if not _token_in(t, ft))
            miss_f = sorted(t for t in credential_tokens(ft) if not _token_in(t, dt))
            status = "FAIL" if (miss_d or miss_f) else "PASS"
            self.checks.append(Check(
                self.company, f"xdoc.credentials.{_slug(f)}", "cross_document",
                f"credentials of founder {_initials(f)}: named institutions and durations agree", status,
                inputs=[self._inp(c) for c in deck + form], material_field="credentials",
                note=(f"in deck, not form: {miss_d}; in form, not deck: {miss_f}" if status == "FAIL" else "")))

    def _inp(self, c: dict) -> Input:
        return Input(label=f"{c['doc']}: {c.get('label') or c['metric']}", value=c.get("value"),
                     as_written=c["as_written"], cite=c.get("cite", ""), quote=c["quote"], claim_id=c["id"])


# ---- credential tokens --------------------------------------------------
STOP = {"Ex", "Qualified", "Trained", "Designed", "Designs", "Built", "Runs", "Ran", "Led", "Launched", "Product",
        "Summer", "Software", "Food", "Team", "Founder", "Co", "Background", "Head", "Senior", "Former", "Worked",
        "Years", "In", "At", "As", "The", "A", "An"}
ALIASES = {"CA": ["chartered accountant"], "IIM": ["iim", "indian institute of management"],
           "IIT": ["iit", "indian institute of technology"]}
DURATION = re.compile(r"(\d+)[\s-]*(years?|months?|weeks?)", re.I)


NORMALISE = [(re.compile(r"chartered accountant", re.I), "CA")]


def credential_tokens(s: str) -> set:
    s2 = re.sub(r"linkedin\.com/\S+", "", s)
    for pat, rep in NORMALISE:
        s2 = pat.sub(rep, s2)
    toks = set()
    for w in re.findall(r"[A-Z][A-Za-z&]+", s2.replace("Ex-", "")):
        if w not in STOP:
            toks.add(w)
    for n, u in DURATION.findall(s2):
        toks.add(f"{n} {u.rstrip('s').lower()}")
    return toks


def _token_in(tok: str, other: str) -> bool:
    o = text.squash(other)
    if " " in tok and re.match(r"\d+ ", tok):  # duration
        n, u = tok.split()
        return any(int(a) == int(n) and b.lower().startswith(u) for a, b in DURATION.findall(other))
    for pat, rep in NORMALISE:
        o = text.squash(pat.sub(rep, other))
    if text.squash(tok) in o:
        return True
    return any(text.squash(a) in o for a in ALIASES.get(tok, []))


def _slug(s):
    return re.sub(r"\W+", "_", s.lower()).strip("_")


def _initials(s):
    return "".join(w[0] for w in re.sub(r"^(Dr\.?\s+)", "", s).split() if w)


# ---- company-specific specs -----------------------------------------------
def specs(r: Runner):
    g, co = r.ctx.get, r.company
    F, X, A, I = "formula", "cross_document", "assumption_vs_observed", "internal"

    if co == "CAPilot":
        r.formula("arr_from_mrr", "ARR = form MRR x 12", F, lambda: g("ARR", "arr_inr", "deck"),
                  lambda: [g("MRR", "mrr_inr", "form"), const("months", 12, "annualisation")],
                  lambda m, k: m * k, "MRR x 12")
        r.formula("chart_oct_vs_mrr", "Deck chart Oct point = form MRR", I, lambda: g("MRR", "mrr_inr", "form"),
                  lambda: [g("chart Oct", "time_series", "deck", entity="Oct")], lambda x: x, "chart Oct")
        r.formula("deck_paying_eq_form_paying_plus_trial",
                  "Deck '31 paying' equals form paying + free trial (i.e. trials counted as paying)", X,
                  lambda: g("deck paying", "customers_paying", "deck"),
                  lambda: [g("form paying", "customers_paying", "form"), g("form trial", "customers_trial", "form")],
                  lambda p, t: p + t, "form paying + form trial",
                  note="PASS here means the deck figure reconciles only if free-trial firms are counted as paying.")
        r.formula("arpu_in_price_band_low", "Implied MRR per paying firm >= lowest plan price", I,
                  lambda: g("lowest plan", "price_inr", "deck", aw="INR 2,500"),
                  lambda: [g("MRR", "mrr_inr", "form"), g("form paying", "customers_paying", "form")],
                  lambda m, p: m / p, "MRR / form paying firms", bound="lower")

    if co == "CareCorner":
        r.formula("clinic_runrate_vs_maturity", "Observed annual revenue per clinic vs INR 1.4 Cr maturity used in SOM", A,
                  lambda: g("maturity revenue per clinic", "market_som_inr", "deck").__class__(
                      label="maturity revenue per clinic", value=1.4e7, as_written="INR 1.4 Cr",
                      cite=g("som", "market_som_inr", "deck").cite, quote=g("som", "market_som_inr", "deck").quote),
                  lambda: [g("Oct revenue (3 clinics)", "revenue_month_inr", "form"),
                           g("clinics open", "units_live", "deck"), const("months", 12, "annualisation")],
                  lambda rev, n, k: rev / n * k, "Oct revenue / clinics x 12",
                  note="The deck labels INR 1.4 Cr as revenue 'at maturity'; the gap is the ramp the SOM assumes.")
        r.formula("use_of_funds_clinics", "47% of raise covers 5 clinics at stated capex", I,
                  lambda: g("capex per clinic", "capex_inr", "deck"),
                  lambda: [g("raise", "raise_inr", "deck"), g("47% to new clinics", "use_of_funds_pct", "deck",
                                                              contains="47%"), const("new clinics", 5, "deck: 'Five new clinics'")],
                  lambda raise_, pct, n: raise_ * pct / n, "raise x 47% / 5")
        r.formula("channel_mix_sum", "Patient channel mix sums to 100%", I, lambda: const("100%", 1.0, "total"),
                  lambda: [g(c, "channel_mix_pct", "deck", entity=c) for c in ("Local doctor", "WhatsApp", "Health camps")],
                  lambda *v: sum(v), "sum of channel shares")

    if co == "EarnWise":
        r.formula("chart_sum", "Monthly advances chart sums to INR 38 L", I,
                  lambda: g("advances disbursed", "volume_cumulative_inr", "deck"),
                  lambda: [g(m, "time_series", "deck", entity=m) for m in ("Jul", "Aug", "Sep", "Oct")],
                  lambda *v: sum(v), "Jul + Aug + Sep + Oct")
        r.formula("advance_per_worker_vs_tam", "Observed advance per enabled worker per month vs TAM's INR 12,000", A,
                  lambda: g("TAM monthly advance", "market_tam_inr", "deck").__class__(
                      label="TAM average monthly advance", value=12000, as_written="INR 12,000",
                      cite=g("t", "market_tam_inr", "deck").cite, quote=g("t", "market_tam_inr", "deck").quote),
                  lambda: [g("advances", "volume_cumulative_inr", "form"), g("workers", "users_registered", "form"),
                           const("months", 4, "Jul-Oct 2026, deck chart")],
                  lambda adv, w, m: adv / w / m, "INR 38 L / 1,600 workers / 4 months",
                  note="Uses all enabled workers; per active borrower is not disclosed.")

    if co == "GrainKind":
        r.formula("blended_cac_from_channels", "Blended CAC = channel mix x channel CAC", I,
                  lambda: g("blended CAC", "cac_inr", "deck"),
                  lambda: [g("paid social share", "channel_mix_pct", "form", entity="Paid social"),
                           g("paid social CAC", "cac_channel_inr", "form", entity="Paid social"),
                           g("quick commerce share", "channel_mix_pct", "form", entity="Quick commerce", contains="25%"),
                           g("quick commerce CAC", "cac_channel_inr", "form", entity="Quick commerce"),
                           g("nutritionist share", "channel_mix_pct", "form", entity="Nutritionist"),
                           g("nutritionist CAC", "cac_channel_inr", "form", entity="Nutritionist"),
                           g("sampling share", "channel_mix_pct", "form", entity="Gyms"),
                           g("sampling CAC", "cac_channel_inr", "form", entity="Gyms")],
                  lambda a, b, c, d, e, f, h, i: a * b + c * d + e * f + h * i, "sum(share x CAC)")
        r.formula("som_spend_vs_tam_spend", "SOM spend per household equals TAM/SAM spend", I,
                  lambda: g("TAM spend", "market_tam_inr", "deck").__class__(
                      label="TAM/SAM spend per household", value=2400, as_written="INR 2,400",
                      cite=g("t", "market_tam_inr", "deck").cite, quote=g("t", "market_tam_inr", "deck").quote),
                  lambda: [g("SOM spend", "market_som_inr", "deck").__class__(
                      label="SOM spend per household", value=3200, as_written="INR 3,200",
                      cite=g("s", "market_som_inr", "deck").cite, quote=g("s", "market_som_inr", "deck").quote)],
                  lambda x: x, "SOM spend",
                  note="Same households, different annual spend: the SOM uses a higher spend than the TAM and SAM.")
        r.formula("som_households", "1.5% of 6M SAM households = 90,000", I,
                  lambda: g("SOM households", "market_som_inr", "deck").__class__(
                      label="SOM households", value=90000, as_written="90,000",
                      cite=g("s", "market_som_inr", "deck").cite, quote=g("s", "market_som_inr", "deck").quote),
                  lambda: [const("share of SAM", 0.015, "deck: 1.5% of SAM households"), const("SAM households", 6e6, "deck: 6M")],
                  lambda a, b: a * b, "1.5% x 6M")
        r.formula("sku_share_sum", "Three hero SKUs = 87% of orders (form)", I,
                  lambda: const("form: 87% of orders", 0.87, "form p1: 'Three hero SKUs account for 87% of orders'"),
                  lambda: [const("Ragi choco crunch", 0.42, "deck p3"), const("Millet muesli", 0.28, "deck p3"),
                           const("Jowar puffs", 0.17, "deck p3")], lambda *v: sum(v), "42% + 28% + 17%")
        r.formula("ltv_cac", "12-month LTV/CAC 1.8x reproducible from disclosed inputs", I,
                  lambda: g("LTV/CAC", "ltv_cac", "deck"), lambda: [g("12-month orders per customer", "other",
                                                                       contains="12-month orders")],
                  lambda x: x, "", note="12-month orders per customer and LTV method are not disclosed.")

    if co == "Pumpwise":
        r.formula("tam_at_observed_sensors", "TAM at observed 23 sensors/customer vs stated (60 assumed)", A,
                  lambda: g("TAM", "market_tam_inr", "deck"),
                  lambda: [const("MSMEs", 300e3, "deck p6 TAM input"), g("observed sensors per customer", contains="23 sensors"),
                           const("annual subscription", 9000, "deck p6 TAM input")],
                  lambda n, s, p: n * s * p, "300K x 23 x INR 9,000")
        r.formula("annual_sub_eq_monthly", "INR 9,000/yr = INR 750/month x 12", I,
                  lambda: const("TAM price per sensor per year", 9000, "deck p6"),
                  lambda: [g("subscription per sensor per month", "price_inr", "deck", aw="INR 750"), const("months", 12, "")],
                  lambda p, k: p * k, "750 x 12")
        r.formula("msme_base", "~300K = 12% of ~2.5M Udyam manufacturing MSMEs", I,
                  lambda: const("TAM firms", 300e3, "deck p6"),
                  lambda: [const("share", 0.12, "deck p6 footnote"), const("Udyam manufacturing MSMEs", 2.5e6, "deck p6 footnote")],
                  lambda a, b: a * b, "12% x 2.5M")
        r.formula("mrr_from_sensors", "MRR = sensors live x INR 750", I, lambda: g("MRR", "mrr_inr", "deck"),
                  lambda: [g("sensors live", "units_live", "deck"), g("price", "price_inr", "deck", aw="INR 750")],
                  lambda n, p: n * p, "140 x 750")
        r.formula("hardware_revenue", "Hardware revenue = sensors x INR 9,500", I,
                  lambda: g("hardware revenue", "revenue_cumulative_inr", "form", entity="hardware"),
                  lambda: [g("sensors live", "units_live", "form"), g("hardware price", "price_inr", "deck", aw="INR 9,500")],
                  lambda n, p: n * p, "140 x 9,500")
        r.formula("avg_sensors", "Average 23 sensors per customer = 140 / 6", I,
                  lambda: g("avg sensors", contains="23 sensors"),
                  lambda: [g("sensors live", "units_live", "deck"), g("paid customers", "customers_paying", "form")],
                  lambda n, c: n / c, "140 / 6")
        r.formula("pilot_conversion", "Pilot-to-paid 55% = 6 / 11", I, lambda: g("pilot to paid", "pilot_to_paid_pct", "deck"),
                  lambda: [g("paid", "customers_paying", "form"), g("pilots", "customers_pilot", "form")],
                  lambda p, n: p / n, "6 / 11")
        r.formula("cac", "CAC = pilot cost / paid customers", I, lambda: g("CAC", "cac_inr", "deck", aw="INR 73,000"),
                  lambda: [g("pilot cost", "cac_inr", "deck", aw="INR 4.4 L"), g("paid", "customers_paying", "form")],
                  lambda c, n: c / n, "INR 4.4 L / 6", note="Excludes founder time (form).")
        r.formula("first_year_gp", "First-year gross profit per average customer", I,
                  lambda: g("first-year GP", contains="3.1 L"),
                  lambda: [const("sensors", 23, "deck p8 average"), g("hardware price", "price_inr", "deck", aw="INR 9,500"),
                           const("hardware cost", 3200, "deck p8 'Cost to us: INR 3,200'"),
                           g("subscription", "price_inr", "deck", aw="INR 750"), g("sub margin", "gross_margin_pct", "deck")],
                  lambda s, hp, hc, sp, gm: s * (hp - hc) + s * sp * 12 * gm, "23 x (9,500 - 3,200) + 23 x 750 x 12 x 85%")
        r.formula("payback", "Payback < 4 months on first-year gross profit", I,
                  lambda: g("payback", "payback_months", "deck"),
                  lambda: [g("CAC", "cac_inr", "deck", aw="INR 73,000"), g("first-year GP", contains="3.1 L")],
                  lambda c, gp: c / (gp / 12), "CAC / (first-year GP / 12)")
        r.formula("chart_oct", "Chart Oct = 140 sensors live", I, lambda: g("sensors live", "units_live", "deck"),
                  lambda: [g("chart Oct", "time_series", "deck", entity="Oct")], lambda x: x, "chart Oct")

    if co == "RentRoute":
        r.formula("chart_sum", "Monthly rent chart sums to INR 6.1 Cr", I, lambda: g("rent paid", "volume_cumulative_inr", "deck"),
                  lambda: [g(m, "time_series", "deck", entity=m) for m in ("Jul", "Aug", "Sep", "Oct")],
                  lambda *v: sum(v), "Jul + Aug + Sep + Oct")
        r.formula("gross_fee", "Gross fee = 1.8% x INR 6.1 Cr", I, lambda: g("gross revenue", "revenue_gross_inr", "form"),
                  lambda: [g("fee", "take_rate_pct", "form"), g("volume", "volume_cumulative_inr", "form")],
                  lambda p, v: p * v, "1.8% x 6.1 Cr")
        r.formula("net_fee", "Net revenue = (1.8% - 0.9%) x INR 6.1 Cr", I, lambda: g("net revenue", "revenue_net_inr", "form"),
                  lambda: [g("fee", "take_rate_pct", "form"), g("partner cost", "partner_cost_pct", "form"),
                           g("volume", "volume_cumulative_inr", "form")],
                  lambda p, c, v: (p - c) * v, "(1.8% - 0.9%) x 6.1 Cr")
        r.curated("deck_revenue_basis", "Deck reports revenue gross only", lambda: g("deck revenue", "revenue_gross_inr", "deck"),
                  lambda: g("form net revenue", "revenue_net_inr", "form"), "FAIL",
                  "Deck shows INR 11 L 'revenue (1.8% fee)'; the form discloses that net revenue after the partner's 0.9% is INR 5.5 L. Omission, not a contradiction in figures: the deck omits the net basis.",
                  material_field=None)

    if co == "Settlr":
        r.formula("volume_per_sme_vs_tam", "Observed annual volume per SME vs TAM's INR 4.5 Cr", A,
                  lambda: g("TAM", "market_tam_inr", "deck").__class__(
                      label="TAM volume per SME", value=4.5e7, as_written="INR 4.5 Cr",
                      cite=g("t", "market_tam_inr", "deck").cite, quote=g("t", "market_tam_inr", "deck").quote),
                  lambda: [g("Oct volume", "volume_month_inr", "form"), const("months", 12, "annualisation"),
                           g("SMEs", "customers_live", "form")],
                  lambda v, k, n: v * k / n, "INR 86 Cr x 12 / 1,150")
        r.formula("arpu", "Fees per SME = net revenue / SMEs", I, lambda: g("ARPU", "arpu_month_inr", "deck"),
                  lambda: [g("net revenue Oct", "revenue_net_inr", "form"), g("SMEs", "customers_live", "form")],
                  lambda rev, n: rev / n, "INR 78 L / 1,150")
        r.formula("payback", "Payback = CAC / (monthly fees x gross margin)", I, lambda: g("payback", "payback_months", "deck"),
                  lambda: [g("CAC", "cac_inr", "deck"), g("ARPU", "arpu_month_inr", "deck"), g("GM", "gross_margin_pct", "deck")],
                  lambda c, a, m: c / (a * m), "14,500 / (6,800 x 58%)",
                  note="The deck's method is not stated; a shorter recomputed payback is not in the company's disfavour.")
        r.formula("chart_oct", "Chart Oct = INR 86 Cr", I, lambda: g("Oct volume", "volume_month_inr", "deck"),
                  lambda: [g("chart Oct", "time_series", "deck", entity="Oct")], lambda x: x, "chart Oct")

    if co == "StockSathi":
        r.formula("cac", "October CAC = INR 40,000 / 14 stores", I, lambda: g("CAC", "cac_inr", "deck"),
                  lambda: [g("field cost", "other", "deck", aw="INR 40,000"), g("Oct stores", "customers_onboarded", "deck", aw="14 stores")],
                  lambda c, n: c / n, "40,000 / 14")
        r.formula("payback", "Payback = CAC / monthly margin per store", I, lambda: g("payback", "payback_months", "deck"),
                  lambda: [g("CAC", "cac_inr", "deck"), g("margin", "margin_per_unit_month_inr", "deck")],
                  lambda c, m: c / m, "2,860 / 520")
        r.formula("channel_sum", "Acquisition channels sum to 38 stores", I, lambda: g("deck retailers", "customers_onboarded", "deck", aw="38 retailers"),
                  lambda: [g(c, "channel_mix_pct", "deck", entity=c) for c in ("Field agents", "Neighbour", "Distributor")],
                  lambda *v: sum(v), "24 + 9 + 5")
        r.formula("som_stores", "2% of 450K SAM stores = 9,000", I,
                  lambda: const("SOM stores", 9000, "deck p6"),
                  lambda: [const("share", 0.02, "deck p6"), const("SAM stores", 450e3, "deck p6")], lambda a, b: a * b, "2% x 450K")
        r.formula("som_spend", "40% of INR 1.2 L = INR 48K", I, lambda: const("SOM spend", 48000, "deck p6"),
                  lambda: [const("share", 0.4, "deck p6"), const("monthly purchases", 1.2e5, "deck p6")], lambda a, b: a * b, "40% x 1.2 L")
        r.curated("credit_funding", "Who funds the credit book: deck vs form",
                  lambda: Input(**_txt(r.ctx, "credit_funding", "deck", "own capital")),
                  lambda: Input(**_txt(r.ctx, "credit_funding", "form", "NBFC partner")),
                  "FAIL", "Deck: credit funded from own capital, NBFC partnership 'in discussion'. Form: credit provided through an NBFC partner, company takes first-loss risk, not registered as an NBFC.",
                  material_field=None)

    if co == "Talkbook":
        r.formula("mrr_seats_deck", "Deck MRR = 340 seats x INR 500", I, lambda: g("deck MRR", "mrr_inr", "deck"),
                  lambda: [g("seats", "seats_paid", "deck"), g("price", "price_inr", "deck", aw="INR 500")],
                  lambda s, p: s * p, "340 x 500")
        r.formula("mrr_seats_form", "Form MRR = 340 seats x INR 500", I, lambda: g("form MRR", "mrr_inr", "form"),
                  lambda: [g("seats", "seats_paid", "form"), g("price", "price_inr", "form", aw="INR 500")],
                  lambda s, p: s * p, "340 x 500")
        r.formula("arpu_from_seats", "Average team pays = seats x price / teams", I, lambda: g("ARPU", "arpu_month_inr", "deck"),
                  lambda: [g("seats", "seats_paid", "deck"), g("price", "price_inr", "deck", aw="INR 500"),
                           g("teams", "customers_paying", "deck")], lambda s, p, t: s * p / t, "340 x 500 / 16")
        r.formula("arpu_from_mrr", "Average team pays = deck MRR / teams", I, lambda: g("ARPU", "arpu_month_inr", "deck"),
                  lambda: [g("deck MRR", "mrr_inr", "deck"), g("teams", "customers_paying", "deck")],
                  lambda m, t: m / t, "2.1 L / 16")
        r.formula("payback", "Payback = CAC / (ARPU x gross margin)", I, lambda: g("payback", "payback_months", "deck"),
                  lambda: [g("CAC", "cac_inr", "deck"), g("ARPU", "arpu_month_inr", "deck"), g("GM", "gross_margin_pct", "deck")],
                  lambda c, a, m: c / (a * m), "48,000 / (13,000 x 70%)")
        r.formula("annual_price", "INR 6,000/seat/yr = INR 500 x 12", I, lambda: g("annual price", "price_inr", "deck", aw="INR 6,000"),
                  lambda: [g("price", "price_inr", "deck", aw="INR 500"), const("months", 12, "")], lambda p, k: p * k, "500 x 12")
        r.formula("channel_sum", "Channels sum to 16 teams", I, lambda: g("teams", "customers_paying", "deck"),
                  lambda: [g(c, "channel_mix_pct", "deck", entity=c) for c in ("Founder-led", "Customer referrals", "CRM consultants")],
                  lambda *v: sum(v), "9 + 5 + 2")
        r.formula("chart_oct", "Chart Oct = deck MRR", I, lambda: g("deck MRR", "mrr_inr", "deck"),
                  lambda: [g("chart Oct", "time_series", "deck", entity="Oct")], lambda x: x, "chart Oct")

    if co == "Yatrika":
        r.formula("revenue_commission", "Revenue = 12% of booking value", I, lambda: g("revenue", "revenue_cumulative_inr", "form"),
                  lambda: [g("commission", "take_rate_pct", "form"), g("booking value", "gmv_period_inr", "form")],
                  lambda p, v: p * v, "12% x 38.6 L")
        r.curated("travellers", "Travellers served: deck 'thousands' vs form ~1,300",
                  lambda: Input(**_txt(r.ctx, "users_registered", "deck", "thousands")),
                  lambda: g("form travellers", "users_paying", "form"), "FAIL",
                  "'Thousands' implies at least 2,000; the form gives about 1,300.", material_field="traction")


def _txt(ctx: Ctx, metric: str, doc: str, contains: str) -> dict:
    c = ctx.find(metric, doc, contains=contains, numeric=False)
    if not c:
        raise MissingInput(f"{metric} {doc} '{contains}'")
    c = c[0]
    return dict(label=f"{doc}: {c.get('label') or metric}", value=c.get("value"), as_written=c["as_written"],
                cite=c.get("cite", ""), quote=c["quote"], claim_id=c["id"])


def run(company: str) -> List[Check]:
    cfg = config.load()
    r = Runner(company, cfg["arithmetic"]["tolerance"])
    r.market_formulas()
    specs(r)
    r.cross_documents()
    r.credentials()
    return r.checks


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    allc = []
    for co in COMPANIES:
        cs = run(co)
        (OUT / f"{co}.json").write_text(json.dumps([c.as_dict() for c in cs], indent=1, ensure_ascii=False))
        allc += cs
    summary = {}
    for c in allc:
        s = summary.setdefault(c.company, {"PASS": 0, "FAIL": 0, "UNCHECKABLE": 0, "material_xdoc_fail": 0})
        s[c.status] += 1
        if c.status == "FAIL" and c.kind == "cross_document" and c.material_field:
            s["material_xdoc_fail"] += 1
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    return allc, summary


if __name__ == "__main__":
    allc, summary = main()
    for c in allc:
        st = c.stated.as_written if c.stated else ""
        print(f"{c.company:11} {c.status:11} {c.kind[:6]:6} {c.id:42} stated={st[:18]:18} recomputed={c.recomputed!s:14} "
              f"{c.direction[:45]} {'[curated]' if c.curated else ''}{' [' + c.material_field + ']' if c.material_field and c.status == 'FAIL' else ''}")
    print(json.dumps(summary, indent=1))
