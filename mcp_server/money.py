"""Purchase orders, approvals, drafts, and the one tool that moves cash.

These carry the shop's money rules:

- rule 3: a purchase order's expected date is the shop's today plus the
  vendor's ``lead_days``;
- rule 4: no purchase order for a vendor with an open invoice, checked when
  the order is drafted and again when it is paid;
- rule 5: ``pay`` runs only against an approval a human has marked
  ``approved``, and records the payment, the balance, and the invoice, lease,
  or order it settles in one transaction;
- rule 6: ``pay`` refuses when the balance is short, so no account goes
  negative;
- rule 7: cash only leaves; there is no tool that adds to a balance;
- rule 9: drafts are stored on the board; there is no tool that sends one.

Amounts are never typed in by an agent: an approval takes its amount from the
invoice, lease, or purchase order it refers to.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from mcp_server import db, shop
from mcp_server.tickets import _require_actor, _require_text, _ticket_row, log_event

APPROVAL_KINDS = ("invoice", "rent", "purchase_order", "price_override")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "executed")
PO_STATUSES = ("draft", "waiting_approval", "ordered", "received")


def _add_days(iso_date: str, days: int) -> str:
    return (date.fromisoformat(iso_date[:10]) + timedelta(days=days)).isoformat()


def _add_one_month(iso_date: str) -> str:
    """The same day next month (clamped to that month's length)."""
    d = date.fromisoformat(iso_date[:10])
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    last_day = (date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day)).isoformat()


# --------------------------------------------------------------------------
# Purchase orders
# --------------------------------------------------------------------------


def _po_row(conn: sqlite3.Connection, po_id: int) -> dict:
    row = db.one(conn.execute("SELECT * FROM purchase_orders WHERE id = ?", (po_id,)))
    if row is None:
        raise ValueError(f"Purchase order {po_id} does not exist.")
    return row


def list_purchase_orders(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    if status is not None and status not in PO_STATUSES:
        raise ValueError(f"Unknown purchase order status '{status}'. Statuses: {', '.join(PO_STATUSES)}.")
    sql = "SELECT po.*, v.name AS vendor_name, v.lead_days AS vendor_lead_days FROM purchase_orders po JOIN vendors v ON v.id = po.vendor_id"
    params: tuple = ()
    if status is not None:
        sql += " WHERE po.status = ?"
        params = (status,)
    return db.rows(conn.execute(sql + " ORDER BY po.id", params))


def create_purchase_order(
    conn: sqlite3.Connection,
    *,
    vendor_id: int,
    sku: str,
    size: str,
    qty: int,
    agent: str,
    ticket_id: int | None = None,
) -> dict:
    """Draft a restock order. Priced at unit_cost x qty; dated today + the vendor's lead days.

    Refused when the vendor has an open invoice (rule 4): they will not ship.
    """
    _require_actor(agent)
    if qty <= 0:
        raise ValueError("qty must be a positive whole number.")
    vendor = shop.get_vendor(conn, vendor_id)
    if not vendor["can_ship"]:
        ids = ", ".join(str(i) for i in vendor["open_invoice_ids"])
        raise ValueError(
            f"{vendor['name']} will not ship while invoice {ids} (${vendor['open_invoice_total']:.2f}) is unpaid. "
            "Pay the invoice first (it needs a human approval), then order."
        )
    if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
        raise ValueError(f"No inventory row for sku '{sku}' in size '{size}'.")
    pricing = shop.get_pricing(conn, sku)
    if ticket_id is not None:
        _ticket_row(conn, ticket_id)
    today = db.shop_today(conn)
    total = round(pricing["unit_cost"] * qty, 2)
    cursor = conn.execute(
        "INSERT INTO purchase_orders (ticket_id, vendor_id, sku, size, qty, unit_cost, total, status, expected_date, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)",
        (ticket_id, vendor_id, sku, size, qty, pricing["unit_cost"], total, _add_days(today, vendor["lead_days"]), agent, db.now_iso()),
    )
    po_id = cursor.lastrowid
    log_event(
        conn, agent, "purchase_order",
        f"Purchase order {po_id} drafted: {qty} x {sku} {size} from {vendor['name']} for ${total:.2f}, expected {_add_days(today, vendor['lead_days'])}",
        ticket_id, {"purchase_order_id": po_id, "vendor_id": vendor_id, "total": total},
    )
    return _po_row(conn, po_id)


# --------------------------------------------------------------------------
# Approvals
# --------------------------------------------------------------------------


def _approval_row(conn: sqlite3.Connection, approval_id: int) -> dict:
    row = db.one(conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)))
    if row is None:
        raise ValueError(f"Approval {approval_id} does not exist.")
    return row


