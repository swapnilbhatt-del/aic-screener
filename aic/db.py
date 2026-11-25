"""SQLite schema. The approval gate and the human-decision gate are enforced by triggers,
so no code path (including a buggy one) can send, hold, or decide without a recorded human approval."""
import sqlite3
from pathlib import Path
from typing import Optional, Union

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "aic.db"

THREADS_DDL = """CREATE TABLE IF NOT EXISTS {name} (
    id              INTEGER PRIMARY KEY,
    company         TEXT NOT NULL,
    root_outbox_id  INTEGER NOT NULL UNIQUE REFERENCES outbox(id),
    status          TEXT NOT NULL DEFAULT 'awaiting_reply'
                    CHECK (status IN ('awaiting_reply', 'replied', 'no_reply', 'closed')),
    -- no_reply: max follow-ups sent and still silent; a partner decides (never auto-closed).
    followups_sent  INTEGER NOT NULL DEFAULT 0 CHECK (followups_sent BETWEEN 0 AND 3),  -- backstop; config sets the cap
    closed_by       TEXT CHECK (closed_by IS NULL OR lower(trim(closed_by)) NOT IN ('model', 'system', 'auto', 'claude', '')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SCHEMA = """
PRAGMA foreign_keys = ON;

-- Append-only record of human approvals. One row authorises one action on one target.
CREATE TABLE IF NOT EXISTS approvals (
    id          INTEGER PRIMARY KEY,
    action_type TEXT NOT NULL CHECK (action_type IN ('send_email', 'create_calendar_hold')),
    target_id   INTEGER NOT NULL,
    approved_by TEXT NOT NULL CHECK (length(trim(approved_by)) > 0
                                     AND lower(trim(approved_by)) NOT IN ('model', 'system', 'auto', 'claude')),
    approved_at TEXT NOT NULL DEFAULT (datetime('now')),
    note        TEXT,
    revoked_at  TEXT
);

CREATE TRIGGER IF NOT EXISTS approvals_no_delete
BEFORE DELETE ON approvals
BEGIN SELECT RAISE(ABORT, 'approvals are append-only'); END;

CREATE TRIGGER IF NOT EXISTS approvals_only_revoke
BEFORE UPDATE ON approvals
WHEN NEW.id IS NOT OLD.id OR NEW.action_type IS NOT OLD.action_type OR NEW.target_id IS NOT OLD.target_id
  OR NEW.approved_by IS NOT OLD.approved_by OR NEW.approved_at IS NOT OLD.approved_at
  OR NEW.note IS NOT OLD.note OR OLD.revoked_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'approvals can only be revoked, once'); END;

-- Placeholder addresses a human has allowed for test sends. Empty by default.
CREATE TABLE IF NOT EXISTS allowed_recipients (
    address  TEXT PRIMARY KEY CHECK (address = lower(trim(address)) AND address LIKE '%_@_%'),
    added_by TEXT NOT NULL CHECK (length(trim(added_by)) > 0
                                  AND lower(trim(added_by)) NOT IN ('model', 'system', 'auto', 'claude')),
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outbox (
    id          INTEGER PRIMARY KEY,
    company     TEXT NOT NULL,
    to_addr     TEXT NOT NULL,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'outreach' CHECK (kind IN ('outreach', 'follow_up', 'pass_note', 'reply')),
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'sent', 'cancelled')),
    approval_id INTEGER REFERENCES approvals(id),
    dry_run     INTEGER NOT NULL DEFAULT 1 CHECK (dry_run IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    sent_at     TEXT
);

CREATE TRIGGER IF NOT EXISTS outbox_insert_draft_only
BEFORE INSERT ON outbox
WHEN NEW.status <> 'draft' OR NEW.approval_id IS NOT NULL OR NEW.sent_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'outbox rows must be inserted as unapproved drafts'); END;

