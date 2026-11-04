"""Ticket tools: the shop's inbox and board.

Every function takes an open connection (see ``db.connect``) and returns plain
dicts, so ``server.py`` can stay a thin MCP wrapper and the tests can call
these directly on a temporary copy of the database.

Nothing here invents data. Every value returned is a column from the database
or arithmetic on such columns (days overdue, days until due). Every write is
also recorded in ``ticket_events`` so the board can show who did what.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from mcp_server import db

# The five agents, plus the two non-agent actors that can touch a ticket.
AGENTS = ("boss", "inventory", "accounting", "facilities", "customer_service")
ACTORS = AGENTS + ("human", "system")

# Ticket statuses. "resolved" is reached only through resolve_ticket.
OPEN_STATUSES = ("open", "in_progress", "waiting_approval")
TICKET_STATUSES = OPEN_STATUSES + ("resolved",)

# The seed's created_at values carry this offset (New Haven in August).
SHOP_UTC_OFFSET = "-04:00"


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------


def _require_actor(agent: str) -> str:
    if agent not in ACTORS:
        raise ValueError(f"Unknown agent '{agent}'. Known agents: {', '.join(ACTORS)}.")
    return agent


def _require_text(name: str, value: str | None) -> str:
    if value is None or not value.strip():
        raise ValueError(f"'{name}' is required and cannot be blank.")
    return value.strip()


def _ticket_row(conn: sqlite3.Connection, ticket_id: int) -> dict:
    row = db.one(conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)))
    if row is None:
        raise ValueError(f"Ticket {ticket_id} does not exist.")
    return row


def _days_between(from_date: str, to_date: str) -> int:
    """Whole days from one ISO date to another; the time part, if any, is ignored."""
    return (date.fromisoformat(to_date[:10]) - date.fromisoformat(from_date[:10])).days


# --------------------------------------------------------------------------
# The activity feed
# --------------------------------------------------------------------------


def log_event(
    conn: sqlite3.Connection,
    agent: str,
    kind: str,
    message: str,
    ticket_id: int | None = None,
    data: dict | None = None,
) -> dict:
    """Append one row to ticket_events and return it."""
    _require_actor(agent)
    kind = _require_text("kind", kind)
    message = _require_text("message", message)
    if ticket_id is not None:
        _ticket_row(conn, ticket_id)
    cursor = conn.execute(
        "INSERT INTO ticket_events (ticket_id, agent, kind, message, data, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (ticket_id, agent, kind, message, json.dumps(data) if data is not None else None, db.now_iso()),
    )
    return _event_row(conn, cursor.lastrowid)


def _event_row(conn: sqlite3.Connection, event_id: int) -> dict:
    row = db.one(conn.execute("SELECT * FROM ticket_events WHERE id = ?", (event_id,)))
    assert row is not None
    row["data"] = json.loads(row["data"]) if row["data"] else None
    return row


def list_ticket_events(
    conn: sqlite3.Connection,
    ticket_id: int | None = None,
    since_id: int | None = None,
    limit: int = 100,
) -> list[dict]:
    """Events oldest first, for one ticket or for the whole shop.

    ``since_id`` returns only events after that id, which is how a caller
    polls for new activity without re-reading the whole feed.
    """
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000.")
    clauses, params = [], []
    if ticket_id is not None:
        _ticket_row(conn, ticket_id)
        clauses.append("ticket_id = ?")
        params.append(ticket_id)
    if since_id is not None:
        clauses.append("id > ?")
        params.append(since_id)
    sql = "SELECT * FROM ticket_events"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id LIMIT ?"
    params.append(limit)
    events = db.rows(conn.execute(sql, params))
    for event in events:
        event["data"] = json.loads(event["data"]) if event["data"] else None
    return events


# --------------------------------------------------------------------------
# Reading tickets
# --------------------------------------------------------------------------


def list_tickets(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    """All tickets, or those with one status. Prioritised tickets first, then by id."""
    if status is not None and status not in TICKET_STATUSES:
        raise ValueError(f"Unknown status '{status}'. Statuses: {', '.join(TICKET_STATUSES)}.")
    sql = "SELECT * FROM tickets"
    params: tuple = ()
    if status is not None:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY CASE WHEN priority IS NULL THEN 1 ELSE 0 END, priority, id"
    return db.rows(conn.execute(sql, params))


def get_ticket(conn: sqlite3.Connection, ticket_id: int) -> dict:
    """One ticket with everything it links to.

    ``links`` holds the invoice (with its vendor and days overdue by the shop's
    clock), the lease (with days until the next due date), the inventory rows
    for the ticket's SKU (the requested size flagged), and that SKU's pricing.
    A link the ticket does not have is None (or an empty list for stock).
    """
    ticket = _ticket_row(conn, ticket_id)
    today = db.shop_today(conn)
    links: dict = {"invoice": None, "lease": None, "stock": [], "pricing": None}

    if ticket["invoice_id"] is not None:
        invoice = db.one(
            conn.execute(
                "SELECT i.*, v.name AS vendor_name, v.specialty AS vendor_specialty, v.lead_days AS vendor_lead_days "
                "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (ticket["invoice_id"],),
            )
        )
        if invoice is not None:
            overdue = _days_between(invoice["due_date"], today)
            invoice["days_overdue"] = max(0, overdue) if invoice["status"] == "open" else 0
        links["invoice"] = invoice

    if ticket["lease_id"] is not None:
        lease = db.one(conn.execute("SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)))
        if lease is not None:
            lease["days_until_due"] = _days_between(today, lease["next_due"])
        links["lease"] = lease

    if ticket["sku"]:
        stock = db.rows(conn.execute("SELECT * FROM inventory WHERE sku = ? ORDER BY rowid", (ticket["sku"],)))
        for row in stock:
            row["requested_size"] = row["size"] == ticket["size"]
        links["stock"] = stock
        links["pricing"] = db.one(conn.execute("SELECT * FROM pricing WHERE sku = ?", (ticket["sku"],)))

    ticket["shop_today"] = today
    ticket["links"] = links
    return ticket


# --------------------------------------------------------------------------
# Writing tickets
# --------------------------------------------------------------------------


def open_ticket(
    conn: sqlite3.Connection,
    *,
    type: str,
    requester: str,
    subject: str,
    notes: str | None = None,
    sku: str | None = None,
    size: str | None = None,
    qty: int | None = None,
    lease_id: int | None = None,
    invoice_id: int | None = None,
    agent: str = "human",
) -> dict:
    """Add a ticket to the board with status 'open'.

    Anything the ticket points at must exist: the SKU (and size) in inventory,
    the lease, the invoice. The created_at date is the shop's today; the time
    of day is the wall clock, written with the same offset as the seed rows.
    """
    _require_actor(agent)
    type = _require_text("type", type)
    requester = _require_text("requester", requester)
    subject = _require_text("subject", subject)
    if qty is not None and qty <= 0:
        raise ValueError("qty must be a positive whole number.")
    if size and not sku:
        raise ValueError("A size needs a sku.")
    if sku:
        if size:
            found = conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone()
            if found is None:
                raise ValueError(f"No inventory row for sku '{sku}' in size '{size}'.")
        else:
            found = conn.execute("SELECT 1 FROM inventory WHERE sku = ?", (sku,)).fetchone()
            if found is None:
                raise ValueError(f"No inventory rows for sku '{sku}'.")
    if lease_id is not None and conn.execute("SELECT 1 FROM leases WHERE id = ?", (lease_id,)).fetchone() is None:
        raise ValueError(f"Lease {lease_id} does not exist.")
    if invoice_id is not None and conn.execute("SELECT 1 FROM invoices WHERE id = ?", (invoice_id,)).fetchone() is None:
        raise ValueError(f"Invoice {invoice_id} does not exist.")

    today = db.shop_today(conn)
    created_at = f"{today}T{datetime.now().strftime('%H:%M:%S')}{SHOP_UTC_OFFSET}"
    cursor = conn.execute(
        "INSERT INTO tickets (type, requester, subject, sku, size, qty, lease_id, invoice_id, status, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)",
        (type, requester, subject, sku, size, qty, lease_id, invoice_id, notes, created_at, db.now_iso()),
    )
    ticket_id = cursor.lastrowid
    log_event(conn, agent, "opened", f"Ticket {ticket_id} opened ({type}): {subject}", ticket_id, {"type": type, "requester": requester})
    return get_ticket(conn, ticket_id)


def assign_ticket(conn: sqlite3.Connection, ticket_id: int, assigned_to: str, agent: str) -> dict:
    """Hand a ticket to one of the five agents. An 'open' ticket becomes 'in_progress'."""
    _require_actor(agent)
    if assigned_to not in AGENTS:
        raise ValueError(f"Cannot assign to '{assigned_to}'. Agents: {', '.join(AGENTS)}.")
    ticket = _ticket_row(conn, ticket_id)
    if ticket["status"] == "resolved":
        raise ValueError(f"Ticket {ticket_id} is resolved. Set its status back to 'open' before assigning it.")
    new_status = "in_progress" if ticket["status"] == "open" else ticket["status"]
    conn.execute(
        "UPDATE tickets SET assigned_to = ?, status = ?, updated_at = ? WHERE id = ?",
        (assigned_to, new_status, db.now_iso(), ticket_id),
    )
    log_event(conn, agent, "assigned", f"Ticket {ticket_id} assigned to {assigned_to}", ticket_id, {"assigned_to": assigned_to})
    return get_ticket(conn, ticket_id)


def set_ticket_priority(conn: sqlite3.Connection, ticket_id: int, priority: int, agent: str) -> dict:
    """Rank a ticket; 1 is the most urgent."""
    _require_actor(agent)
    if priority < 1:
        raise ValueError("priority must be 1 or more (1 = most urgent).")
    _ticket_row(conn, ticket_id)
    conn.execute("UPDATE tickets SET priority = ?, updated_at = ? WHERE id = ?", (priority, db.now_iso(), ticket_id))
    log_event(conn, agent, "priority", f"Ticket {ticket_id} priority set to {priority}", ticket_id, {"priority": priority})
    return get_ticket(conn, ticket_id)


def set_ticket_status(conn: sqlite3.Connection, ticket_id: int, status: str, agent: str) -> dict:
    """Move a ticket between 'open', 'in_progress', and 'waiting_approval'.

    Resolving goes through resolve_ticket, which requires a written
    resolution. Setting a resolved ticket back to 'open' reopens it and clears
    its resolution (the old text is kept in the event log).
    """
    _require_actor(agent)
    if status not in OPEN_STATUSES:
        if status == "resolved":
            raise ValueError("Use resolve_ticket to resolve a ticket; it needs a resolution.")
        raise ValueError(f"Unknown status '{status}'. Statuses: {', '.join(OPEN_STATUSES)}.")
    ticket = _ticket_row(conn, ticket_id)
    previous = ticket["status"]
    reopening = previous == "resolved"
    conn.execute(
        "UPDATE tickets SET status = ?, resolution = CASE WHEN ? THEN NULL ELSE resolution END, updated_at = ? WHERE id = ?",
        (status, reopening, db.now_iso(), ticket_id),
    )
    data = {"from": previous, "to": status}
    if reopening:
        data["cleared_resolution"] = ticket["resolution"]
    log_event(conn, agent, "status", f"Ticket {ticket_id} status {previous} -> {status}", ticket_id, data)
    return get_ticket(conn, ticket_id)


def add_ticket_note(conn: sqlite3.Connection, ticket_id: int, note: str, agent: str) -> dict:
    """Write a note on a ticket's timeline. Returns the event."""
    _require_actor(agent)
    note = _require_text("note", note)
    _ticket_row(conn, ticket_id)
    return log_event(conn, agent, "note", note, ticket_id)


def resolve_ticket(conn: sqlite3.Connection, ticket_id: int, resolution: str, agent: str) -> dict:
    """Close a ticket with a written resolution."""
    _require_actor(agent)
    resolution = _require_text("resolution", resolution)
    ticket = _ticket_row(conn, ticket_id)
    if ticket["status"] == "resolved":
        raise ValueError(f"Ticket {ticket_id} is already resolved.")
    conn.execute(
        "UPDATE tickets SET status = 'resolved', resolution = ?, updated_at = ? WHERE id = ?",
        (resolution, db.now_iso(), ticket_id),
    )
    log_event(conn, agent, "resolved", f"Ticket {ticket_id} resolved: {resolution}", ticket_id, {"resolution": resolution})
    return get_ticket(conn, ticket_id)