def list_approvals(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    if status is not None and status not in APPROVAL_STATUSES:
        raise ValueError(f"Unknown approval status '{status}'. Statuses: {', '.join(APPROVAL_STATUSES)}.")
    sql = "SELECT * FROM approvals"
    params: tuple = ()
    if status is not None:
        sql += " WHERE status = ?"
        params = (status,)
    return db.rows(conn.execute(sql + " ORDER BY id", params))


def _reference(conn: sqlite3.Connection, kind: str, ref_id: int | None) -> tuple[float, str]:
    """The amount an approval is for, read from the row it refers to, and a label for the payee."""
    if kind == "price_override":
        return 0.0, "no payment"
    if ref_id is None:
        raise ValueError(f"An approval of kind '{kind}' needs a ref_id.")
    if kind == "invoice":
        invoice = shop.get_invoice(conn, ref_id)
        if invoice["status"] != "open":
            raise ValueError(f"Invoice {ref_id} is already {invoice['status']}.")
        return invoice["amount"], invoice["vendor_name"]
    if kind == "rent":
        lease = shop.get_lease(conn, ref_id)
        return lease["monthly_rent"], lease["landlord"]
    if kind == "purchase_order":
        po = _po_row(conn, ref_id)
        if po["status"] not in ("draft", "waiting_approval"):
            raise ValueError(f"Purchase order {ref_id} is already {po['status']}.")
        return po["total"], shop.get_vendor(conn, po["vendor_id"])["name"]
    raise ValueError(f"Unknown approval kind '{kind}'. Kinds: {', '.join(APPROVAL_KINDS)}.")


def request_approval(
    conn: sqlite3.Connection,
    *,
    kind: str,
    rationale: str,
    agent: str,
    ref_id: int | None = None,
    ticket_id: int | None = None,
) -> dict:
    """Ask a human to approve a payment (or a price override). Never moves money (rule 5).

    The amount comes from the invoice, lease, or purchase order named by
    ref_id. The ticket, if given, moves to waiting_approval.
    """
    _require_actor(agent)
    rationale = _require_text("rationale", rationale)
    if kind not in APPROVAL_KINDS:
        raise ValueError(f"Unknown approval kind '{kind}'. Kinds: {', '.join(APPROVAL_KINDS)}.")
    amount, payee = _reference(conn, kind, ref_id)
    if amount < 0:
        raise ValueError("An approval cannot be for a negative amount: cash only goes out.")
    if ticket_id is not None:
        _ticket_row(conn, ticket_id)
    duplicate = conn.execute(
        "SELECT id FROM approvals WHERE kind = ? AND ref_id IS ? AND status IN ('pending', 'approved')", (kind, ref_id)
    ).fetchone()
    if duplicate is not None:
        raise ValueError(f"Approval {duplicate['id']} for this {kind} is already {('pending or approved')}.")
    cursor = conn.execute(
        "INSERT INTO approvals (ticket_id, kind, ref_id, amount, rationale, requested_by, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
        (ticket_id, kind, ref_id, amount, rationale, agent, db.now_iso()),
    )
    approval_id = cursor.lastrowid
    if kind == "purchase_order":
        conn.execute("UPDATE purchase_orders SET status = 'waiting_approval' WHERE id = ?", (ref_id,))
    if ticket_id is not None:
        conn.execute("UPDATE tickets SET status = 'waiting_approval', updated_at = ? WHERE id = ? AND status != 'resolved'", (db.now_iso(), ticket_id))
    log_event(
        conn, agent, "approval_requested",
        f"Approval {approval_id} requested: {kind} {ref_id or ''} ${amount:.2f} to {payee}. {rationale}",
        ticket_id, {"approval_id": approval_id, "kind": kind, "ref_id": ref_id, "amount": amount},
    )
    return _approval_row(conn, approval_id)


def decide_approval(conn: sqlite3.Connection, approval_id: int, decision: str, decided_by: str, note: str | None = None) -> dict:
    """A human approves or rejects a pending request. Still no money moves; pay does that."""
    decided_by = _require_text("decided_by", decided_by)
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'.")
    approval = _approval_row(conn, approval_id)
    if approval["status"] != "pending":
        raise ValueError(f"Approval {approval_id} is already {approval['status']}.")
    conn.execute(
        "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ?, decision_note = ? WHERE id = ?",
        (decision, decided_by, db.now_iso(), note, approval_id),
    )
    if decision == "rejected":
        if approval["kind"] == "purchase_order":
            conn.execute("UPDATE purchase_orders SET status = 'draft' WHERE id = ?", (approval["ref_id"],))
        if approval["ticket_id"] is not None:
            conn.execute("UPDATE tickets SET status = 'in_progress', updated_at = ? WHERE id = ? AND status = 'waiting_approval'", (db.now_iso(), approval["ticket_id"]))
    log_event(
        conn, "human", decision,
        f"Approval {approval_id} {decision} by {decided_by}" + (f": {note}" if note else ""),
        approval["ticket_id"], {"approval_id": approval_id, "decided_by": decided_by},
    )
    return _approval_row(conn, approval_id)


# --------------------------------------------------------------------------
# Paying: the only tool that touches cash
# --------------------------------------------------------------------------


def pay(conn: sqlite3.Connection, approval_id: int, approved_by: str) -> dict:
    """Execute an approved payment in one transaction.

    Refuses unless the approval is 'approved' by the same named human (rule 5),
    unless the account can cover it (rule 6), and, for a purchase order,
    unless the vendor has no other open invoice (rule 4). Then inserts the
    payment dated the shop's today, subtracts from the account, settles the
    invoice / advances the lease / marks the order ordered, and marks the
    approval executed. Cash only goes out (rule 7).
    """
    approved_by = _require_text("approved_by", approved_by)
    approval = _approval_row(conn, approval_id)
    if approval["status"] == "executed":
        raise ValueError(f"Approval {approval_id} was already executed (paid). Nothing more to pay.")
    if approval["status"] != "approved":
        raise ValueError(f"Approval {approval_id} is {approval['status']}; a human must approve it before anything is paid.")
    if approval["decided_by"] != approved_by:
        raise ValueError(f"Approval {approval_id} was approved by {approval['decided_by']}, not {approved_by}.")
    kind, ref_id, amount, account = approval["kind"], approval["ref_id"], approval["amount"], approval["account"]
    if kind == "price_override" or amount <= 0:
        raise ValueError(f"Approval {approval_id} ({kind}) carries no payment; nothing to pay.")

    # Re-read the amount from the referenced row so a stale approval cannot overpay.
    current_amount, payee = _reference(conn, kind, ref_id)
    if abs(current_amount - amount) > 0.005:
        raise ValueError(f"Approval {approval_id} was for ${amount:.2f} but the {kind} now reads ${current_amount:.2f}. Request a new approval.")
    if kind == "purchase_order":
        po = _po_row(conn, ref_id)
        vendor = shop.get_vendor(conn, po["vendor_id"])
        if not vendor["can_ship"]:
            raise ValueError(f"{vendor['name']} will not ship while invoice {vendor['open_invoice_ids']} is unpaid. Pay that first.")

    cash = db.one(conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)))
    if cash is None:
        raise ValueError(f"No cash account named '{account}'.")
    if cash["balance"] < amount:
        raise ValueError(
            f"Not enough cash: {account} holds ${cash['balance']:.2f} and the payment is ${amount:.2f}. Refused; no negative balances."
        )

    today = db.shop_today(conn)
    cursor = conn.execute(
        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
        (kind, ref_id, amount, account, today, approved_by),
    )
    payment_id = cursor.lastrowid
    new_balance = round(cash["balance"] - amount, 2)
    conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, account))
    if kind == "invoice":
        conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
        settled = f"invoice {ref_id} marked paid"
    elif kind == "rent":
        lease = shop.get_lease(conn, ref_id)
        next_due = _add_one_month(lease["next_due"])
        conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, ref_id))
        settled = f"lease {ref_id} next_due moved to {next_due}"
    else:
        conn.execute("UPDATE purchase_orders SET status = 'ordered' WHERE id = ?", (ref_id,))
        settled = f"purchase order {ref_id} ordered"
    conn.execute("UPDATE approvals SET status = 'executed' WHERE id = ?", (approval_id,))
    log_event(
        conn, "human", "paid",
        f"Paid ${amount:.2f} to {payee} from {account} ({kind} {ref_id}), approved by {approved_by}; {settled}; balance now ${new_balance:.2f}",
        approval["ticket_id"],
        {"payment_id": payment_id, "approval_id": approval_id, "kind": kind, "ref_id": ref_id, "amount": amount, "balance": new_balance},
    )
    payment = db.one(conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)))
    assert payment is not None
    payment["payee"] = payee
    payment["balance_after"] = new_balance
    payment["settled"] = settled
    return payment


