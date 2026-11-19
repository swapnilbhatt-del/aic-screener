"""Stage 7: outreach, dry-run only.

Gates (each enforced in code AND, where it matters, in the DB):
  * Drafting needs a human decision in `outcomes` ('call' for an invite, 'pass' for a pass note).
  * A recipient that appears anywhere in the application documents is refused (constraint 6).
  * Sending needs an approval row for that exact email and an allow-listed recipient (DB triggers).
  * Only a DryRunSender exists: it writes .eml files to outbox/. There is no live sender.
  * Calendar holds are .ics files written only after an approval (DB trigger on ics_path).
  * Founder replies are stored and labelled by fixed rules; their text is never used to choose an action,
    a recipient, or email content. 'no'/'unclear' needs a named human before any action (DB trigger).

  python -m aic.outreach status
  python -m aic.outreach approve-email <outbox_id> <your name>
  python -m aic.outreach approve-hold <hold_id> <your name>
  python -m aic.outreach allow <placeholder address> <your name>
"""
import json
import re
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from pathlib import Path
from string import Template
from typing import List, Optional

from zoneinfo import ZoneInfo

from . import config, db, text

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates" / "outreach"
OUTBOX = ROOT / "outbox"
IST = ZoneInfo("Asia/Kolkata")
DAYS = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class OutreachError(RuntimeError):
    pass


# ---- guards ----------------------------------------------------------------------
def human_decision(conn: sqlite3.Connection, company: str) -> Optional[str]:
    row = conn.execute("SELECT human_decision FROM outcomes WHERE company=? AND human_decision IS NOT NULL "
                       "ORDER BY decided_at DESC, id DESC LIMIT 1", (company,)).fetchone()
    return row[0] if row else None


def addresses_in_documents(text_dir: Path = text.TEXT_DIR) -> set:
    found = set()
    for p in text_dir.glob("*.json"):
        for pg in json.loads(p.read_text())["pages"]:
            found |= {a.lower() for a in EMAIL_RE.findall(pg["plain"] + " " + pg["layout"])}
    return found


def domains_in_documents(text_dir: Path = text.TEXT_DIR) -> set:
    found = set()
    for p in text_dir.glob("*.json"):
        for pg in json.loads(p.read_text())["pages"]:
            found |= {d.lower() for d in re.findall(r"\bwww\.([A-Za-z0-9.-]+\.[A-Za-z]{2,})", pg["plain"])}
    return found


def check_recipient(addr: str, doc_addrs: set, doc_domains: Optional[set] = None) -> str:
    a = addr.strip().lower()
    if not EMAIL_RE.fullmatch(a):
        raise OutreachError(f"not an email address: {addr!r}")
    if a in doc_addrs:
        raise OutreachError(f"{a} appears in an application document; deck/form addresses are never used")
    doc_domains = domains_in_documents() if doc_domains is None else doc_domains
    if a.split("@", 1)[1] in doc_domains:
        raise OutreachError(f"{a} is on a company domain from the application documents; never used")
    return a


def _require_dry_run(cfg: dict):
    if cfg["outreach"].get("dry_run") is not True:   # config.validate already refuses this; belt and braces
        raise OutreachError("live sending is not implemented; dry_run must be true")


# ---- slots -----------------------------------------------------------------------
def propose_slots(conn: sqlite3.Connection, after: datetime, n: int = 3, cfg: Optional[dict] = None) -> List[datetime]:
    """Next n free slots on the configured days/window (Tue/Thu 14:00-18:00 IST, 30 min)."""
    cfg = cfg or config.load()
    o = cfg["outreach"]
    days = {DAYS[d] for d in o["slot_days"]}
    start_t, end_t = (time.fromisoformat(o["slot_window"][k]) for k in ("start", "end"))
    mins = o["slot_minutes"]
    taken = {datetime.fromisoformat(r[0]) for r in conn.execute(
        "SELECT start_at FROM calendar_holds WHERE status IN ('proposed', 'held')")}
    after = after.astimezone(IST)
    if o.get("slot_lead") == "next_business_day":
        d0 = after.date() + timedelta(days=1)
        while d0.weekday() >= 5:            # skip Saturday and Sunday
            d0 += timedelta(days=1)
        after = max(after, datetime.combine(d0, time(0, 0), IST))
    out, d = [], after.date()
    while len(out) < n:
        if d.weekday() in days:
            t = datetime.combine(d, start_t, IST)
            while t + timedelta(minutes=mins) <= datetime.combine(d, end_t, IST) and len(out) < n:
                if t > after and t not in taken:
                    out.append(t)
                t += timedelta(minutes=mins)
        d += timedelta(days=1)
    return out


