"""Read tools for the shop's tables: stock, pricing, vendors, cash, invoices, leases, payments.

Nothing here writes. Every value returned is a column from the database or
arithmetic on such columns: a margin is list price minus unit cost, days
overdue is the shop's today minus a due date (shop rule 2), and a vendor's
``can_ship`` is simply "has no open invoice" (shop rule 4).
"""

from __future__ import annotations

import sqlite3

from mcp_server import db
from mcp_server.tickets import _days_between


# --------------------------------------------------------------------------
# Stock and pricing
# --------------------------------------------------------------------------


def get_pricing(conn: sqlite3.Connection, sku: str) -> dict:
    """Unit cost, list price, and the margin between them for one SKU."""
    pricing = db.one(conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)))
    if pricing is None:
        raise ValueError(f"No pricing row for sku '{sku}'.")
    pricing["margin"] = round(pricing["list_price"] - pricing["unit_cost"], 2)
    pricing["margin_pct"] = round(100 * pricing["margin"] / pricing["list_price"], 1) if pricing["list_price"] else None
    return pricing


def get_stock(conn: sqlite3.Connection, sku: str, size: str | None = None) -> dict:
    """Inventory rows for a SKU (one size, or all of them) with its pricing attached."""
    if size:
        stock = db.rows(conn.execute("SELECT * FROM inventory WHERE sku = ? AND size = ?", (sku, size)))
        if not stock:
            raise ValueError(f"No inventory row for sku '{sku}' in size '{size}'.")
    else:
        stock = db.rows(conn.execute("SELECT * FROM inventory WHERE sku = ? ORDER BY rowid", (sku,)))
        if not stock:
            raise ValueError(f"No inventory rows for sku '{sku}'.")
    pricing = db.one(conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)))
    return {"sku": sku, "stock": stock, "pricing": pricing}


def list_stock(conn: sqlite3.Connection) -> list[dict]:
    """Every inventory row, with the SKU's unit cost and list price alongside."""
    return db.rows(
        conn.execute(
            "SELECT i.*, p.unit_cost, p.list_price FROM inventory i LEFT JOIN pricing p ON p.sku = i.sku ORDER BY i.rowid"
        )
    )


# --------------------------------------------------------------------------
# Vendors and invoices
# --------------------------------------------------------------------------


def open_invoices_for_vendor(conn: sqlite3.Connection, vendor_id: int) -> list[dict]:
    """The vendor's invoices with status 'open'. Non-empty means the vendor will not ship (rule 4)."""
    return db.rows(conn.execute("SELECT * FROM invoices WHERE vendor_id = ? AND status = 'open' ORDER BY id", (vendor_id,)))


def list_vendors(conn: sqlite3.Connection) -> list[dict]:
    """Vendors with their lead times, their open invoices, and whether they will ship."""
    vendors = db.rows(conn.execute("SELECT * FROM vendors ORDER BY id"))
    for vendor in vendors:
        open_rows = open_invoices_for_vendor(conn, vendor["id"])
        vendor["open_invoice_ids"] = [row["id"] for row in open_rows]
        vendor["open_invoice_total"] = round(sum(row["amount"] for row in open_rows), 2)
        vendor["can_ship"] = not open_rows
    return vendors


def get_vendor(conn: sqlite3.Connection, vendor_id: int) -> dict:
    for vendor in list_vendors(conn):
        if vendor["id"] == vendor_id:
            return vendor
    raise ValueError(f"Vendor {vendor_id} does not exist.")


def list_invoices(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    """Invoices with the vendor's name and days overdue against the shop's today."""
    if status is not None and status not in ("open", "paid"):
        raise ValueError(f"Unknown invoice status '{status}'. Statuses: open, paid.")
    sql = "SELECT i.*, v.name AS vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id"
    params: tuple = ()
    if status is not None:
        sql += " WHERE i.status = ?"
        params = (status,)
    sql += " ORDER BY i.due_date, i.id"
    today = db.shop_today(conn)
    invoices = db.rows(conn.execute(sql, params))
    for invoice in invoices:
        overdue = _days_between(invoice["due_date"], today)
        invoice["days_overdue"] = max(0, overdue) if invoice["status"] == "open" else 0
    return invoices


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict:
    for invoice in list_invoices(conn):
        if invoice["id"] == invoice_id:
            return invoice
    raise ValueError(f"Invoice {invoice_id} does not exist.")


# --------------------------------------------------------------------------
# Cash, leases, payments
# --------------------------------------------------------------------------


def get_cash(conn: sqlite3.Connection) -> dict:
    """Every cash account with its balance and the date of that balance."""
    accounts = db.rows(conn.execute("SELECT * FROM cash_accounts ORDER BY name"))
    return {"accounts": accounts, "total": round(sum(a["balance"] for a in accounts), 2)}


def get_lease(conn: sqlite3.Connection, lease_id: int) -> dict:
    """One lease with days until its next due date by the shop's clock."""
    lease = db.one(conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)))
    if lease is None:
        raise ValueError(f"Lease {lease_id} does not exist.")
    lease["days_until_due"] = _days_between(db.shop_today(conn), lease["next_due"])
    return lease


def list_leases(conn: sqlite3.Connection) -> list[dict]:
    today = db.shop_today(conn)
    leases = db.rows(conn.execute("SELECT * FROM leases ORDER BY id"))
    for lease in leases:
        lease["days_until_due"] = _days_between(today, lease["next_due"])
    return leases


def list_payments(conn: sqlite3.Connection) -> list[dict]:
    """Every payment made so far, oldest first. The seed starts with none."""
    return db.rows(conn.execute("SELECT * FROM payments ORDER BY id"))
