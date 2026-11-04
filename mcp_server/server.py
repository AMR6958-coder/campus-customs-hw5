"""Campus Customs MCP server.

Exposes the shop's data and actions as MCP tools for the agent team. Every
agent may call every tool. The tools only read and write the working copy of
the database (``data/campus_customs_new.db``) and never invent a value: what
they return is what the database holds, plus arithmetic on it.

Run from the project root (streamable HTTP on port 8100)::

    .venv\\Scripts\\python -m mcp_server.server

The tool functions here are thin: they open a connection for the call and
hand off to ``tickets.py``, where the real work and the validation live.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `fastmcp run mcp_server/server.py` and `python mcp_server/server.py`,
# which load this file outside its package, to still import the package.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP  # noqa: E402

from mcp_server import db, money, shop, tickets  # noqa: E402

HOST = "127.0.0.1"
PORT = 8100

INSTRUCTIONS = """\
Tools for running the Campus Customs shop (a Yale merchandise store).

The shop has its own clock: get_today returns the date everything is judged
against. Tickets are the inbox: list them, read one with everything it links
to (invoice, lease, stock, pricing), open new ones, assign them to an agent,
set a priority, move them between statuses, add notes, and resolve them with
a written resolution. Every change is recorded on the ticket's timeline.

Stock, pricing, vendors, invoices, leases, cash, and payments are read with
the get_/list_ tools. Restocking: create_purchase_order (refused while the
vendor has an unpaid invoice). Money: request_approval asks a human; only
pay moves cash, only against an approved request, and never below zero.
Customer messages go through draft_customer_message and stay on the board:
nothing here sends email.

Agents: boss, inventory, accounting, facilities, customer_service.
Statuses: open, in_progress, waiting_approval, resolved.
"""

mcp = FastMCP(name="Campus Customs Shop", instructions=INSTRUCTIONS)


# --------------------------------------------------------------------------
# The shop's clock
# --------------------------------------------------------------------------


@mcp.tool()
def get_today() -> dict:
    """The shop's date (desk.date_today) and the desk notes.

    Use this date, never the real calendar, to decide what is overdue or when
    a delivery lands.
    """
    with db.connect() as conn:
        row = conn.execute("SELECT date_today, notes FROM desk LIMIT 1").fetchone()
        if row is None:
            raise ValueError("The desk table is empty, so the shop has no date.")
        return {"date_today": row["date_today"], "notes": row["notes"]}


# --------------------------------------------------------------------------
# Reading tickets
# --------------------------------------------------------------------------


@mcp.tool()
def list_tickets(status: str | None = None) -> list[dict]:
    """All tickets on the board, or only those with one status.

    status: open, in_progress, waiting_approval, or resolved. Omit it for all.
    Tickets with a priority come first (1 = most urgent), then by id.
    """
    with db.connect() as conn:
        return tickets.list_tickets(conn, status)


@mcp.tool()
def get_ticket(ticket_id: int) -> dict:
    """One ticket with everything it links to.

    The result includes shop_today and a links object: the invoice (with its
    vendor and days_overdue by the shop's clock), the lease (with
    days_until_due), the inventory rows for the ticket's SKU with the
    requested size flagged, and that SKU's pricing. Links the ticket does not
    have are null.
    """
    with db.connect() as conn:
        return tickets.get_ticket(conn, ticket_id)


@mcp.tool()
def list_ticket_events(ticket_id: int | None = None, since_id: int | None = None, limit: int = 100) -> list[dict]:
    """The timeline: who did what, oldest first.

    Give a ticket_id for one ticket's history, or omit it for the whole shop.
    since_id returns only events after that id, for polling.
    """
    with db.connect() as conn:
        return tickets.list_ticket_events(conn, ticket_id, since_id, limit)


# --------------------------------------------------------------------------
# Writing tickets
# --------------------------------------------------------------------------


@mcp.tool()
def open_ticket(
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
    """Put a new ticket on the board with status 'open'.

    type is free text such as customer_order, rent_notice, price_override,
    unpaid_invoice, or restock. Anything the ticket points at must exist: the
    sku (and size) in inventory, the lease, the invoice. agent is who is
    opening it (an agent name, or human).
    """
    with db.connect() as conn:
        return tickets.open_ticket(
            conn,
            type=type,
            requester=requester,
            subject=subject,
            notes=notes,
            sku=sku,
            size=size,
            qty=qty,
            lease_id=lease_id,
            invoice_id=invoice_id,
            agent=agent,
        )


@mcp.tool()
def assign_ticket(ticket_id: int, assigned_to: str, agent: str) -> dict:
    """Hand a ticket to an agent (boss, inventory, accounting, facilities, customer_service).

    An open ticket becomes in_progress. A resolved ticket cannot be assigned
    until it is reopened. agent is who is doing the assigning.
    """
    with db.connect() as conn:
        return tickets.assign_ticket(conn, ticket_id, assigned_to, agent)


@mcp.tool()
def set_ticket_priority(ticket_id: int, priority: int, agent: str) -> dict:
    """Rank a ticket. 1 is the most urgent; larger numbers are less urgent."""
    with db.connect() as conn:
        return tickets.set_ticket_priority(conn, ticket_id, priority, agent)


@mcp.tool()
def set_ticket_status(ticket_id: int, status: str, agent: str) -> dict:
    """Move a ticket to open, in_progress, or waiting_approval.

    To resolve a ticket use resolve_ticket, which needs a written resolution.
    Setting a resolved ticket back to open reopens it.
    """
    with db.connect() as conn:
        return tickets.set_ticket_status(conn, ticket_id, status, agent)


@mcp.tool()
def add_ticket_note(ticket_id: int, note: str, agent: str) -> dict:
    """Write a note on a ticket's timeline: a finding, a decision, a handoff."""
    with db.connect() as conn:
        return tickets.add_ticket_note(conn, ticket_id, note, agent)