# --------------------------------------------------------------------------
# Drafts: messages that stay on the board
# --------------------------------------------------------------------------


def draft_customer_message(conn: sqlite3.Connection, *, ticket_id: int, recipient: str, subject: str, body: str, agent: str) -> dict:
    """Save a message for the human to read on the board. Nothing is sent (rule 9)."""
    _require_actor(agent)
    recipient = _require_text("recipient", recipient)
    subject = _require_text("subject", subject)
    body = _require_text("body", body)
    _ticket_row(conn, ticket_id)
    cursor = conn.execute(
        "INSERT INTO drafts (ticket_id, recipient, subject, body, author, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (ticket_id, recipient, subject, body, agent, db.now_iso()),
    )
    draft_id = cursor.lastrowid
    log_event(conn, agent, "draft", f"Draft {draft_id} to {recipient}: {subject}", ticket_id, {"draft_id": draft_id, "recipient": recipient})
    row = db.one(conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)))
    assert row is not None
    return row


def list_drafts(conn: sqlite3.Connection, ticket_id: int | None = None) -> list[dict]:
    if ticket_id is not None:
        _ticket_row(conn, ticket_id)
        return db.rows(conn.execute("SELECT * FROM drafts WHERE ticket_id = ? ORDER BY id", (ticket_id,)))
    return db.rows(conn.execute("SELECT * FROM drafts ORDER BY id"))
