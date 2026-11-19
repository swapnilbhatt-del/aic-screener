"""The approval gate must hold at the database level: a send or hold without approval must fail."""
import sqlite3

import pytest

from aic import db

PLACEHOLDER = "test-inbox@placeholder.test"
DECK_ADDRESS = "hello@yatrika.example"  # an address found in a deck: must never be sendable


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def draft(conn, to=PLACEHOLDER):
    cur = conn.execute(
        "INSERT INTO outbox (company, to_addr, subject, body) VALUES ('Pumpwise', ?, 's', 'b')", (to,))
    return cur.lastrowid


def approve(conn, target, action="send_email", by="Kushal"):
    cur = conn.execute(
        "INSERT INTO approvals (action_type, target_id, approved_by) VALUES (?, ?, ?)", (action, target, by))
    return cur.lastrowid


def allow(conn, addr=PLACEHOLDER):
    conn.execute("INSERT INTO allowed_recipients (address, added_by) VALUES (?, 'Swapnil')", (addr,))


def blocked(conn, sql, params=()):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, params)


# --- emails ---------------------------------------------------------------

def test_send_without_approval_fails(conn):
    allow(conn)
    oid = draft(conn)
    blocked(conn, "UPDATE outbox SET status='sent' WHERE id=?", (oid,))
    blocked(conn, "UPDATE outbox SET status='approved' WHERE id=?", (oid,))


def test_insert_as_sent_or_approved_fails(conn):
    blocked(conn, "INSERT INTO outbox (company,to_addr,subject,body,status) VALUES ('X',?,'s','b','sent')", (PLACEHOLDER,))
    blocked(conn, "INSERT INTO outbox (company,to_addr,subject,body,status) VALUES ('X',?,'s','b','approved')", (PLACEHOLDER,))


def test_approval_for_a_different_email_does_not_count(conn):
    allow(conn)
    a, b = draft(conn), draft(conn)
    aid = approve(conn, a)
    blocked(conn, "UPDATE outbox SET status='approved', approval_id=? WHERE id=?", (aid, b))


def test_approval_for_wrong_action_type_does_not_count(conn):
    oid = draft(conn)
    aid = approve(conn, oid, action="create_calendar_hold")
    blocked(conn, "UPDATE outbox SET status='approved', approval_id=? WHERE id=?", (aid, oid))


def test_revoked_approval_does_not_count(conn):
    allow(conn)
    oid = draft(conn)
    aid = approve(conn, oid)
    conn.execute("UPDATE approvals SET revoked_at=datetime('now') WHERE id=?", (aid,))
    blocked(conn, "UPDATE outbox SET status='approved', approval_id=? WHERE id=?", (aid, oid))


def test_cannot_skip_approved_state(conn):
    allow(conn)
    oid = draft(conn)
    aid = approve(conn, oid)
    blocked(conn, "UPDATE outbox SET status='sent', approval_id=? WHERE id=?", (aid, oid))


def test_approved_email_to_non_placeholder_cannot_be_sent(conn):
    allow(conn)
    oid = draft(conn, to=DECK_ADDRESS)
    aid = approve(conn, oid)
    conn.execute("UPDATE outbox SET status='approved', approval_id=? WHERE id=?", (aid, oid))
    blocked(conn, "UPDATE outbox SET status='sent' WHERE id=?", (oid,))


def test_empty_allowlist_blocks_every_send(conn):
    oid = draft(conn)
    aid = approve(conn, oid)
    conn.execute("UPDATE outbox SET status='approved', approval_id=? WHERE id=?", (aid, oid))
    blocked(conn, "UPDATE outbox SET status='sent' WHERE id=?", (oid,))


def test_content_cannot_change_after_approval(conn):
    oid = draft(conn)
    aid = approve(conn, oid)
    conn.execute("UPDATE outbox SET status='approved', approval_id=? WHERE id=?", (aid, oid))
    blocked(conn, "UPDATE outbox SET body='different' WHERE id=?", (oid,))
    blocked(conn, "UPDATE outbox SET to_addr=? WHERE id=?", (DECK_ADDRESS, oid))