@mcp.tool()
def resolve_ticket(ticket_id: int, resolution: str, agent: str) -> dict:
    """Close a ticket with a written resolution. The Boss makes this call."""
    with db.connect() as conn:
        return tickets.resolve_ticket(conn, ticket_id, resolution, agent)


@mcp.tool()
def log_event(kind: str, message: str, agent: str, ticket_id: int | None = None, data: dict | None = None) -> dict:
    """Append an entry to the activity feed without changing anything else.

    The back end uses this for delegations, tool calls, and errors so the
    board shows the agents working. Agents write their own findings with
    add_ticket_note. Omit ticket_id for a shop-wide event.
    """
    with db.connect() as conn:
        return tickets.log_event(conn, agent, kind, message, ticket_id, data)


# --------------------------------------------------------------------------
# Stock, pricing, vendors, invoices, leases, cash (read only)
# --------------------------------------------------------------------------


@mcp.tool()
def get_stock(sku: str, size: str | None = None) -> dict:
    """Inventory for a SKU: every size, or one size, with the SKU's pricing attached."""
    with db.connect() as conn:
        return shop.get_stock(conn, sku, size)


@mcp.tool()
def list_stock() -> list[dict]:
    """Every inventory row with its unit cost and list price."""
    with db.connect() as conn:
        return shop.list_stock(conn)


@mcp.tool()
def get_pricing(sku: str) -> dict:
    """Unit cost, list price, margin in dollars, and margin percent for a SKU."""
    with db.connect() as conn:
        return shop.get_pricing(conn, sku)


@mcp.tool()
def list_vendors() -> list[dict]:
    """Vendors with lead_days, their open invoices, and can_ship (false while an invoice is unpaid)."""
    with db.connect() as conn:
        return shop.list_vendors(conn)


@mcp.tool()
def get_vendor(vendor_id: int) -> dict:
    """One vendor with lead_days, open invoices, and can_ship."""
    with db.connect() as conn:
        return shop.get_vendor(conn, vendor_id)


@mcp.tool()
def list_invoices(status: str | None = None) -> list[dict]:
    """Invoices (open or paid) with the vendor's name and days_overdue by the shop's clock."""
    with db.connect() as conn:
        return shop.list_invoices(conn, status)


@mcp.tool()
def get_invoice(invoice_id: int) -> dict:
    """One invoice with the vendor's name and days_overdue by the shop's clock."""
    with db.connect() as conn:
        return shop.get_invoice(conn, invoice_id)


@mcp.tool()
def get_lease(lease_id: int) -> dict:
    """A lease with its landlord, monthly rent, next due date, and days_until_due."""
    with db.connect() as conn:
        return shop.get_lease(conn, lease_id)