def fmt_slot(t: datetime) -> str:
    return t.strftime("%a %d %b, %H:%M") + " IST"


# ---- drafting ----------------------------------------------------------------------
def _render(name: str, **kw) -> (str, str):
    raw = Template((TEMPLATES / f"{name}.txt").read_text()).safe_substitute(**kw)
    subject, _, body = raw.partition("\n---\n")
    return subject.replace("Subject:", "").strip(), body.strip() + "\n"


def draft_invite(conn, company: str, to_addr: str, founder_first: str, after: datetime,
                 signature: str = "[EDIT: signature]", doc_addrs: Optional[set] = None) -> dict:
    if human_decision(conn, company) != "call":
        raise OutreachError(f"{company}: no human 'call' decision recorded; nothing is drafted")
    to = check_recipient(to_addr, addresses_in_documents() if doc_addrs is None else doc_addrs)
    slots = propose_slots(conn, after, n=config.load()["outreach"].get("holds_per_invite", 3))
    subject, body = _render("call_invite", company=company, founder_first=founder_first,
                            slots="\n".join(f"  - {fmt_slot(s)}" for s in slots), signature=signature)
    oid = conn.execute("INSERT INTO outbox (company, to_addr, subject, body, kind) VALUES (?, ?, ?, ?, 'outreach')",
                       (company, to, subject, body)).lastrowid
    tid = conn.execute("INSERT INTO threads (company, root_outbox_id) VALUES (?, ?)", (company, oid)).lastrowid
    conn.execute("INSERT INTO thread_messages (thread_id, outbox_id) VALUES (?, ?)", (tid, oid))
    holds = [conn.execute("INSERT INTO calendar_holds (company, start_at, minutes) VALUES (?, ?, ?)",
                          (company, s.isoformat(), config.load()["outreach"]["slot_minutes"])).lastrowid for s in slots]
    conn.commit()
    return {"outbox_id": oid, "thread_id": tid, "hold_ids": holds, "slots": [s.isoformat() for s in slots]}


def draft_pass_note(conn, company: str, to_addr: str, founder_first: str, partner_reason: str,
                    signature: str = "[EDIT: signature]", doc_addrs: Optional[set] = None) -> int:
    if human_decision(conn, company) != "pass":
        raise OutreachError(f"{company}: no human 'pass' decision recorded; nothing is drafted")
    if not partner_reason.strip():
        raise OutreachError("a pass note needs the partner's own reason")
    to = check_recipient(to_addr, addresses_in_documents() if doc_addrs is None else doc_addrs)
    subject, body = _render("pass_note", company=company, founder_first=founder_first,
                            partner_reason=partner_reason.strip(), signature=signature)
    oid = conn.execute("INSERT INTO outbox (company, to_addr, subject, body, kind) VALUES (?, ?, ?, ?, 'pass_note')",
                       (company, to, subject, body)).lastrowid
    conn.commit()
    return oid


# ---- approvals and dry-run sending ----------------------------------------------------
def approve_email(conn, outbox_id: int, by: str, note: str = "") -> int:
    aid = conn.execute("INSERT INTO approvals (action_type, target_id, approved_by, note) VALUES ('send_email', ?, ?, ?)",
                       (outbox_id, by, note)).lastrowid
    conn.execute("UPDATE outbox SET status='approved', approval_id=? WHERE id=?", (aid, outbox_id))
    conn.commit()
    return aid


class DryRunSender:
    """Writes the email as an .eml file. The only sender that exists."""

    def __init__(self, outdir: Path = OUTBOX / "sent"):
        self.outdir = outdir

    def deliver(self, row: dict) -> Path:
        m = EmailMessage()
        m["To"], m["Subject"] = row["to_addr"], row["subject"]
        m["X-AIC-Dry-Run"], m["X-AIC-Outbox-Id"] = "true", str(row["id"])
        m.set_content(row["body"])
        self.outdir.mkdir(parents=True, exist_ok=True)
        p = self.outdir / f"{row['id']:05d}_{row['company']}_{row['kind']}.eml"
        p.write_bytes(bytes(m))
        return p


def send(conn, outbox_id: int, sender: Optional[DryRunSender] = None, now: Optional[datetime] = None) -> Path:
    _require_dry_run(config.load())
    sender = sender or DryRunSender()
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM outbox WHERE id=?", (outbox_id,)).fetchone())
    conn.row_factory = None
    now = now or datetime.now(IST)
    try:
        # The DB decides first: no approval or non-allow-listed recipient -> IntegrityError, nothing written.
        conn.execute("UPDATE outbox SET status='sent', sent_at=? WHERE id=?", (now.isoformat(), outbox_id))
        path = sender.deliver(row)
    except Exception:
        conn.rollback()
        raise
    if row["kind"] == "follow_up":
        conn.execute("UPDATE threads SET followups_sent = followups_sent + 1 WHERE id = "
                     "(SELECT thread_id FROM thread_messages WHERE outbox_id=?)", (outbox_id,))
    conn.commit()
    return path


