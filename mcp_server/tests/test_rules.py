"""One test per shop rule, run against a temporary copy of the original database.

Rules (AI_prompts.md, "Shop rules"):
 1 work on the copy, never the original      6 no negative balances
 2 desk.date_today is today                  7 cash only goes out
 3 lead times come from vendors              8 reset before a full run
 4 unpaid vendor will not ship               9 drafts stay on the board
 5 a human approves every payment           10 gpt-6-luna via Portkey (back end; not an MCP concern)
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_server import db, money, reset, shop, tickets
from mcp_server.tests.test_tickets import sha256, work_db  # noqa: F401  (fixture)

TODAY = "2026-08-31"


def _approve_and_pay(conn, kind, ref_id, ticket_id=None, who="Store Manager"):
    approval = money.request_approval(conn, kind=kind, ref_id=ref_id, rationale=f"pay {kind} {ref_id}", agent="accounting", ticket_id=ticket_id)
    money.decide_approval(conn, approval["id"], "approved", who)
    return money.pay(conn, approval["id"], who)


def test_rule_1_tools_work_on_the_copy_and_the_original_is_never_written(work_db):
    before = sha256(db.ORIGINAL_DB_PATH)
    with db.connect() as conn:
        _approve_and_pay(conn, "invoice", 501, ticket_id=101)
    assert sha256(db.ORIGINAL_DB_PATH) == before
    assert sha256(work_db) != before  # the copy changed, the original did not


def test_rule_2_overdue_and_due_dates_use_the_shops_clock(work_db):
    with db.connect() as conn:
        assert db.shop_today(conn) == TODAY
        invoice = shop.get_invoice(conn, 501)
        assert invoice["days_overdue"] == 3  # due 2026-08-28
        lease = shop.get_lease(conn, 1)
        assert lease["days_until_due"] == 2  # due 2026-09-02


def test_rule_3_purchase_orders_use_the_vendors_lead_time(work_db):
    with db.connect() as conn:
        po = money.create_purchase_order(conn, vendor_id=2, sku="CC-MUG-CREST", size="OS", qty=10, agent="inventory")
        assert po["expected_date"] == "2026-09-03"  # Elm City Gifts: 3 days
        assert po["unit_cost"] == 3.5 and po["total"] == 35.0  # pricing table, not typed in
        assert po["status"] == "draft"


def test_rule_4_a_vendor_with_an_open_invoice_will_not_ship(work_db):
    with db.connect() as conn:
        bulldog = shop.get_vendor(conn, 1)
        assert bulldog["can_ship"] is False and bulldog["open_invoice_ids"] == [501]
        with pytest.raises(ValueError, match="will not ship while invoice 501"):
            money.create_purchase_order(conn, vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=20, agent="inventory", ticket_id=103)
        assert money.list_purchase_orders(conn) == []
        # Paying the invoice unblocks the vendor.
        _approve_and_pay(conn, "invoice", 501, ticket_id=101)
        assert shop.get_vendor(conn, 1)["can_ship"] is True
        po = money.create_purchase_order(conn, vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=20, agent="inventory", ticket_id=103)
        assert po["total"] == 440.0 and po["expected_date"] == "2026-09-05"


def test_rule_5_only_a_human_approval_lets_pay_run_and_the_tables_are_updated(work_db):
    with db.connect() as conn:
        approval = money.request_approval(conn, kind="invoice", ref_id=501, rationale="3 days overdue; vendor blocked", agent="accounting", ticket_id=101)
        assert approval["status"] == "pending" and approval["amount"] == 840.0
        assert conn.execute("SELECT status FROM tickets WHERE id = 101").fetchone()[0] == "waiting_approval"
        with pytest.raises(ValueError, match="a human must approve it"):
            money.pay(conn, approval["id"], "Store Manager")
        assert shop.list_payments(conn) == []
        money.decide_approval(conn, approval["id"], "approved", "Store Manager", note="ok, pay it")
        with pytest.raises(ValueError, match="approved by Store Manager, not"):
            money.pay(conn, approval["id"], "Somebody Else")
        payment = money.pay(conn, approval["id"], "Store Manager")
        assert payment["amount"] == 840.0 and payment["paid_at"] == TODAY and payment["approved_by"] == "Store Manager"
        assert shop.get_invoice(conn, 501)["status"] == "paid"
        assert shop.get_cash(conn)["accounts"][0]["balance"] == 2560.0
        assert money.list_approvals(conn, "executed")[0]["id"] == approval["id"]
        with pytest.raises(ValueError, match="already executed"):
            money.pay(conn, approval["id"], "Store Manager")
        kinds = [e["kind"] for e in tickets.list_ticket_events(conn, 101)]
        assert kinds == ["approval_requested", "approved", "paid"]


def test_rule_6_pay_refuses_when_cash_is_short(work_db):
    with db.connect() as conn:
        _approve_and_pay(conn, "invoice", 501)  # 3400 -> 2560
        po = money.create_purchase_order(conn, vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=20, agent="inventory")
        po_approval = money.request_approval(conn, kind="purchase_order", ref_id=po["id"], rationale="restock 20 hoodies", agent="accounting")
        money.decide_approval(conn, po_approval["id"], "approved", "Store Manager")
        _approve_and_pay(conn, "rent", 1)  # 2560 -> 160
        assert shop.get_cash(conn)["accounts"][0]["balance"] == 160.0
        with pytest.raises(ValueError, match="Not enough cash: checking holds \\$160.00 and the payment is \\$440.00"):
            money.pay(conn, po_approval["id"], "Store Manager")
        assert shop.get_cash(conn)["accounts"][0]["balance"] == 160.0  # unchanged
        assert len(shop.list_payments(conn)) == 2
        assert money.list_purchase_orders(conn)[0]["status"] == "waiting_approval"
        assert shop.get_lease(conn, 1)["next_due"] == "2026-10-02"  # rent moved the lease one month


def test_rule_7_cash_only_goes_out(work_db):
    with db.connect() as conn:
        override = money.request_approval(conn, kind="price_override", rationale="20 hoodies for the AI Club", agent="boss", ticket_id=103)
        assert override["amount"] == 0.0
        money.decide_approval(conn, override["id"], "approved", "Store Manager")
        with pytest.raises(ValueError, match="carries no payment"):
            money.pay(conn, override["id"], "Store Manager")
        start = shop.get_cash(conn)["total"]
        _approve_and_pay(conn, "invoice", 501)
        assert shop.get_cash(conn)["total"] < start
    # No tool can add cash: nothing in the money module writes a larger balance.
    import inspect

    source = inspect.getsource(money)
    assert "balance + " not in source and "balance +=" not in source


def test_rule_8_reset_restores_the_seed(work_db):
    with db.connect() as conn:
        _approve_and_pay(conn, "invoice", 501, ticket_id=101)
        money.draft_customer_message(conn, ticket_id=101, recipient="Tauhid Zaman", subject="Your tee", body="Back in stock on 9/5.", agent="customer_service")
    summary = reset.reset_working_copy()
    assert summary["counts"] == {"tickets": 3, "payments": 0, "approvals": 0, "purchase_orders": 0, "drafts": 0}
    assert summary["checking_balance"] == 3400.0
    with db.connect() as conn:
        assert shop.get_invoice(conn, 501)["status"] == "open"
        events = tickets.list_ticket_events(conn)
        assert [e["kind"] for e in events] == ["reset"] and events[0]["agent"] == "system"


def test_rule_9_drafts_stay_on_the_board_and_nothing_sends(work_db):
    with db.connect() as conn:
        draft = money.draft_customer_message(conn, ticket_id=101, recipient="Tauhid Zaman", subject="Your tee", body="Back in stock on 9/5.", agent="customer_service")
        assert draft["author"] == "customer_service"
        assert [d["id"] for d in money.list_drafts(conn, 101)] == [draft["id"]]
    from fastmcp import Client

    from mcp_server.server import mcp

    async def _names():
        async with Client(mcp) as client:
            return {t.name for t in await client.list_tools()}

    names = asyncio.run(_names())
    assert not {n for n in names if "send" in n or "email" in n or "mail" in n}
    assert "draft_customer_message" in names and "pay" in names