@mcp.tool()
def list_leases() -> list[dict]:
    """Every lease with days_until_due, for when no ticket names the lease."""
    with db.connect() as conn:
        return shop.list_leases(conn)


@mcp.tool()
def get_cash() -> dict:
    """Every cash account with its balance and the date of that balance, plus the total."""
    with db.connect() as conn:
        return shop.get_cash(conn)


@mcp.tool()
def list_payments() -> list[dict]:
    """Payments made so far, oldest first, each with who approved it."""
    with db.connect() as conn:
        return shop.list_payments(conn)


# --------------------------------------------------------------------------
# Purchase orders, approvals, drafts, paying
# --------------------------------------------------------------------------


@mcp.tool()
def list_purchase_orders(status: str | None = None) -> list[dict]:
    """Purchase orders: draft, waiting_approval, ordered, or received. Omit status for all."""
    with db.connect() as conn:
        return money.list_purchase_orders(conn, status)


@mcp.tool()
def create_purchase_order(vendor_id: int, sku: str, size: str, qty: int, agent: str, ticket_id: int | None = None) -> dict:
    """Draft a restock order priced at unit_cost x qty, expected on today + the vendor's lead days.

    Refused while the vendor has an open invoice: they will not ship. Paying
    the order needs request_approval and then a human's approval.
    """
    with db.connect() as conn:
        return money.create_purchase_order(conn, vendor_id=vendor_id, sku=sku, size=size, qty=qty, agent=agent, ticket_id=ticket_id)


@mcp.tool()
def list_approvals(status: str | None = None) -> list[dict]:
    """Approval requests: pending, approved, rejected, or executed. Omit status for all."""
    with db.connect() as conn:
        return money.list_approvals(conn, status)


@mcp.tool()
def request_approval(kind: str, rationale: str, agent: str, ref_id: int | None = None, ticket_id: int | None = None) -> dict:
    """Ask the human to approve a payment. No money moves here.

    kind: invoice (ref_id = invoice id), rent (ref_id = lease id),
    purchase_order (ref_id = purchase order id), or price_override (no
    payment). The amount is read from that row, never typed in. The ticket,
    if given, moves to waiting_approval.
    """
    with db.connect() as conn:
        return money.request_approval(conn, kind=kind, rationale=rationale, agent=agent, ref_id=ref_id, ticket_id=ticket_id)


@mcp.tool()
def decide_approval(approval_id: int, decision: str, decided_by: str, note: str | None = None) -> dict:
    """The human's decision on a pending request: 'approved' or 'rejected'. Still moves no money."""
    with db.connect() as conn:
        return money.decide_approval(conn, approval_id, decision, decided_by, note)


@mcp.tool()
def pay(approval_id: int, approved_by: str) -> dict:
    """Execute an approved payment: the only tool that moves cash.

    Refused unless the approval is 'approved' by this same person, unless the
    account covers the amount (no negative balances), and, for a purchase
    order, unless the vendor has no unpaid invoice. Records the payment,
    lowers the balance, settles the invoice / lease / order, and marks the
    approval executed, all in one transaction.
    """
    with db.connect() as conn:
        return money.pay(conn, approval_id, approved_by)


@mcp.tool()
def draft_customer_message(ticket_id: int, recipient: str, subject: str, body: str, agent: str) -> dict:
    """Write a message for a customer and leave it on the board. Nothing is sent."""
    with db.connect() as conn:
        return money.draft_customer_message(conn, ticket_id=ticket_id, recipient=recipient, subject=subject, body=body, agent=agent)


@mcp.tool()
def list_drafts(ticket_id: int | None = None) -> list[dict]:
    """Drafted customer messages, for one ticket or all of them."""
    with db.connect() as conn:
        return money.list_drafts(conn, ticket_id)


if __name__ == "__main__":
    if "--stdio" in sys.argv[1:]:
        # Claude Code starts the server this way (see .mcp.json): it owns the
        # process and talks over stdin/stdout, so nothing else may print there.
        mcp.run(transport="stdio", show_banner=False)
    else:
        # The back end and the dashboard use this long-running HTTP server.
        mcp.run(transport="http", host=HOST, port=PORT)
