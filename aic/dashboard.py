"""Local HTML dashboard: python -m aic.dashboard  ->  dashboard/index.html (gitignored; contains founder data).

One self-contained file: inline CSS/JS, no external requests. All document, research and reply text is
untrusted, so it is embedded as JSON (with '<' escaped) and rendered with textContent only. Links are
created only for http(s) URLs and for local source PDFs.
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config, db
from .ingest import COMPANIES

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboard" / "index.html"
DATA = ROOT / "data"


def _load(p: Path, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def _rows(conn, sql, args=()):
    conn.row_factory = sqlite3.Row
    r = [dict(x) for x in conn.execute(sql, args)]
    conn.row_factory = None
    return r


def pdf_link(cite: str) -> str:
    """'Pumpwise/deck p6 (slide 7)' -> '../seed/applications/Pumpwise/deck.pdf#page=6' (local file)."""
    m = re.match(r"^(\w+)/(deck|form) p(\d+)", cite or "")
    return f"../seed/applications/{m.group(1)}/{m.group(2)}.pdf#page={m.group(3)}" if m else ""


def _evidence(items):
    out = []
    for e in items or []:
        out.append({"ref": e.get("ref"), "point": e.get("point"), "quote": e.get("quote"), "type": e.get("type"),
                    "cite": e.get("cite"), "pdf": pdf_link(e.get("cite", "")), "url": e.get("url"),
                    "accessed": e.get("accessed_date"), "published": e.get("published_date"),
                    "confidence": e.get("confidence"), "status": e.get("status")})
    return out


def collect() -> dict:
    cfg = config.load()
    conn = db.connect()
    fund = _load(DATA / "research" / "_fund.json", {"overlaps": []})
    companies = []
    for co in COMPANIES:
        sc = _load(DATA / "scores" / f"{co}.json")
        if not sc:
            continue
        checks = _load(DATA / "checks" / f"{co}.json", [])
        res = _load(DATA / "research" / f"{co}.json", {"findings": [], "competitors": [], "conflicts": [], "not_found": []})
        app = _load(DATA / "applications" / f"{co}.json", {"form_fields": {}})
        ff = app["form_fields"]
        crit = []
        for k, c in sc["criteria"].items():
            adj = [a for a in sc["adjustments"] if a["criterion"] == k]
            crit.append({"id": k, "name": cfg["criteria"][k]["name"], "weight": c["weight"], "proposed": c["proposed"],
                         "final": c["final"], "points": c["points"], "unknown": c["unknown"],
                         "confidence": c["confidence"], "rationale": c["rationale"], "evidence": _evidence(c["evidence"]),
                         "adjustments": adj, "subparts": {n: {"present": s.get("present"), "normalised": s.get("normalised")}
                                                          for n, s in (c.get("subparts") or {}).items()},
                         "m3": {"public": c.get("public_line_fit"), "observed": c.get("observed_pattern_fit")} if k == "M3" else None,
                         "past": [{"message": p["message"]} for p in sc.get("past_corrections", {}).get(k, [])]})
        gates = [{"id": g, "state": v["state"], "reason": v.get("reason", ""), "evidence": _evidence(v.get("evidence")),
                  "adjacent": v.get("adjacent_overlaps"), "caveat": v.get("caveat")} for g, v in sc["gates"].items()]
        disc = []
        for c in checks:
            if c["status"] == "PASS":
                continue
            st = c.get("stated") or {}
            disc.append({"id": c["id"], "status": c["status"], "kind": c["kind"], "label": c["label"],
                         "stated": st.get("as_written"), "stated_cite": st.get("cite"), "stated_pdf": pdf_link(st.get("cite", "")),
                         "recomputed": c.get("recomputed"), "diff_pct": c.get("diff_pct"), "direction": c.get("direction"),
                         "material": c.get("material_field"), "curated": c.get("curated"), "note": c.get("note"),
                         "inputs": [{"label": i.get("label"), "as_written": i.get("as_written"), "cite": i.get("cite"),
                                     "pdf": pdf_link(i.get("cite", ""))} for i in c.get("inputs", [])]})
        n_pass = sum(c["status"] == "PASS" for c in checks)
        fmap = {f["id"]: f for f in res["findings"]}
        research = {
            "competitors": [{"name": c["name"], "funded": c.get("funded"), "funding": c.get("funding"),
                             "named": c.get("named_in_application"),
                             "links": [{"url": fmap[i]["url"], "publisher": fmap[i]["publisher"],
                                        "accessed": fmap[i]["accessed_date"]} for i in c.get("finding_ids", []) if i in fmap]}
                            for c in res["competitors"]],
            "findings": [{"id": f["id"], "topic": f["topic"], "stance": f["stance"], "claim": f["supports_claim"],
                          "finding": f["finding"], "url": f["url"], "publisher": f["publisher"],
                          "published": f["published_date"], "accessed": f["accessed_date"], "confidence": f["confidence"]}
                         for f in res["findings"]],
            "conflicts": res["conflicts"], "not_found": res["not_found"]}
        history = {
            "outcomes": _rows(conn, "SELECT model_band, model_recommendation, human_decision, decided_by, decided_at, reason, created_at "
                                    "FROM outcomes WHERE company=? ORDER BY id", (co,)),
            "corrections": _rows(conn, "SELECT criterion, model_score, human_score, reason, corrected_by, corrected_at "
                                       "FROM corrections WHERE company=? ORDER BY id", (co,)),
            "outbox": _rows(conn, "SELECT o.id, o.kind, o.status, o.to_addr, o.created_at, o.sent_at, a.approved_by "
                                  "FROM outbox o LEFT JOIN approvals a ON a.id=o.approval_id WHERE o.company=? ORDER BY o.id", (co,)),
            "holds": _rows(conn, "SELECT h.id, h.start_at, h.status, a.approved_by FROM calendar_holds h "
                                 "LEFT JOIN approvals a ON a.id=h.approval_id WHERE h.company=? ORDER BY h.id", (co,)),
            "replies": _rows(conn, "SELECT r.received_at, r.classification, r.confirmed_by, r.action FROM replies r "
                                   "JOIN threads t ON t.id=r.thread_id WHERE t.company=? ORDER BY r.id", (co,)),
        }
        companies.append({
            "company": co, "sector": ff.get("sector_selected", {}).get("value"), "stage": ff.get("stage_selected", {}).get("value"),
            "location": ff.get("location", {}).get("value"), "one_liner": ff.get("one_liner", {}).get("value"),
            "raise": ff.get("raise", {}).get("value"),
            "total": sc["total"], "band": sc["band"], "band_reasons": sc["band_reasons"],
            "subtotals": {"founder": sc["founder_subtotal"], "path": sc["path_subtotal"],
                          "thesis": sc["thesis_subtotal"], "structure": sc["structure_subtotal"]},
            "close_call": sc["close_call"], "close_call_threshold": sc["close_call_threshold"],
            "swing": sc["swing_criteria"], "integrity_cap": sc["integrity_cap"], "unknown": sc["unknown"],
            "routing": sc["routing"], "criteria": crit, "gates": gates, "discrepancies": disc, "checks_passed": n_pass,
            "checks_total": len(checks), "research": research, "history": history,
            "overlaps": [o for o in fund.get("overlaps", []) if o.get("applicant") == co and o.get("portfolio_company")]})
    bt = _load(DATA / "backtest" / "result.json")
    backtest = None
    if bt:
        backtest = {"agreement": bt["agreement"], "rows": [
            {"memo": r["memo_no"], "company": r["company"], "decision": r["decision"], "total": r["total"], "band": r["band"],
             "result": r["result"], "founder": r["founder"], "path": r["path"]} for r in bt["rows"]]}
    return {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "config_version": cfg.get("version"),
            "thresholds": cfg["thresholds"], "groups": {g: sum(cfg["criteria"][k]["weight"] for k in ks)
                                                         for g, ks in cfg["groups"].items()},
            "companies": companies, "backtest": backtest,
            "reports": sorted(p.name for p in (ROOT / "reports").glob("stage*.md"))}


PUBLISH_HEAD = """<title>AIC Screener</title>
<meta name="claude:viewport-fit-sides" content="cover">
"""


def publishable(data: dict) -> dict:
    """Variant for an online page: no links to local files (source PDFs, reports)."""
    d = json.loads(json.dumps(data))
    for c in d["companies"]:
        for cr in c["criteria"]:
            for e in cr["evidence"]:
                e["pdf"] = ""
        for g in c["gates"]:
            for e in g["evidence"]:
                e["pdf"] = ""
        for x in c["discrepancies"]:
            x["stated_pdf"] = ""
            for i in x["inputs"]:
                i["pdf"] = ""
    d["reports"] = []
    d["backtest"] = None   # names real memo companies with the fund's decisions; kept off the online page
    return d


def render(data: dict, publish: bool = False) -> str:
    if publish:
        data = publishable(data)
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = TEMPLATE.replace("__DATA__", payload)
    if publish:
        # The artifact host supplies doctype/head/body and the theme; keep page content, style and scripts.
        head_end = html.index("<style>")
        html = PUBLISH_HEAD + html[head_end:]
        html = html.replace("</style></head>\n<body>", "</style>").replace("</script></body></html>", "</script>")
        html = re.sub(r'<span class="meta">Theme: <button id="theme".*?</button></span>', "", html, flags=re.S)
        html = re.sub(r"// ---- theme toggle.*?\}\)\(\);\n", "", html, flags=re.S)
        html = html.replace("b.addEventListener(\"click\",()=>{i=(i+1)%3;apply();render();});apply();})();", "")
        html = html.replace("header{padding:16px 24px;", "header{padding-block:16px;padding-left:max(24px,env(safe-area-inset-left,0px));padding-right:max(24px,env(safe-area-inset-right,0px));")
        html = html.replace("main{display:grid;grid-template-columns:260px minmax(0,1fr);gap:16px;padding:0 24px 32px}",
                            "main{display:grid;grid-template-columns:260px minmax(0,1fr);gap:16px;padding-block:0 32px;padding-left:max(24px,env(safe-area-inset-left,0px));padding-right:max(24px,env(safe-area-inset-right,0px))}")
        html = html.replace("@media (max-width:900px){main{grid-template-columns:minmax(0,1fr);padding:0 16px 24px}.notice{margin-left:16px;margin-right:16px}header{padding:12px 16px}",
                            "@media (max-width:900px){main{grid-template-columns:minmax(0,1fr);padding-block:0 24px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}.notice{margin-left:max(16px,env(safe-area-inset-left,0px));margin-right:max(16px,env(safe-area-inset-right,0px))}header{padding-block:12px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}")
        html = html.replace("nav{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px;align-self:start;position:sticky;top:8px}",
                            "nav{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px;align-self:start;position:sticky;top:calc(env(safe-area-inset-top,0px) + 8px)}")
    return html


PUBLISH_OUT = ROOT / "dashboard" / "publish.html"


def build(publish: bool = False) -> Path:
    out = PUBLISH_OUT if publish else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(collect(), publish=publish))
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIC Screener</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:">
<style>
:root{color-scheme:light;--bg:#f6f6f4;--surface:#fcfcfb;--line:#e4e3df;--text:#0b0b0b;--text2:#52514e;--muted:#77756f;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--good:#0ca30c;--warn:#fab219;--serious:#ec835a;--crit:#d03b3b;--link:#1c5cab;--chip:#f0efec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#121211;--surface:#1a1a19;--line:#33332f;
--text:#f0efec;--text2:#c3c2b7;--muted:#9a988f;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--link:#86b6ef;--chip:#2a2a27}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121211;--surface:#1a1a19;--line:#33332f;--text:#f0efec;--text2:#c3c2b7;--muted:#9a988f;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--link:#86b6ef;--chip:#2a2a27}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:16px 24px;border-bottom:1px solid var(--line);background:var(--surface);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
header h1{font-size:18px;margin:0}header .meta{color:var(--muted);font-size:12px}
.notice{margin:12px 24px;padding:10px 12px;border:1px solid var(--line);border-left:4px solid var(--s1);background:var(--surface);border-radius:6px;color:var(--text2)}
main{display:grid;grid-template-columns:260px minmax(0,1fr);gap:16px;padding:0 24px 32px}#view{min-width:0}
@media (max-width:900px){main{grid-template-columns:minmax(0,1fr);padding:0 16px 24px}.notice{margin-left:16px;margin-right:16px}header{padding:12px 16px}
nav{position:static;display:flex;overflow-x:auto;gap:4px;padding:6px}nav button{width:auto;flex:0 0 auto;gap:8px;white-space:nowrap}}
nav{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px;align-self:start;position:sticky;top:8px}
nav button{display:flex;justify-content:space-between;width:100%;padding:8px;border:0;background:none;color:var(--text);text-align:left;border-radius:6px;cursor:pointer;font:inherit}
nav button:hover,nav button[aria-current="true"]{background:var(--chip)}nav .t{color:var(--text2);font-variant-numeric:tabular-nums}
section.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px;margin-bottom:16px;overflow-x:auto}
h2{font-size:16px;margin:0 0 8px}h3{font-size:14px;margin:16px 0 6px;color:var(--text2)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px}td:last-child{min-width:240px}td.n{text-align:right;font-variant-numeric:tabular-nums}
tr.click{cursor:pointer}tr.click:hover{background:var(--chip)}
.badge{display:inline-flex;gap:4px;align-items:center;padding:1px 8px;border-radius:10px;font-size:12px;border:1px solid var(--line);white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.b-call .dot{background:var(--good)}.b-partner_review .dot{background:var(--warn)}.b-hold .dot{background:var(--serious)}.b-pass .dot{background:var(--crit)}
.st-FAIL{color:var(--crit);font-weight:600}.st-UNCHECKABLE{color:var(--muted);font-weight:600}.st-flag{color:var(--serious);font-weight:600}.st-hold{color:var(--crit);font-weight:600}.st-clear{color:var(--text2)}
.muted{color:var(--muted)}.small{font-size:12px}a{color:var(--link)}
.ev{margin:2px 0;font-size:12px;color:var(--text2)}.ev .q{color:var(--text);font-style:italic}
.kv{display:grid;grid-template-columns:160px 1fr;gap:4px 12px;font-size:13px}.kv div:nth-child(odd){color:var(--muted)}
.chart{position:relative}.chart svg{display:block;width:100%;height:auto}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--text2);margin:6px 0}.legend span{display:inline-flex;gap:6px;align-items:center}
.sw{width:12px;height:12px;border-radius:3px;display:inline-block}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;z-index:9}
details summary{cursor:pointer;color:var(--text2)}
.adj{color:var(--serious);font-size:12px}.past{font-size:12px;color:var(--text2);border-left:3px solid var(--s1);padding-left:6px;margin:4px 0}
.tabs{display:flex;gap:4px;flex-wrap:wrap;margin:8px 0}.tabs button{border:1px solid var(--line);background:var(--surface);color:var(--text);padding:4px 10px;border-radius:14px;cursor:pointer;font:inherit;font-size:12px}
.tabs button[aria-selected="true"]{background:var(--text);color:var(--surface)}
</style></head>
<body>
<header><h1>AIC Screener</h1><span class="meta" id="meta"></span>
<span class="meta">Theme: <button id="theme" style="font:inherit;background:none;border:1px solid var(--line);color:var(--text);border-radius:6px;cursor:pointer">auto</button></span></header>
<div class="notice">Recommendations only. Partners decide; nobody is auto-rejected or auto-advanced. Every score cites its evidence; numbers are computed in code.</div>
<main><nav id="nav" aria-label="Companies"></nav><div id="view"></div></main>
<div id="tip" role="tooltip"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const BAND = {call:"Call", partner_review:"Partner review", hold:"Hold", pass:"Pass recommendation"};
const ICON = {call:"\u2713", partner_review:"!", hold:"\u23F8", pass:"\u00D7"};
const GROUPS = [["founder","Founder","--s1"],["path","Path","--s2"],["thesis","Thesis","--s3"],["structure","Structure","--s4"]];
function el(tag, attrs, ...kids){const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs||{})){if(v==null)continue;if(k==="class")e.className=v;else if(k==="on")for(const [ev,f] of Object.entries(v))e.addEventListener(ev,f);else e.setAttribute(k,v);}for(const k of kids){if(k==null||k===false)continue;e.append(k instanceof Node?k:document.createTextNode(String(k)));}return e;}
function safeUrl(u){try{const x=new URL(u);return (x.protocol==="https:"||x.protocol==="http:")?x.href:null;}catch(e){return null;}}
function link(text, href, ext){if(!href)return document.createTextNode(text||"");const a=el("a",{href:href},text);if(ext){a.target="_blank";a.rel="noopener noreferrer";}return a;}
function badge(band){return el("span",{class:"badge b-"+band},el("span",{class:"dot","aria-hidden":"true"}),ICON[band]+" "+BAND[band]);}
function evidence(list){const box=el("div");for(const e of list||[]){const row=el("div",{class:"ev"});
  if(e.type==="external"){const u=safeUrl(e.url);row.append(link((e.cite||"source"),u,true)," ",el("span",{class:"muted"},"accessed "+(e.accessed||"?")+(e.confidence?(" \u00B7 "+e.confidence+" confidence"):"")));}
  else if(e.type==="check"){row.append(el("span",{},"Check "+e.ref.replace("check:","")+" ["+(e.status||"")+"] "),el("span",{class:"muted"},e.cite||""));}
  else{row.append(e.pdf?link(e.cite,e.pdf,false):el("span",{},e.cite||e.ref));}
  if(e.quote)row.append(" ",el("span",{class:"q"},"\u201C"+e.quote+"\u201D"));if(e.point)row.append(el("div",{},e.point));box.append(row);}return box;}
function fmt(n){if(n==null)return "";if(typeof n!=="number")return String(n);const a=Math.abs(n);
  if(a>=1e12)return "INR "+(n/1e12).toFixed(2)+" lakh Cr";if(a>=1e7)return "INR "+(n/1e7).toFixed(2)+" Cr";if(a>=1e5)return "INR "+(n/1e5).toFixed(2)+" L";
  return Number.isInteger(n)?n.toLocaleString("en-IN"):n.toLocaleString("en-IN",{maximumFractionDigits:3});}

// ---- theme toggle
(function(){const b=document.getElementById("theme");const order=["auto","light","dark"];let i=0;try{const s=localStorage.getItem("aic-theme");if(s)i=order.indexOf(s);}catch(e){}
  function apply(){const t=order[i];if(t==="auto")document.documentElement.removeAttribute("data-theme");else document.documentElement.setAttribute("data-theme",t);b.textContent=t;try{localStorage.setItem("aic-theme",t);}catch(e){}}
  b.addEventListener("click",()=>{i=(i+1)%3;apply();render();});apply();})();

document.getElementById("meta").textContent="Generated "+D.generated+" \u00B7 rubric "+D.config_version+" \u00B7 thresholds: call "+D.thresholds.call+", pass "+D.thresholds.pass;

let current=null;
function nav(){const n=document.getElementById("nav");n.replaceChildren();
  n.append(el("button",{"aria-current":String(current===null),on:{click:()=>{current=null;render();}}},el("span",{},"Overview"),el("span",{class:"t"},"")));
  for(const c of D.companies)n.append(el("button",{"aria-current":String(current===c.company),on:{click:()=>{current=c.company;render();window.scrollTo(0,0);}}},
    el("span",{},c.company),el("span",{class:"t"},c.total.toFixed(0)+" \u00B7 "+ICON[c.band])));
  if(D.backtest)n.append(el("button",{"aria-current":String(current==="__bt"),on:{click:()=>{current="__bt";render();}}},el("span",{},"Backtest (12 memos)"),el("span",{class:"t"},"")));}

// ---- overview chart: stacked subtotals with threshold lines
const tip=document.getElementById("tip");
function showTip(ev,lines){tip.replaceChildren(...lines.map(l=>el("div",{},l)));tip.style.display="block";
  const x=Math.min(ev.clientX+12,window.innerWidth-tip.offsetWidth-8),y=ev.clientY+12;tip.style.left=x+"px";tip.style.top=y+"px";}
function hideTip(){tip.style.display="none";}
function chart(list){const css=getComputedStyle(document.documentElement);const W=760,rowH=26,top=24,left=96,right=24,H=top+list.length*rowH+24;
  const xs=v=>left+(W-left-right)*v/100;const NS="http://www.w3.org/2000/svg";
  const svg=document.createElementNS(NS,"svg");svg.setAttribute("viewBox","0 0 "+W+" "+H);svg.setAttribute("role","img");
  svg.setAttribute("aria-label","Stacked score by group for each company, with call and pass thresholds");
  function s(tag,a){const e=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(a))e.setAttribute(k,v);return e;}
  for(const t of [0,25,50,75,100]){svg.append(s("line",{x1:xs(t),x2:xs(t),y1:top-6,y2:H-20,stroke:css.getPropertyValue("--line"),"stroke-width":1}));
    const tx=s("text",{x:xs(t),y:H-6,"text-anchor":"middle","font-size":11,fill:css.getPropertyValue("--muted")});tx.textContent=t;svg.append(tx);}
  list.forEach((c,i)=>{const y=top+i*rowH;const lab=s("text",{x:left-8,y:y+14,"text-anchor":"end","font-size":12,fill:css.getPropertyValue("--text")});lab.textContent=c.company;svg.append(lab);
    let acc=0;GROUPS.forEach(([g,name,v],gi)=>{const val=c.subtotals[g];if(val<=0){return;}const x0=xs(acc),x1=xs(acc+val);acc+=val;
      const r=s("rect",{x:x0+(gi?1:0),y:y+4,width:Math.max(0,x1-x0-(gi?1:0)-1),height:rowH-10,rx:3,fill:css.getPropertyValue(v).trim()});
      const hit=s("rect",{x:x0,y:y,width:Math.max(2,x1-x0),height:rowH,fill:"transparent"});
      hit.addEventListener("mousemove",ev=>showTip(ev,[c.company+" \u00B7 "+name,val+" of "+D.groups[g]+" points","Total "+c.total+" \u00B7 "+BAND[c.band]]));
      hit.addEventListener("mouseleave",hideTip);hit.style.cursor="pointer";hit.addEventListener("click",()=>{current=c.company;render();});svg.append(r,hit);});
    const tv=s("text",{x:xs(acc)+6,y:y+14,"font-size":12,fill:css.getPropertyValue("--text2")});tv.textContent=c.total.toFixed(0);svg.append(tv);});
  for(const [t,name] of [[D.thresholds.pass,"pass "+D.thresholds.pass],[D.thresholds.call,"call "+D.thresholds.call]]){
    svg.append(s("line",{x1:xs(t),x2:xs(t),y1:top-10,y2:H-20,stroke:css.getPropertyValue("--text"),"stroke-width":1.5,"stroke-dasharray":"4 3"}));
    const tx=s("text",{x:xs(t),y:top-12,"text-anchor":"middle","font-size":11,fill:css.getPropertyValue("--text")});tx.textContent=name;svg.append(tx);}
  const leg=el("div",{class:"legend"},...GROUPS.map(([g,name,v])=>el("span",{},el("span",{class:"sw",style:"background:var("+v+")"}),name+" (/"+D.groups[g]+")")),
    el("span",{class:"muted"},"Dashed lines: thresholds. Hover for values; click to open."));
  return el("div",{class:"chart"},leg,svg);}

function overview(){const v=el("div");const list=[...D.companies].sort((a,b)=>b.total-a.total);
  v.append(el("section",{class:"card"},el("h2",{},"Applications"),chart(list)));
  const t=el("table",{},el("thead",{},el("tr",{},...["Company","Sector","Total","Founder","Path","Recommendation","Gates not clear","Integrity cap","Close call","Discrepancies","Human decision"].map(h=>el("th",{},h)))));
  const tb=el("tbody");for(const c of list){const g=c.gates.filter(x=>x.state!=="clear").map(x=>x.id+" "+x.state).join(", ")||"none";
    const dec=c.history.outcomes.filter(o=>o.human_decision).slice(-1)[0];
    tb.append(el("tr",{class:"click",tabindex:"0",on:{click:()=>{current=c.company;render();},keydown:e=>{if(e.key==="Enter"){current=c.company;render();}}}},
      el("td",{},c.company),el("td",{class:"small"},c.sector||""),el("td",{class:"n"},c.total.toFixed(0)),el("td",{class:"n"},c.subtotals.founder),el("td",{class:"n"},c.subtotals.path),
      el("td",{},badge(c.band)),el("td",{class:"small"},g),el("td",{},c.integrity_cap.applies?"yes":"no"),el("td",{},c.close_call?("yes ("+c.close_call_threshold+")"):"no"),
      el("td",{class:"n"},c.discrepancies.filter(d=>d.status==="FAIL").length),el("td",{},dec?(dec.human_decision+" by "+dec.decided_by):el("span",{class:"muted"},"undecided"))));}
  t.append(tb);v.append(el("section",{class:"card"},el("h2",{},"Table view"),t));
  if(D.reports.length)v.append(el("section",{class:"card"},el("h2",{},"Run reports"),el("div",{},...D.reports.map(r=>el("div",{},link(r,"../reports/"+r,false))))));
  return v;}

function companyView(c){const v=el("div");
  const head=el("section",{class:"card"},el("h2",{},c.company+"  "),el("p",{class:"muted"},(c.one_liner||"")),
    el("div",{class:"kv"},el("div",{},"Recommendation"),el("div",{},badge(c.band)," ",el("span",{class:"muted"},c.band_reasons.join("; "))),
      el("div",{},"Total"),el("div",{},c.total+" / 100 \u00B7 founder "+c.subtotals.founder+"/35 \u00B7 path "+c.subtotals.path+"/35 \u00B7 thesis "+c.subtotals.thesis+"/20 \u00B7 structure "+c.subtotals.structure+"/10"),
      el("div",{},"Close call"),el("div",{},c.close_call?("yes, within 5 of "+c.close_call_threshold):"no"),
      el("div",{},"Integrity cap"),el("div",{},c.integrity_cap.applies?("applies: "+c.integrity_cap.contradictions.map(x=>x.field+" ("+x.id+")").join(", ")):"does not apply"),
      el("div",{},"Unknown (missing data)"),el("div",{},c.unknown.length?c.unknown.join(", "):"none"),
      el("div",{},"Most likely to change it"),el("div",{},c.swing.map(s=>s.criterion+" ("+s.why+", "+s.points_per_step+" pts per step "+s.direction+")").join("; ")),
      el("div",{},"Sector / stage / raise"),el("div",{},[c.sector,c.stage,c.raise,c.location].filter(Boolean).join(" \u00B7 ")),
      el("div",{},"Routing"),el("div",{},...c.routing.map(r=>el("div",{},r)))));
  v.append(head);
  const tabs=[["score","Score card"],["gates","Gates"],["disc","Discrepancies ("+c.discrepancies.filter(d=>d.status==="FAIL").length+")"],["research","Research"],["history","Decision history"]];
  const body=el("section",{class:"card"});const tb=el("div",{class:"tabs",role:"tablist"});let sel="score";try{sel=sessionStorage.getItem("aic-tab")||"score";}catch(e){}
  function show(k){sel=k;try{sessionStorage.setItem("aic-tab",k);}catch(e){}for(const b of tb.children)b.setAttribute("aria-selected",String(b.dataset.k===k));body.replaceChildren(tb,renderTab(c,k));}
  for(const [k,n] of tabs){const b=el("button",{role:"tab",on:{click:()=>show(k)}},n);b.dataset.k=k;tb.append(b);}show(tabs.some(t=>t[0]===sel)?sel:"score");v.append(body);return v;}

function renderTab(c,k){
  if(k==="score"){const t=el("table",{},el("thead",{},el("tr",{},...["Criterion","Weight","Score","Points","Confidence","Rationale and evidence"].map(h=>el("th",{},h)))));const b=el("tbody");
    for(const r of c.criteria){const cell=el("td",{},el("div",{},r.rationale||""));
      for(const a of r.adjustments)cell.append(el("div",{class:"adj"},"Adjusted "+a.from+" \u2192 "+a.to+": "+a.rule));
      if(Object.keys(r.subparts).length)cell.append(el("div",{class:"small muted"},"Sub-parts: "+Object.entries(r.subparts).map(([n,s])=>n+(s.present?" \u2713":" \u2013")).join(", ")));
      if(r.m3)cell.append(el("div",{class:"small muted"},"Public line: "+r.m3.public+" \u00B7 observed pattern: "+r.m3.observed));
      cell.append(evidence(r.evidence));for(const p of r.past)cell.append(el("div",{class:"past"},p.message));
      b.append(el("tr",{},el("td",{},r.id+" "+r.name),el("td",{class:"n"},r.weight),el("td",{class:"n"},(r.unknown?"0 (unknown)":String(r.final))+(r.proposed!==r.final?" (proposed "+r.proposed+")":"")),
        el("td",{class:"n"},r.points),el("td",{class:"small"},r.confidence||""),cell));}
    t.append(b);return t;}
  if(k==="gates"){const t=el("table",{},el("thead",{},el("tr",{},...["Gate","State","Reason and evidence"].map(h=>el("th",{},h)))));const b=el("tbody");
    for(const g of c.gates){const cell=el("td",{},el("div",{},g.reason||""));if(g.adjacent&&g.adjacent.length)cell.append(el("div",{class:"small muted"},"Adjacent portfolio overlaps (shown, not held): "+g.adjacent.join(", ")));
      if(g.caveat)cell.append(el("div",{class:"small muted"},g.caveat));cell.append(evidence(g.evidence));
      b.append(el("tr",{},el("td",{},g.id),el("td",{class:"st-"+g.state},g.state),cell));}
    t.append(b);return t;}
  if(k==="disc"){const box=el("div");box.append(el("p",{class:"muted small"},c.checks_passed+" of "+c.checks_total+" deterministic checks passed. Failures and unverifiable checks below; 'material' contradictions trigger the integrity cap."));
    const t=el("table",{},el("thead",{},el("tr",{},...["Check","Status","Kind","Stated","Recomputed","Diff","Material","Inputs and note"].map(h=>el("th",{},h)))));const b=el("tbody");
    for(const d of c.discrepancies){const cell=el("td",{class:"small"});for(const i of d.inputs)cell.append(el("div",{},(i.label||"")+": "+(i.as_written||"")+" ",i.pdf?link(i.cite,i.pdf,false):el("span",{class:"muted"},i.cite||"")));
      if(d.direction)cell.append(el("div",{},d.direction));if(d.note)cell.append(el("div",{class:"muted"},d.note));if(d.curated)cell.append(el("div",{class:"adj"},"Curated text check: a human should confirm."));
      b.append(el("tr",{},el("td",{},d.label),el("td",{class:"st-"+d.status},d.status),el("td",{class:"small"},d.kind),
        el("td",{class:"small"},d.stated||"",d.stated_pdf?el("div",{},link(d.stated_cite,d.stated_pdf,false)):""),el("td",{class:"n"},fmt(d.recomputed)),
        el("td",{class:"n"},d.diff_pct!=null?(d.diff_pct>0?"+":"")+d.diff_pct+"%":""),el("td",{},d.material||""),cell));}
    t.append(b);box.append(t);return box;}
  if(k==="research"){const box=el("div");const r=c.research;
    box.append(el("h3",{},"Competitors ("+r.competitors.length+", "+r.competitors.filter(x=>x.funded).length+" funded)"));
    const t=el("table",{},el("thead",{},el("tr",{},...["Name","Funding","Named in application","Sources"].map(h=>el("th",{},h)))));const b=el("tbody");
    for(const x of r.competitors)b.append(el("tr",{},el("td",{},x.name),el("td",{class:"small"},x.funded?(x.funding||"funded"):"not found"),el("td",{},x.named?"yes":"no"),
      el("td",{class:"small"},...x.links.map(l=>el("div",{},link(l.publisher,safeUrl(l.url),true)," ",el("span",{class:"muted"},"accessed "+l.accessed))))));
    t.append(b);box.append(t);
    if(c.overlaps.length){box.append(el("h3",{},"Portfolio overlap screen (public list only)"));for(const o of c.overlaps)box.append(el("div",{class:"ev"},o.portfolio_company+" ["+o.strength+"]: "+o.basis));}
    box.append(el("h3",{},"Findings ("+r.findings.length+")"));
    const t2=el("table",{},el("thead",{},el("tr",{},...["Topic","Stance","Tests","Finding","Source"].map(h=>el("th",{},h)))));const b2=el("tbody");
    for(const f of r.findings)b2.append(el("tr",{},el("td",{class:"small"},f.topic),el("td",{class:"small"+(f.stance==="contradicts"?" st-FAIL":"")},f.stance),el("td",{class:"small"},f.claim),
      el("td",{class:"small"},f.finding),el("td",{class:"small"},link(f.publisher,safeUrl(f.url),true),el("div",{class:"muted"},"published "+f.published+" \u00B7 accessed "+f.accessed+" \u00B7 "+f.confidence))));
    t2.append(b2);box.append(t2);
    if(r.conflicts.length){box.append(el("h3",{},"Conflicting sources"));for(const x of r.conflicts)box.append(el("div",{class:"ev"},(x.topic||"")+": "+(x.description||"")+" ["+(x.finding_ids||[]).join(", ")+"]"));}
    if(r.not_found.length){box.append(el("h3",{},"Not found"));for(const x of r.not_found)box.append(el("div",{class:"ev"},x.question));}
    return box;}
  if(k==="history"){const h=c.history;const box=el("div");
    function tbl(title,rows,cols){box.append(el("h3",{},title));if(!rows.length){box.append(el("div",{class:"muted small"},"none"));return;}
      const t=el("table",{},el("thead",{},el("tr",{},...cols.map(x=>el("th",{},x)))),el("tbody",{},...rows.map(r=>el("tr",{},...cols.map(x=>el("td",{class:"small"},r[x]==null?"":String(r[x])))))));box.append(t);}
    tbl("Outcomes (model recommends; a named human decides)",h.outcomes,["created_at","model_band","model_recommendation","human_decision","decided_by","decided_at","reason"]);
    tbl("Score corrections",h.corrections,["corrected_at","criterion","model_score","human_score","reason","corrected_by"]);
    tbl("Outreach (dry run)",h.outbox,["id","kind","status","to_addr","approved_by","created_at","sent_at"]);
    tbl("Calendar holds",h.holds,["id","start_at","status","approved_by"]);
    tbl("Replies (labels only; text is untrusted)",h.replies,["received_at","classification","confirmed_by","action"]);
    return box;}
}

function backtestView(){const B=D.backtest;const v=el("section",{class:"card"},el("h2",{},"Blind backtest: 12 past deal memos"),
  el("p",{class:"muted"},"Scored blind (decision, stage, source, rationale and names removed; outcome files vaulted), then unsealed. As scored: agree "+B.agreement.as_scored.agree+", disagree "+B.agreement.as_scored.disagree+", partner review "+B.agreement.as_scored.review+". Every memo scored Pass, so band agreement equals 'always pass'. See reports/stage5.md."));
  const t=el("table",{},el("thead",{},el("tr",{},...["Memo","Company","Decision","Total","Founder","Path","Band","Result"].map(h=>el("th",{},h)))),
    el("tbody",{},...B.rows.map(r=>el("tr",{},el("td",{class:"n"},r.memo),el("td",{},r.company),el("td",{},r.decision),el("td",{class:"n"},r.total),el("td",{class:"n"},r.founder),el("td",{class:"n"},r.path),el("td",{},badge(r.band)),el("td",{class:r.result==="disagree"?"st-FAIL":""},r.result)))));
  v.append(t);return v;}

function render(){nav();const view=document.getElementById("view");view.replaceChildren();
  if(current===null)view.append(overview());else if(current==="__bt")view.append(backtestView());
  else view.append(companyView(D.companies.find(c=>c.company===current)));}
render();
</script></body></html>
"""

if __name__ == "__main__":
    import sys
    print(build(publish="--publish" in sys.argv))
