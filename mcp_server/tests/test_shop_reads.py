"""The single-record read tools added for the agents: get_vendor, get_invoice, list_leases."""

from __future__ import annotations

import pytest

from mcp_server import db, shop
from mcp_server.tests.test_tickets import work_db  # noqa: F401  (fixture)


def test_get_vendor_get_invoice_and_list_leases_read_the_seed(work_db):
    with db.connect() as conn:
        vendor = shop.get_vendor(conn, 1)
        assert vendor["name"] == "Bulldog Print Co" and vendor["lead_days"] == 5 and vendor["can_ship"] is False
        invoice = shop.get_invoice(conn, 501)
        assert invoice["vendor_name"] == "Bulldog Print Co" and invoice["days_overdue"] == 3
        leases = shop.list_leases(conn)
        assert [(lease["id"], lease["landlord"], lease["days_until_due"]) for lease in leases] == [(1, "Elm City Properties", 2)]
        with pytest.raises(ValueError, match="Vendor 9 does not exist"):
            shop.get_vendor(conn, 9)
        with pytest.raises(ValueError, match="Invoice 9 does not exist"):
            shop.get_invoice(conn, 9)
