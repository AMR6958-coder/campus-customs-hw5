# The Campus Customs MCP server

This package is the shop's data and actions, exposed as MCP tools so the agent team (Boss,
Inventory, Accounting, Facilities, Customer Service) can read the shop and act on it. Every agent
may call every tool. The tools never invent a value: what they return is what the database holds,
plus arithmetic on it (days overdue, days until due, margin, order totals).

## Which database

The server works on the **working copy**, `data/campus_customs_new.db`. The original,
`data/campus_customs.db`, is the reset source and is never opened by this package: `db.py` refuses
it even if `CAMPUS_DB_PATH` points at it. On first use the working copy receives four extra ticket
columns (`assigned_to`, `priority`, `resolution`, `updated_at`) and four extra tables
(`ticket_events`, `approvals`, `drafts`, `purchase_orders`). The seed tables are not changed.

`CAMPUS_DB_PATH` points the server at another file; the tests use it to run on a temporary copy.

## Running, testing, resetting

From the project root, with the virtual environment set up as in the main README:

```
.venv\Scripts\python -m mcp_server.server     # streamable HTTP on http://127.0.0.1:8100
.venv\Scripts\python -m pytest                # 31 tests on a temporary copy
.venv\Scripts\python -m mcp_server.reset      # copy the original over the working copy
```

Resetting is a script, not a tool: agents cannot reset the shop.

The project's `.mcp.json` registers this server with Claude Code as `campus-customs` over stdio:
Claude Code runs `python -m mcp_server.server --stdio` itself when a session opens, and the tools
are callable in that session as `mcp__campus-customs__<tool>`. Without `--stdio` the same module
serves HTTP on port 8100 for the back end. Both copies work on the same working copy.

## The tools (30)

**Shop clock and board** (`tickets.py`)

| Tool | What it does |
|---|---|
| `get_today` | the shop's date (`desk.date_today`) and the desk notes; every due-date judgement uses it |
| `list_tickets(status?)` | the board, prioritised tickets first |
| `get_ticket(ticket_id)` | one ticket with its invoice (and vendor, days overdue), lease (days until due), stock, and pricing |
| `list_ticket_events(ticket_id?, since_id?, limit)` | the timeline: who did what, oldest first |
| `open_ticket(type, requester, subject, ...)` | a new ticket; anything it points at must exist |
| `assign_ticket(ticket_id, assigned_to, agent)` | hand a ticket to an agent; open becomes in_progress |
| `set_ticket_priority(ticket_id, priority, agent)` | 1 is most urgent |
| `set_ticket_status(ticket_id, status, agent)` | open, in_progress, or waiting_approval |
| `add_ticket_note(ticket_id, note, agent)` | a finding or handoff on the timeline |
| `resolve_ticket(ticket_id, resolution, agent)` | close with a written resolution |
| `log_event(kind, message, agent, ticket_id?, data?)` | an entry on the timeline that changes nothing else; the back end's audit trail (delegations, tool calls, errors), hidden from the agents |

**Stock, pricing, vendors, invoices, leases, cash** (`shop.py`, read only)

| Tool | What it returns |
|---|---|
| `get_stock(sku, size?)`, `list_stock()` | inventory rows with pricing |
| `get_pricing(sku)` | unit cost, list price, margin |
| `list_vendors()`, `get_vendor(vendor_id)` | vendors with lead days, open invoices, and `can_ship` |
| `list_invoices(status?)`, `get_invoice(invoice_id)` | invoices with vendor name and days overdue |
| `get_lease(lease_id)`, `list_leases()` | the lease(s) with days until due |
| `get_cash()`, `list_payments()` | balances, and the payments made |

**Purchase orders, approvals, drafts, paying** (`money.py`)

| Tool | What it does | Rule |
|---|---|---|
| `list_purchase_orders(status?)`, `create_purchase_order(vendor_id, sku, size, qty, agent, ticket_id?)` | a draft order priced from `pricing`, dated today + the vendor's lead days; refused while the vendor has an open invoice | 3, 4 |
| `list_approvals(status?)`, `request_approval(kind, rationale, agent, ref_id?, ticket_id?)` | asks a human; the amount is read from the invoice, lease, or order; no money moves | 5 |
| `decide_approval(approval_id, decision, decided_by, note?)` | the human's approved or rejected | 5 |
| `pay(approval_id, approved_by)` | the only cash movement: approved by that same named human, balance must cover it, vendor re-checked; writes the payment, the balance, the settled row, and the approval in one transaction | 4, 5, 6, 7 |
| `draft_customer_message(ticket_id, recipient, subject, body, agent)`, `list_drafts(ticket_id?)` | messages stay on the board; there is no send tool | 9 |

A refusal is a plain sentence saying what to fix, returned to the caller as a tool error.

## Where to read more

`output/harness.md` sections 4 and 5: the design, what each value is computed from, the decisions
made, the tool-to-ticket map, and what the tests verified.