CREATE TRIGGER IF NOT EXISTS outbox_no_content_change_after_draft
BEFORE UPDATE ON outbox
WHEN OLD.status <> 'draft'
 AND (NEW.to_addr IS NOT OLD.to_addr OR NEW.subject IS NOT OLD.subject OR NEW.body IS NOT OLD.body
      OR NEW.company IS NOT OLD.company)
BEGIN SELECT RAISE(ABORT, 'approved or sent email content cannot change'); END;

CREATE TRIGGER IF NOT EXISTS outbox_requires_approval
BEFORE UPDATE OF status ON outbox
WHEN NEW.status IN ('approved', 'sent')
 AND NOT EXISTS (SELECT 1 FROM approvals a
                 WHERE a.id = NEW.approval_id AND a.action_type = 'send_email'
                   AND a.target_id = NEW.id AND a.revoked_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'send blocked: no valid approval recorded for this email'); END;

CREATE TRIGGER IF NOT EXISTS outbox_sent_requires_allowed_recipient
BEFORE UPDATE OF status ON outbox
WHEN NEW.status = 'sent'
 AND NOT EXISTS (SELECT 1 FROM allowed_recipients r WHERE r.address = lower(trim(NEW.to_addr)))
BEGIN SELECT RAISE(ABORT, 'send blocked: recipient is not an allowed placeholder address'); END;

CREATE TRIGGER IF NOT EXISTS outbox_sent_only_from_approved
BEFORE UPDATE OF status ON outbox
WHEN NEW.status = 'sent' AND OLD.status <> 'approved'
BEGIN SELECT RAISE(ABORT, 'send blocked: email must be approved before it is sent'); END;

CREATE TABLE IF NOT EXISTS calendar_holds (
    id          INTEGER PRIMARY KEY,
    company     TEXT NOT NULL,
    start_at    TEXT NOT NULL,
    minutes     INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'held', 'cancelled')),
    approval_id INTEGER REFERENCES approvals(id),
    ics_path    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS holds_insert_proposed_only
BEFORE INSERT ON calendar_holds
WHEN NEW.status <> 'proposed' OR NEW.approval_id IS NOT NULL OR NEW.ics_path IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'calendar holds must be inserted as unapproved proposals'); END;

CREATE TRIGGER IF NOT EXISTS holds_require_approval
BEFORE UPDATE ON calendar_holds
WHEN (NEW.status = 'held' OR NEW.ics_path IS NOT NULL)
 AND NOT EXISTS (SELECT 1 FROM approvals a
                 WHERE a.id = NEW.approval_id AND a.action_type = 'create_calendar_hold'
                   AND a.target_id = NEW.id AND a.revoked_at IS NULL)
BEGIN SELECT RAISE(ABORT, 'calendar hold blocked: no valid approval recorded'); END;

-- Human gate on outcomes: the model recommends, a named human decides.
CREATE TABLE IF NOT EXISTS outcomes (
    id                   INTEGER PRIMARY KEY,
    company              TEXT NOT NULL,
    model_band           TEXT NOT NULL,
    model_recommendation TEXT NOT NULL,
    human_decision       TEXT CHECK (human_decision IN ('call', 'pass', 'hold', 'review_more')),
    decided_by           TEXT,
    decided_at           TEXT,
    reason               TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS outcomes_insert_undecided
BEFORE INSERT ON outcomes
WHEN NEW.human_decision IS NOT NULL OR NEW.decided_by IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'outcomes are created undecided; a human decides later'); END;

CREATE TRIGGER IF NOT EXISTS outcomes_human_only
BEFORE UPDATE OF human_decision, decided_by ON outcomes
WHEN NEW.human_decision IS NOT NULL
 AND (NEW.decided_by IS NULL OR length(trim(NEW.decided_by)) = 0
      OR lower(trim(NEW.decided_by)) IN ('model', 'system', 'auto', 'claude')
      OR NEW.reason IS NULL OR length(trim(NEW.reason)) = 0)
BEGIN SELECT RAISE(ABORT, 'decision blocked: needs a named human and a one-line reason'); END;