# ---- tentative holds (.ics) ----------------------------------------------------------
def approve_hold(conn, hold_id: int, by: str, outdir: Path = OUTBOX / "ics") -> Path:
    aid = conn.execute("INSERT INTO approvals (action_type, target_id, approved_by) VALUES ('create_calendar_hold', ?, ?)",
                       (hold_id, by)).lastrowid
    company, start, mins = conn.execute("SELECT company, start_at, minutes FROM calendar_holds WHERE id=?",
                                        (hold_id,)).fetchone()
    path = outdir / f"hold_{hold_id:05d}_{company}.ics"
    try:
        conn.execute("UPDATE calendar_holds SET status='held', approval_id=?, ics_path=? WHERE id=?",
                     (aid, str(path), hold_id))
        s = datetime.fromisoformat(start).astimezone(ZoneInfo("UTC"))
        e = s + timedelta(minutes=mins)
        f = "%Y%m%dT%H%M%SZ"
        outdir.mkdir(parents=True, exist_ok=True)
        path.write_text("\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AIC Screener//dry-run//EN", "BEGIN:VEVENT",
            f"UID:aic-hold-{hold_id}@screener.invalid", f"DTSTAMP:{datetime.now(ZoneInfo('UTC')).strftime(f)}",
            f"DTSTART:{s.strftime(f)}", f"DTEND:{e.strftime(f)}", f"SUMMARY:HOLD (tentative): call with {company}",
            "STATUS:TENTATIVE", "TRANSP:OPAQUE", "END:VEVENT", "END:VCALENDAR", ""]))
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return path


def release_unchosen_holds(conn, thread_id: int, keep_hold_id: Optional[int] = None):
    company = conn.execute("SELECT company FROM threads WHERE id=?", (thread_id,)).fetchone()[0]
    conn.execute("UPDATE calendar_holds SET status='cancelled' WHERE company=? AND status='proposed' AND id IS NOT ?",
                 (company, keep_hold_id))
    conn.commit()


# ---- replies --------------------------------------------------------------------
NO = re.compile(r"\b(not interested|no thanks|no, thank|not a fit|decline|pass on|not raising|already (?:closed|raised)|"
                r"unsubscribe|please don'?t)\b", re.I)
RESCHEDULE = re.compile(r"\b(reschedule|another (?:time|day|slot)|different (?:time|day)|none of (?:these|those)|"
                        r"next week|can we do|later date)\b", re.I)
YES = re.compile(r"\b(works for (?:me|us)|sounds good|happy to|yes|confirmed?|see you|looking forward|"
                 r"(?:tue|thu)(?:sday|rsday)? (?:at )?\d)", re.I)


SUSPICIOUS = re.compile(r"(ignore (?:all |any |the )?(?:previous|prior|above)|\bsystem\s*:|\binstructions?\b|"
                        r"\bapprov\w*|allow-?list|whitelist|\bforward\b|send (?:it|this|the|our)\b|"
                        r"mark (?:this|it) as|confirmed by|https?://|\bpassword\b|\bwire\b|bank details)", re.I)


def classify(body: str) -> str:
    """Fixed rules on the reply text. Ambiguity (mixed or no cues) is 'unclear', never a guess.
    Instruction-like text or any email address/link in the body always goes to a human ('unclear')."""
    b = body[:4000]
    if SUSPICIOUS.search(b) or EMAIL_RE.search(b):
        return "unclear"
    n, r, y = bool(NO.search(b)), bool(RESCHEDULE.search(b)), bool(YES.search(b))
    if n and not (y or r):
        return "no"
    if r and not n:
        return "reschedule"
    if y and not (n or r):
        return "yes"
    return "unclear"


def record_reply(conn, thread_id: int, from_addr: str, body: str, received_at: datetime) -> dict:
    label = classify(body)
    rid = conn.execute("INSERT INTO replies (thread_id, received_at, from_addr, body, classification, classifier) "
                       "VALUES (?, ?, ?, ?, ?, 'rules-v1')",
                       (thread_id, received_at.isoformat(), from_addr, body, label)).lastrowid
    conn.execute("UPDATE threads SET status='replied' WHERE id=?", (thread_id,))
    conn.commit()
    return {"reply_id": rid, "classification": label,
            "needs_human": label in ("no", "unclear")}