def test_full_happy_path(conn):
    allow(conn)
    oid = draft(conn)
    aid = approve(conn, oid)
    conn.execute("UPDATE outbox SET status='approved', approval_id=? WHERE id=?", (aid, oid))
    conn.execute("UPDATE outbox SET status='sent', sent_at=datetime('now') WHERE id=?", (oid,))
    assert conn.execute("SELECT status FROM outbox WHERE id=?", (oid,)).fetchone()[0] == "sent"


# --- approvals table ------------------------------------------------------

@pytest.mark.parametrize("by", ["", "  ", "model", "System", "auto", "claude"])
def test_approval_needs_named_human(conn, by):
    blocked(conn, "INSERT INTO approvals (action_type,target_id,approved_by) VALUES ('send_email',1,?)", (by,))


def test_approvals_are_append_only(conn):
    aid = approve(conn, 1)
    blocked(conn, "DELETE FROM approvals WHERE id=?", (aid,))
    blocked(conn, "UPDATE approvals SET target_id=2 WHERE id=?", (aid,))
    blocked(conn, "UPDATE approvals SET approved_by='Riya' WHERE id=?", (aid,))
    conn.execute("UPDATE approvals SET revoked_at=datetime('now') WHERE id=?", (aid,))
    blocked(conn, "UPDATE approvals SET revoked_at=NULL WHERE id=?", (aid,))


# --- calendar holds -------------------------------------------------------

def hold(conn):
    return conn.execute(
        "INSERT INTO calendar_holds (company,start_at,minutes) VALUES ('Pumpwise','2026-11-24T14:00+05:30',30)"
    ).lastrowid


def test_hold_without_approval_fails(conn):
    hid = hold(conn)
    blocked(conn, "UPDATE calendar_holds SET status='held' WHERE id=?", (hid,))
    blocked(conn, "UPDATE calendar_holds SET ics_path='x.ics' WHERE id=?", (hid,))


def test_insert_hold_as_held_fails(conn):
    blocked(conn, "INSERT INTO calendar_holds (company,start_at,minutes,status) VALUES ('X','t',30,'held')")


def test_hold_with_email_approval_fails(conn):
    hid = hold(conn)
    aid = approve(conn, hid, action="send_email")
    blocked(conn, "UPDATE calendar_holds SET status='held', approval_id=? WHERE id=?", (aid, hid))


def test_hold_with_approval_succeeds(conn):
    hid = hold(conn)
    aid = approve(conn, hid, action="create_calendar_hold")
    conn.execute("UPDATE calendar_holds SET status='held', approval_id=?, ics_path='h.ics' WHERE id=?", (aid, hid))


# --- human decision gate --------------------------------------------------

def outcome(conn):
    return conn.execute(
        "INSERT INTO outcomes (company, model_band, model_recommendation) VALUES ('Pumpwise','call','Move to call')"
    ).lastrowid


def test_outcome_cannot_be_created_decided(conn):
    blocked(conn, "INSERT INTO outcomes (company,model_band,model_recommendation,human_decision,decided_by) "
                  "VALUES ('X','pass','Pass','pass','Kushal')")


@pytest.mark.parametrize("by", [None, "", "model", "system", "auto"])
def test_outcome_needs_named_human(conn, by):
    oid = outcome(conn)
    blocked(conn, "UPDATE outcomes SET human_decision='pass', decided_by=?, reason='r' WHERE id=?", (by, oid))


def test_outcome_needs_reason(conn):
    oid = outcome(conn)
    blocked(conn, "UPDATE outcomes SET human_decision='pass', decided_by='Kushal' WHERE id=?", (oid,))


def test_outcome_decided_by_human(conn):
    oid = outcome(conn)
    conn.execute("UPDATE outcomes SET human_decision='call', decided_by='Kushal', reason='strong field evidence', "
                 "decided_at=datetime('now') WHERE id=?", (oid,))