-- Corrections log (Stage 6).
CREATE TABLE IF NOT EXISTS corrections (
    id           INTEGER PRIMARY KEY,
    company      TEXT NOT NULL,
    sector       TEXT,
    criterion    TEXT NOT NULL,
    model_score  INTEGER NOT NULL CHECK (model_score BETWEEN 0 AND 5),
    human_score  INTEGER NOT NULL CHECK (human_score BETWEEN 0 AND 5),
    reason       TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    corrected_by TEXT NOT NULL CHECK (length(trim(corrected_by)) > 0),
    corrected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS corrections_human_only
BEFORE INSERT ON corrections
WHEN lower(trim(NEW.corrected_by)) IN ('model', 'system', 'auto', 'claude')
  OR NEW.model_score = NEW.human_score
  OR instr(NEW.reason, char(10)) > 0
BEGIN SELECT RAISE(ABORT, 'correction blocked: needs a named human, a changed score, and a one-line reason'); END;

CREATE TRIGGER IF NOT EXISTS corrections_no_update
BEFORE UPDATE ON corrections
BEGIN SELECT RAISE(ABORT, 'corrections are append-only; add a new correction instead'); END;

CREATE TRIGGER IF NOT EXISTS corrections_no_delete
BEFORE DELETE ON corrections
BEGIN SELECT RAISE(ABORT, 'corrections are append-only'); END;

-- Outreach threads (Stage 7). One thread per first email; follow-ups link to it.
__THREADS__

CREATE TABLE IF NOT EXISTS thread_messages (
    thread_id  INTEGER NOT NULL REFERENCES threads(id),
    outbox_id  INTEGER NOT NULL UNIQUE REFERENCES outbox(id)
);

-- Founder replies are untrusted data: stored and labelled, never executed.
CREATE TABLE IF NOT EXISTS replies (
    id             INTEGER PRIMARY KEY,
    thread_id      INTEGER NOT NULL REFERENCES threads(id),
    received_at    TEXT NOT NULL,
    from_addr      TEXT NOT NULL,
    body           TEXT NOT NULL,
    classification TEXT NOT NULL CHECK (classification IN ('yes', 'no', 'reschedule', 'unclear')),
    classifier     TEXT NOT NULL,
    confirmed_by   TEXT,
    confirmed_at   TEXT,
    action         TEXT CHECK (action IN ('propose_slots', 'close_thread', 'hand_to_partner')),
    actioned_at    TEXT
);

CREATE TRIGGER IF NOT EXISTS replies_no_unclear_need_human
BEFORE UPDATE OF action ON replies
WHEN NEW.action IS NOT NULL AND NEW.classification IN ('no', 'unclear')
 AND (NEW.confirmed_by IS NULL OR length(trim(NEW.confirmed_by)) = 0
      OR lower(trim(NEW.confirmed_by)) IN ('model', 'system', 'auto', 'claude'))
BEGIN SELECT RAISE(ABORT, 'a "no" or unclear reply needs a named human to confirm before any action'); END;

CREATE TRIGGER IF NOT EXISTS replies_confirmer_human
BEFORE UPDATE OF confirmed_by ON replies
WHEN NEW.confirmed_by IS NOT NULL
 AND lower(trim(NEW.confirmed_by)) IN ('model', 'system', 'auto', 'claude', '')
BEGIN SELECT RAISE(ABORT, 'confirmation needs a named human'); END;

CREATE TRIGGER IF NOT EXISTS replies_body_immutable
BEFORE UPDATE OF body, from_addr, received_at ON replies
BEGIN SELECT RAISE(ABORT, 'reply content is a record and cannot change'); END;

-- Out-of-sample test (after Stage 7). A batch's scores are frozen before partners decide; evaluated once.
CREATE TABLE IF NOT EXISTS oos_batches (
    batch      TEXT PRIMARY KEY CHECK (length(trim(batch)) > 0),
    frozen_at  TEXT NOT NULL,
    frozen_by  TEXT NOT NULL CHECK (length(trim(frozen_by)) > 0),
    bar        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oos_members (
    batch      TEXT NOT NULL REFERENCES oos_batches(batch),
    company    TEXT NOT NULL UNIQUE,
    band       TEXT NOT NULL,
    total      REAL NOT NULL,
    score_json TEXT NOT NULL,
    score_sha  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oos_results (
    batch        TEXT PRIMARY KEY REFERENCES oos_batches(batch),
    evaluated_at TEXT NOT NULL,
    result_json  TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS oos_batches_frozen BEFORE UPDATE ON oos_batches
BEGIN SELECT RAISE(ABORT, 'a frozen batch cannot change'); END;
CREATE TRIGGER IF NOT EXISTS oos_batches_keep BEFORE DELETE ON oos_batches
BEGIN SELECT RAISE(ABORT, 'a frozen batch cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS oos_members_frozen BEFORE UPDATE ON oos_members
BEGIN SELECT RAISE(ABORT, 'frozen scores cannot change'); END;
CREATE TRIGGER IF NOT EXISTS oos_members_keep BEFORE DELETE ON oos_members
BEGIN SELECT RAISE(ABORT, 'frozen scores cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS oos_results_once BEFORE UPDATE ON oos_results
BEGIN SELECT RAISE(ABORT, 'a batch is evaluated once'); END;
CREATE TRIGGER IF NOT EXISTS oos_results_keep BEFORE DELETE ON oos_results
BEGIN SELECT RAISE(ABORT, 'results cannot be deleted'); END;

-- Weight-change proposals (Stage 6). Never applied by code; a human edits config/rubric.yaml.
CREATE TABLE IF NOT EXISTS weight_proposals (
    id             INTEGER PRIMARY KEY,
    criterion      TEXT NOT NULL,
    direction      TEXT NOT NULL CHECK (direction IN ('up', 'down')),
    correction_ids TEXT NOT NULL,
    diff           TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'accepted', 'rejected')),
    decided_by     TEXT,
    decided_at     TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS proposals_insert_proposed
BEFORE INSERT ON weight_proposals
WHEN NEW.status <> 'proposed' OR NEW.decided_by IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'proposals are created undecided'); END;

CREATE TRIGGER IF NOT EXISTS proposals_human_decides
BEFORE UPDATE OF status ON weight_proposals
WHEN NEW.status <> 'proposed'
 AND (NEW.decided_by IS NULL OR length(trim(NEW.decided_by)) = 0
      OR lower(trim(NEW.decided_by)) IN ('model', 'system', 'auto', 'claude'))
BEGIN SELECT RAISE(ABORT, 'proposal decisions need a named human'); END;
"""


FEEDBACK_SCHEMA = """
-- Feedback loop (lecture 24 Nov). Riya's email edits: one row per edit, never overwritten, so the system's
-- draft and what she approved are both kept. One edit = one reason = one scope (no bundling of exceptions).
CREATE TABLE IF NOT EXISTS email_edits (
    id            INTEGER PRIMARY KEY,
    outbox_id     INTEGER NOT NULL REFERENCES outbox(id),
    company       TEXT NOT NULL,
    sector        TEXT,
    before_subject TEXT NOT NULL,
    before_body   TEXT NOT NULL,
    after_subject TEXT NOT NULL,
    after_body    TEXT NOT NULL,
    change_ratio  REAL NOT NULL CHECK (change_ratio BETWEEN 0 AND 1),
    reason        TEXT NOT NULL CHECK (length(trim(reason)) > 0 AND instr(reason, char(10)) = 0),
    scope         TEXT NOT NULL CHECK (scope IN ('general', 'this_case')),
    edited_by     TEXT NOT NULL,
    edited_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TRIGGER IF NOT EXISTS email_edits_human_only
BEFORE INSERT ON email_edits
WHEN length(trim(NEW.edited_by)) = 0 OR lower(trim(NEW.edited_by)) IN ('model', 'system', 'auto', 'claude')
BEGIN SELECT RAISE(ABORT, 'email edit blocked: needs a named human'); END;
CREATE TRIGGER IF NOT EXISTS email_edits_no_update BEFORE UPDATE ON email_edits
BEGIN SELECT RAISE(ABORT, 'email edits are append-only'); END;
CREATE TRIGGER IF NOT EXISTS email_edits_no_delete BEFORE DELETE ON email_edits
BEGIN SELECT RAISE(ABORT, 'email edits are append-only'); END;

-- A named human can flag a piece of feedback as a bad-day edit or retract it; flagged feedback is never reused.
CREATE TABLE IF NOT EXISTS feedback_flags (
    id         INTEGER PRIMARY KEY,
    target     TEXT NOT NULL CHECK (target IN ('correction', 'email_edit')),
    target_id  INTEGER NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('bad_day', 'retracted')),
    reason     TEXT NOT NULL CHECK (length(trim(reason)) > 0 AND instr(reason, char(10)) = 0),
    flagged_by TEXT NOT NULL,
    flagged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TRIGGER IF NOT EXISTS feedback_flags_human_only
BEFORE INSERT ON feedback_flags
WHEN length(trim(NEW.flagged_by)) = 0 OR lower(trim(NEW.flagged_by)) IN ('model', 'system', 'auto', 'claude')
BEGIN SELECT RAISE(ABORT, 'flag blocked: needs a named human'); END;
CREATE TRIGGER IF NOT EXISTS feedback_flags_no_update BEFORE UPDATE ON feedback_flags
BEGIN SELECT RAISE(ABORT, 'flags are append-only'); END;
CREATE TRIGGER IF NOT EXISTS feedback_flags_no_delete BEFORE DELETE ON feedback_flags
BEGIN SELECT RAISE(ABORT, 'flags are append-only'); END;
"""


QUEUE_SCHEMA = """
-- Application queue (case Task 2). Every application ends scored, queued, or needs_attention with a reason.
-- Rows are never deleted, so none can disappear; every status change is logged in job_events.
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY,
    batch       TEXT NOT NULL,
    label       TEXT NOT NULL,
    company     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'scored', 'needs_attention')),
    reason      TEXT,
    attempts    INTEGER NOT NULL DEFAULT 0,
    cost_inr    REAL NOT NULL DEFAULT 0,
    trace_id    TEXT,
    queued_at   TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT,
    UNIQUE (batch, label)
);
CREATE TRIGGER IF NOT EXISTS jobs_no_delete BEFORE DELETE ON jobs
BEGIN SELECT RAISE(ABORT, 'jobs are never deleted: every application must be accounted for'); END;
CREATE TRIGGER IF NOT EXISTS jobs_attention_needs_reason BEFORE UPDATE OF status ON jobs
WHEN NEW.status = 'needs_attention' AND (NEW.reason IS NULL OR length(trim(NEW.reason)) = 0)
BEGIN SELECT RAISE(ABORT, 'needs_attention requires a reason'); END;
CREATE TABLE IF NOT EXISTS job_events (
    id     INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    at     TEXT NOT NULL,
    status TEXT NOT NULL,
    note   TEXT
);
CREATE TRIGGER IF NOT EXISTS job_events_no_update BEFORE UPDATE ON job_events
BEGIN SELECT RAISE(ABORT, 'job events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS job_events_no_delete BEFORE DELETE ON job_events
BEGIN SELECT RAISE(ABORT, 'job events are append-only'); END;
"""


AI_SCHEMA = """
-- Every model call, metered (lecture 19 Nov: know where every rupee goes before production). Append-only.
CREATE TABLE IF NOT EXISTS ai_calls (
    id                 INTEGER PRIMARY KEY,
    at                 TEXT NOT NULL,
    day                TEXT NOT NULL,             -- IST date, for the daily limits
    task               TEXT NOT NULL,
    company            TEXT,
    model              TEXT NOT NULL,
    gateway            TEXT NOT NULL,             -- anthropic | portkey | cache | test
    input_tokens       INTEGER NOT NULL DEFAULT 0,
    output_tokens      INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    web_searches       INTEGER NOT NULL DEFAULT 0,
    cost_usd           REAL NOT NULL DEFAULT 0,
    cost_inr           REAL NOT NULL DEFAULT 0,
    latency_ms         INTEGER,
    status             TEXT NOT NULL CHECK (status IN ('ok', 'cached', 'error', 'blocked')),
    request_id         TEXT,
    trace_id           TEXT,
    error              TEXT
);
CREATE TRIGGER IF NOT EXISTS ai_calls_no_update BEFORE UPDATE ON ai_calls
BEGIN SELECT RAISE(ABORT, 'ai_calls is a ledger: append only'); END;
CREATE TRIGGER IF NOT EXISTS ai_calls_no_delete BEFORE DELETE ON ai_calls
BEGIN SELECT RAISE(ABORT, 'ai_calls is a ledger: append only'); END;

-- Response cache: the same request never pays twice.
CREATE TABLE IF NOT EXISTS llm_cache (
    key        TEXT PRIMARY KEY,
    model      TEXT NOT NULL,
    response   TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Alerts and the kill switch. Latest row per day decides; only a named human can release a stop.
CREATE TABLE IF NOT EXISTS spend_events (
    id      INTEGER PRIMARY KEY,
    at      TEXT NOT NULL,
    day     TEXT NOT NULL,
    kind    TEXT NOT NULL CHECK (kind IN ('alert', 'stop', 'manual_stop', 'release')),
    spend_inr REAL NOT NULL,
    by      TEXT NOT NULL,
    note    TEXT
);
CREATE TRIGGER IF NOT EXISTS spend_release_human BEFORE INSERT ON spend_events
WHEN NEW.kind = 'release' AND lower(trim(NEW.by)) IN ('model', 'system', 'auto', 'claude', '')
BEGIN SELECT RAISE(ABORT, 'only a named human can release the kill switch'); END;
CREATE TRIGGER IF NOT EXISTS spend_events_no_update BEFORE UPDATE ON spend_events
BEGIN SELECT RAISE(ABORT, 'spend_events is append only'); END;
CREATE TRIGGER IF NOT EXISTS spend_events_no_delete BEFORE DELETE ON spend_events
BEGIN SELECT RAISE(ABORT, 'spend_events is append only'); END;
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring an existing DB up to the current schema without losing rows."""
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='threads'").fetchone()[0]
    if "BETWEEN 0 AND 3" not in sql:          # follow-up cap 2 -> 3 and 'no_reply' status (user 2026-11-20)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(THREADS_DDL.format(name="threads_new") +
                           "INSERT INTO threads_new (id, company, root_outbox_id, status, followups_sent, created_at) "
                           "SELECT id, company, root_outbox_id, status, followups_sent, created_at FROM threads;"
                           "DROP TABLE threads; ALTER TABLE threads_new RENAME TO threads;")
        conn.execute("PRAGMA foreign_keys = ON")
    for table, col, ddl in (("replies", "requested_slot", "TEXT"), ("calendar_holds", "attendees", "TEXT"),
                            ("corrections", "scope", "TEXT NOT NULL DEFAULT 'general' CHECK (scope IN ('general', 'this_case'))"),
                            ("ai_calls", "prompt_version", "TEXT"), ("ai_calls", "pii_redacted", "INTEGER NOT NULL DEFAULT 0")):
        if col not in [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    conn.commit()


def connect(path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Open the DB with foreign keys on and the schema applied. Use ':memory:' in tests."""
    target = str(path) if path is not None else str(DEFAULT_DB)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.replace("__THREADS__", THREADS_DDL.format(name="threads")) + AI_SCHEMA + FEEDBACK_SCHEMA + QUEUE_SCHEMA)
    _migrate(conn)
    return conn