def confirm_reply(conn, reply_id: int, by: str, classification: Optional[str] = None):
    if classification:
        conn.execute("UPDATE replies SET classification=? WHERE id=?", (classification, reply_id))
    conn.execute("UPDATE replies SET confirmed_by=?, confirmed_at=? WHERE id=?",
                 (by, datetime.now(IST).isoformat(), reply_id))
    conn.commit()


ACTIONS = {"yes": "propose_slots", "reschedule": "propose_slots", "no": "close_thread", "unclear": "hand_to_partner"}


def act_on_reply(conn, reply_id: int) -> str:
    """The action depends only on the label (never on the reply text). DB blocks no/unclear without a human."""
    thread_id, label = conn.execute("SELECT thread_id, classification FROM replies WHERE id=?", (reply_id,)).fetchone()
    action = ACTIONS[label]
    conn.execute("UPDATE replies SET action=?, actioned_at=? WHERE id=?", (action, datetime.now(IST).isoformat(), reply_id))
    if action == "close_thread":
        conn.execute("UPDATE threads SET status='closed' WHERE id=?", (thread_id,))
    conn.commit()
    return action


# ---- follow-ups ----------------------------------------------------------------------
def due_followups(conn, now: datetime, cfg: Optional[dict] = None) -> List[int]:
    """Draft a follow-up for each thread with no reply, >= N days since the last sent message, < max sent."""
    cfg = cfg or config.load()
    o = cfg["outreach"]
    made = []
    rows = conn.execute(
        "SELECT t.id, t.company, t.followups_sent, o.to_addr, o.subject, "
        "       (SELECT max(o2.sent_at) FROM thread_messages m2 JOIN outbox o2 ON o2.id=m2.outbox_id "
        "         WHERE m2.thread_id=t.id AND o2.status='sent') AS last_sent, "
        "       (SELECT count(*) FROM thread_messages m3 JOIN outbox o3 ON o3.id=m3.outbox_id "
        "         WHERE m3.thread_id=t.id AND o3.status IN ('draft','approved')) AS pending "
        "FROM threads t JOIN outbox o ON o.id=t.root_outbox_id "
        "WHERE t.status='awaiting_reply'").fetchall()
    for tid, company, sent_n, to, _subj, last_sent, pending in rows:
        if not last_sent or pending or sent_n >= o["max_follow_ups"]:
            continue
        if now - datetime.fromisoformat(last_sent) < timedelta(days=o["follow_up_after_days"]):
            continue
        slots = propose_slots(conn, now, cfg=cfg)
        subject, body = _render("follow_up", company=company, founder_first="[EDIT: name]",
                                sent_date=datetime.fromisoformat(last_sent).strftime("%d %b"),
                                slots="\n".join(f"  - {fmt_slot(s)}" for s in slots), signature="[EDIT: signature]")
        oid = conn.execute("INSERT INTO outbox (company, to_addr, subject, body, kind) VALUES (?, ?, ?, ?, 'follow_up')",
                           (company, to, subject, body)).lastrowid
        conn.execute("INSERT INTO thread_messages (thread_id, outbox_id) VALUES (?, ?)", (tid, oid))
        made.append(oid)
    conn.commit()
    return made


# ---- CLI -------------------------------------------------------------------------
if __name__ == "__main__":
    a = sys.argv[1:]
    conn = db.connect()
    if a[:1] == ["status"]:
        print("allowed recipients:", [r[0] for r in conn.execute("SELECT address FROM allowed_recipients")] or "none")
        for r in conn.execute("SELECT id, company, kind, status, to_addr FROM outbox ORDER BY id"):
            print("outbox", r)
        for r in conn.execute("SELECT id, company, start_at, status FROM calendar_holds ORDER BY id"):
            print("hold", r)
        for r in conn.execute("SELECT company, model_band, human_decision FROM outcomes ORDER BY company"):
            print("outcome", r)
    elif a[:1] == ["approve-email"] and len(a) == 3:
        print("approval", approve_email(conn, int(a[1]), a[2]))
    elif a[:1] == ["approve-hold"] and len(a) == 3:
        print("ics", approve_hold(conn, int(a[1]), a[2]))
    elif a[:1] == ["allow"] and len(a) == 3:
        addr = check_recipient(a[1], addresses_in_documents())
        conn.execute("INSERT INTO allowed_recipients (address, added_by) VALUES (?, ?)", (addr, a[2]))
        conn.commit()
        print("allowed", addr)
    else:
        print(__doc__)
