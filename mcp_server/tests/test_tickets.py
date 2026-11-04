"""Tests for the ticket tools.

Every test runs against a temporary copy of the original database. The
fixture points the server at that copy through CAMPUS_DB_PATH and, when the
test ends, checks that the original file's hash has not changed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from mcp_server import db, tickets

ORIGINAL = db.ORIGINAL_DB_PATH


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def work_db(tmp_path, monkeypatch):
    """A temporary copy of the original, with the tools pointed at it."""
    target = tmp_path / "campus_customs_test.db"
    shutil.copyfile(ORIGINAL, target)
    monkeypatch.setenv("CAMPUS_DB_PATH", str(target))
    before = sha256(ORIGINAL)
    yield target
    assert sha256(ORIGINAL) == before, "the original database was modified"


# --------------------------------------------------------------------------
# The database layer
# --------------------------------------------------------------------------


def test_refuses_to_open_the_original(monkeypatch):
    monkeypatch.setenv("CAMPUS_DB_PATH", str(ORIGINAL))
    with pytest.raises(RuntimeError, match="untouched original"):
        db.db_path()


def test_schema_additions_are_applied_to_the_copy_only(work_db):
    with db.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tickets)")}
        assert {"assigned_to", "priority", "resolution", "updated_at"} <= columns
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "ticket_events" in tables
        assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM ticket_events").fetchone()[0] == 0


def test_shop_today_comes_from_the_desk(work_db):
    with db.connect() as conn:
        assert db.shop_today(conn) == "2026-08-31"


def test_a_failing_call_is_rolled_back(work_db):
    with pytest.raises(RuntimeError):
        with db.connect() as conn:
            tickets.add_ticket_note(conn, 101, "this note must not survive", "boss")
            raise RuntimeError("something went wrong after the write")
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ticket_events").fetchone()[0] == 0


# --------------------------------------------------------------------------
# Reading tickets
# --------------------------------------------------------------------------


def test_list_tickets_returns_the_seed(work_db):
    with db.connect() as conn:
        rows = tickets.list_tickets(conn)
        assert [row["id"] for row in rows] == [101, 102, 103]
        assert {row["status"] for row in rows} == {"open"}
        assert tickets.list_tickets(conn, "resolved") == []
        assert len(tickets.list_tickets(conn, "open")) == 3
        with pytest.raises(ValueError, match="Unknown status"):
            tickets.list_tickets(conn, "done")


def test_ticket_101_links_to_its_invoice_vendor_stock_and_pricing(work_db):
    with db.connect() as conn:
        ticket = tickets.get_ticket(conn, 101)
    assert ticket["type"] == "customer_order"
    assert ticket["requester"] == "Tauhid Zaman"
    assert ticket["shop_today"] == "2026-08-31"
    invoice = ticket["links"]["invoice"]
    assert invoice["id"] == 501
    assert invoice["vendor_name"] == "Bulldog Print Co"
    assert invoice["vendor_lead_days"] == 5
    assert invoice["amount"] == 840.0
    assert invoice["status"] == "open"
    assert invoice["days_overdue"] == 3  # due 2026-08-28, shop today 2026-08-31
    assert ticket["links"]["lease"] is None
    stock = ticket["links"]["stock"]
    assert [row["size"] for row in stock] == ["S", "M", "L", "XL"]
    requested = [row for row in stock if row["requested_size"]]
    assert len(requested) == 1 and requested[0]["size"] == "S" and requested[0]["qty"] == 0
    assert ticket["links"]["pricing"] == {"sku": "CC-TEE-WHITE", "unit_cost": 8.0, "list_price": 28.0}


def test_ticket_102_links_to_the_lease(work_db):
    with db.connect() as conn:
        ticket = tickets.get_ticket(conn, 102)
    lease = ticket["links"]["lease"]
    assert lease["id"] == 1
    assert lease["landlord"] == "Elm City Properties"
    assert lease["monthly_rent"] == 2400.0
    assert lease["next_due"] == "2026-09-02"
    assert lease["days_until_due"] == 2
    assert ticket["links"]["invoice"] is None
    assert ticket["links"]["stock"] == []
    assert ticket["links"]["pricing"] is None


def test_ticket_103_links_to_the_hoodie_stock(work_db):
    with db.connect() as conn:
        ticket = tickets.get_ticket(conn, 103)
    assert ticket["qty"] == 20
    requested = [row for row in ticket["links"]["stock"] if row["requested_size"]]
    assert requested[0]["size"] == "M" and requested[0]["qty"] == 8
    assert ticket["links"]["pricing"]["unit_cost"] == 22.0
    assert ticket["links"]["invoice"] is None and ticket["links"]["lease"] is None


def test_get_ticket_refuses_a_missing_id(work_db):
    with db.connect() as conn:
        with pytest.raises(ValueError, match="Ticket 999 does not exist"):
            tickets.get_ticket(conn, 999)


# --------------------------------------------------------------------------
# Writing tickets
# --------------------------------------------------------------------------


def test_open_ticket_adds_a_row_and_an_event(work_db):
    with db.connect() as conn:
        ticket = tickets.open_ticket(
            conn,
            type="restock",
            requester="Inventory agent",
            subject="Crest Mug is sold out",
            notes="CC-MUG-CREST OS is at 0.",
            sku="CC-MUG-CREST",
            size="OS",
            qty=24,
            agent="inventory",
        )
    assert ticket["id"] == 104
    assert ticket["status"] == "open"
    assert ticket["assigned_to"] is None and ticket["priority"] is None
    assert ticket["created_at"].startswith("2026-08-31T") and ticket["created_at"].endswith("-04:00")
    assert ticket["links"]["stock"][0]["qty"] == 0
    with db.connect() as conn:
        assert len(tickets.list_tickets(conn)) == 4
        events = tickets.list_ticket_events(conn, 104)
    assert len(events) == 1
    assert events[0]["agent"] == "inventory" and events[0]["kind"] == "opened"
    assert events[0]["data"] == {"type": "restock", "requester": "Inventory agent"}


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(sku="CC-NOPE"), "No inventory rows for sku"),
        (dict(sku="CC-TEE-WHITE", size="XXL"), "No inventory row for sku"),
        (dict(size="M"), "A size needs a sku"),
        (dict(lease_id=9), "Lease 9 does not exist"),
        (dict(invoice_id=9), "Invoice 9 does not exist"),
        (dict(qty=0), "qty must be a positive"),
        (dict(subject="   "), "'subject' is required"),
        (dict(agent="intern"), "Unknown agent 'intern'"),
    ],
)
def test_open_ticket_refuses_bad_input(work_db, kwargs, message):
    base = dict(type="customer_order", requester="Someone", subject="Something", agent="boss")
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        with db.connect() as conn:
            tickets.open_ticket(conn, **base)
    with db.connect() as conn:
        assert len(tickets.list_tickets(conn)) == 3


def test_assign_and_prioritise(work_db):
    with db.connect() as conn:
        ticket = tickets.assign_ticket(conn, 101, "inventory", "boss")
        assert ticket["assigned_to"] == "inventory"
        assert ticket["status"] == "in_progress"
        with pytest.raises(ValueError, match="Cannot assign to 'intern'"):
            tickets.assign_ticket(conn, 101, "intern", "boss")
        tickets.set_ticket_priority(conn, 103, 1, "boss")
        tickets.set_ticket_priority(conn, 102, 2, "boss")
        with pytest.raises(ValueError, match="priority must be 1 or more"):
            tickets.set_ticket_priority(conn, 101, 0, "boss")
        order = [row["id"] for row in tickets.list_tickets(conn)]
    assert order == [103, 102, 101]  # prioritised first, unranked last


def test_status_changes_and_notes_are_logged_in_order(work_db):
    with db.connect() as conn:
        tickets.assign_ticket(conn, 102, "facilities", "boss")
        tickets.add_ticket_note(conn, 102, "Lease confirmed: $2,400 due 2026-09-02.", "facilities")
        ticket = tickets.set_ticket_status(conn, 102, "waiting_approval", "accounting")
        assert ticket["status"] == "waiting_approval"
        with pytest.raises(ValueError, match="Use resolve_ticket"):
            tickets.set_ticket_status(conn, 102, "resolved", "boss")
        with pytest.raises(ValueError, match="Unknown status"):
            tickets.set_ticket_status(conn, 102, "closed", "boss")
        events = tickets.list_ticket_events(conn, 102)
        assert [(e["agent"], e["kind"]) for e in events] == [
            ("boss", "assigned"),
            ("facilities", "note"),
            ("accounting", "status"),
        ]
        assert events[2]["data"] == {"from": "in_progress", "to": "waiting_approval"}
        later = tickets.list_ticket_events(conn, since_id=events[0]["id"])
        assert [e["id"] for e in later] == [events[1]["id"], events[2]["id"]]


def test_resolve_then_reopen(work_db):
    with db.connect() as conn:
        ticket = tickets.resolve_ticket(conn, 102, "Rent paid; see payment 1.", "boss")
        assert ticket["status"] == "resolved"
        assert ticket["resolution"] == "Rent paid; see payment 1."
        with pytest.raises(ValueError, match="already resolved"):
            tickets.resolve_ticket(conn, 102, "again", "boss")
        with pytest.raises(ValueError, match="is resolved"):
            tickets.assign_ticket(conn, 102, "facilities", "boss")
        reopened = tickets.set_ticket_status(conn, 102, "open", "human")
        assert reopened["status"] == "open" and reopened["resolution"] is None
        last = tickets.list_ticket_events(conn, 102)[-1]
        assert last["data"]["cleared_resolution"] == "Rent paid; see payment 1."


# --------------------------------------------------------------------------
# Through MCP, in memory (no server process)
# --------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "get_today",
    "list_tickets",
    "get_ticket",
    "list_ticket_events",
    "open_ticket",
    "assign_ticket",
    "set_ticket_priority",
    "set_ticket_status",
    "add_ticket_note",
    "resolve_ticket",
    # part 2
    "get_stock",
    "list_stock",
    "get_pricing",
    "list_vendors",
    "list_invoices",
    "get_lease",
    # added at the back end step so an agent can look one record up without a ticket link
    "get_vendor",
    "get_invoice",
    "list_leases",
    "get_cash",
    "list_payments",
    "list_purchase_orders",
    "create_purchase_order",
    "list_approvals",
    "request_approval",
    "decide_approval",
    "pay",
    "draft_customer_message",
    "list_drafts",
    # back end audit trail (hidden from the agents by the back end)
    "log_event",
}


def _payload(result):
    """The tool's return value, whichever way the client version exposes it."""
    data = getattr(result, "data", None)
    if data is not None:
        return data
    return json.loads(result.content[0].text)


def test_tools_are_exposed_over_mcp(work_db):
    fastmcp = pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError

    from mcp_server.server import mcp

    async def run():
        async with fastmcp.Client(mcp) as client:
            names = {tool.name for tool in await client.list_tools()}
            today = _payload(await client.call_tool("get_today", {}))
            listed = _payload(await client.call_tool("list_tickets", {}))
            with pytest.raises(ToolError, match="Ticket 999 does not exist"):
                await client.call_tool("get_ticket", {"ticket_id": 999})
            note = _payload(await client.call_tool("add_ticket_note", {"ticket_id": 103, "note": "Checked stock.", "agent": "inventory"}))
            return names, today, listed, note

    names, today, listed, note = asyncio.run(run())
    assert names == EXPECTED_TOOLS
    assert today["date_today"] == "2026-08-31"
    assert [row["id"] for row in listed] == [101, 102, 103]
    assert note["kind"] == "note" and note["ticket_id"] == 103
