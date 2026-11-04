# Harness Notes — Campus Customs Agentic Shop Team

**Project:** MGT 409 E1, Homework 5
**Date started:** 2026-11-02

This document collects the analysis and design notes that guide the build. It begins with a review of
the instructor-provided data file, since that data defines what the agents must handle, then records
the shop rules and where each one is enforced, then the design of the three pieces. Later sections are
added as each build step lands, each ending with what was verified.

---

## 1. Analysis of `data.zip`

The archive (2 KB) was extracted into the project root on 2026-11-02 and produced one file:

- `data/campus_customs.db` — a SQLite database (53 KB, dated 2026-10-03)

A byte-for-byte copy, `data/campus_customs_new.db`, is the **working copy** that the agents read and
write. The original is never opened for writing; it exists so the working copy can be reset. Both
files have SHA-256 `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a` as extracted.

### 1.1 The shop

The database is the **back office** of Campus Customs, the Yale merchandise shop from Homework 4,
reduced to four products and the paperwork of running a store: an inbox of tickets, stock by size and
aisle, a price list, three vendors, one unpaid vendor invoice, one lease, and one checking account.
Unlike the Homework 4 database there is no customer-facing catalogue, no users, and no chat history.

The shop has its own clock. The `desk` table holds a single row whose `date_today` is **2026-08-31**.
Everything that depends on a date (what is overdue, when a restock arrives, what a payment is dated)
is judged against that value, never the real calendar.

### 1.2 Database tables

| Table | Rows | What it holds |
|---|---|---|
| `tickets` | 3 | The inbox: type, requester, subject, free-text notes, optional links to a SKU and size, a lease, or an invoice |
| `inventory` | 10 | Stock per SKU per size, with the aisle it sits in |
| `pricing` | 4 | Unit cost and list price per SKU |
| `vendors` | 3 | Supplier name, specialty, and lead time in days |
| `invoices` | 1 | A vendor bill: amount, due date, status |
| `leases` | 1 | The shop space: landlord, monthly rent, next due date |
| `cash_accounts` | 1 | One account named `checking` with its balance and an as-of date |
| `payments` | 0 | Money that has gone out; empty at the start |
| `desk` | 1 | The shop's clock (`date_today`) and a free-text `notes` column, empty |

Schema details, exactly as stored:

```sql
CREATE TABLE tickets (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,            -- customer_order | rent_notice | price_override (seen so far)
    requester TEXT NOT NULL,       -- free text: a person, a landlord, a student organization
    subject TEXT NOT NULL,
    sku TEXT, size TEXT, qty INTEGER,
    lease_id INTEGER, invoice_id INTEGER,
    status TEXT NOT NULL,          -- 'open' for all three
    notes TEXT,
    created_at TEXT NOT NULL,      -- ISO text with a -04:00 offset
    FOREIGN KEY (lease_id) REFERENCES leases(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);
CREATE TABLE inventory (
    sku TEXT NOT NULL, name TEXT NOT NULL, size TEXT NOT NULL,
    qty INTEGER NOT NULL, location TEXT NOT NULL,
    PRIMARY KEY (sku, size)
);
CREATE TABLE pricing   (sku TEXT PRIMARY KEY, unit_cost REAL NOT NULL, list_price REAL NOT NULL);
CREATE TABLE vendors   (id INTEGER PRIMARY KEY, name TEXT NOT NULL, specialty TEXT NOT NULL, lead_days INTEGER NOT NULL);
CREATE TABLE invoices  (id INTEGER PRIMARY KEY, vendor_id INTEGER NOT NULL, amount REAL NOT NULL,
                        due_date TEXT NOT NULL, status TEXT NOT NULL, description TEXT,
                        FOREIGN KEY (vendor_id) REFERENCES vendors(id));
CREATE TABLE leases    (id INTEGER PRIMARY KEY, space_name TEXT NOT NULL, landlord TEXT NOT NULL,
                        monthly_rent REAL NOT NULL, next_due TEXT NOT NULL, notes TEXT);
CREATE TABLE cash_accounts (name TEXT PRIMARY KEY, balance REAL NOT NULL, date TEXT NOT NULL);
CREATE TABLE payments  (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, ref_id INTEGER, amount REAL NOT NULL,
                        account TEXT NOT NULL, paid_at TEXT NOT NULL, approved_by TEXT NOT NULL);
CREATE TABLE desk      (date_today TEXT NOT NULL, notes TEXT);
```

`PRAGMA integrity_check` returns `ok`. There is no `sqlite_sequence` table, so the `INTEGER PRIMARY
KEY` columns are plain rowids: a new ticket gets id 104, a new payment gets id 1, and so on.

**Fields, and why each table matters to the agents**

| Table | Fields | Why it matters to the agents |
|---|---|---|
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at` | The inbox and the board. Boss reads every open ticket to triage and route it; the agent working a ticket reads its row for the SKU, size, quantity, or linked lease or invoice; Boss writes the status and resolution. The working copy gains `assigned_to`, `priority`, `resolution`, `updated_at`. |
| `inventory` | `sku`, `name`, `size`, `qty`, `location` | What is on the shelf. Inventory checks it for an order (ticket 101) or a bulk request (103), spots the shortfalls (tee S and mug at 0), and raises `qty` when a restock is received. Customer Service reads it to tell a customer what is on hand and where. |
| `pricing` | `sku`, `unit_cost`, `list_price` | The money per unit. Accounting checks margins for a discount request (103) and prices a purchase order at `unit_cost`; Inventory uses `unit_cost` to size a restock; Customer Service quotes `list_price`. |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | Who can restock what, and how fast. Inventory matches a SKU to a vendor by `specialty` and computes the arrival date from `lead_days` (rule 3); Accounting and Inventory check whether a vendor is blocked by an open invoice (rule 4). |
| `invoices` | `id`, `vendor_id`, `amount`, `due_date`, `status`, `description` | What the shop owes. Accounting judges what is overdue against the shop's clock (501 is three days late) and prepares payments for approval; Inventory checks it before ordering, since an unpaid vendor will not ship. The link from ticket 101 shows which customer order a bill belongs to. |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | The shop space. Facilities confirms the rent amount and due date for ticket 102; after a rent payment `next_due` advances one month. Accounting reads it to plan cash. |
| `cash_accounts` | `name`, `balance`, `date` | The budget. Every payment is checked against `balance` (rule 6) and lowers it (rule 7). Boss reads it for final calls, such as whether the hoodie restock can be funded. |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | The record of money out. Written only by the `pay` tool after a human approves; `approved_by NOT NULL` is the schema's own guard for rule 5. Accounting and the dashboard read it. |
| `desk` | `date_today`, `notes` | The shop's clock (rule 2). Every agent calls `get_today` instead of the real date; overdue days, payment dates, and arrival dates are computed from it. `notes` is free text, empty in the seed. |

### 1.3 Relationships

Declared foreign keys:

- `invoices.vendor_id -> vendors.id`
- `tickets.invoice_id -> invoices.id`
- `tickets.lease_id -> leases.id`

Links that exist by convention rather than by constraint, which the tools must respect by hand:

- `tickets.sku` and `tickets.size` name a row of `inventory`; `inventory.sku` names a row of `pricing`.
- `payments.ref_id` is untyped. `payments.kind` says what it points at (an invoice, a lease, a
  purchase order). The tools will write `kind` values of `invoice`, `rent`, and `purchase_order`.
- `payments.account` names a row of `cash_accounts` (`checking`).
- `payments.approved_by` is `NOT NULL`: the schema itself refuses a payment with no named approver.
  This is the hook for the human-approval rule.

### 1.4 The tickets

All three were created on the shop's today, 2026-08-31, and all are `open`.

| Id | Type | Requester | What they want | Links | What the data says |
|---|---|---|---|---|---|
| 101 | `customer_order` | Tauhid Zaman | One `CC-TEE-WHITE`, size S | invoice 501 | Size S is at **0**. Invoice 501 is a rush reprint of exactly this item, three days overdue |
| 102 | `rent_notice` | Elm City Properties | "shop rent due in 2 days" | lease 1 | $2,400 due 2026-09-02 |
| 103 | `price_override` | Yale AI Club | 20 `CC-HOOD-NAVY`, size M, at a bulk discount | none | **8** mediums in stock, 12 short; cost $22, list $58 |

### 1.5 Stock and pricing

| SKU | Name | Sizes and quantities | Aisle | Unit cost | List price | Margin per unit |
|---|---|---|---|---|---|---|
| `CC-HOOD-NAVY` | Basic Hoodie Big Yale | S 4, M 8, L 14, XL 6 (32 total) | A | $22.00 | $58.00 | $36.00 (62%) |
| `CC-TEE-WHITE` | Classic Bulldog Tee | S **0**, M 5, L 3, XL 2 (10 total) | B | $8.00 | $28.00 | $20.00 (71%) |
| `CC-HAT-BLUE` | Yale Cap | OS 40 | C | $6.00 | $22.00 | $16.00 (73%) |
| `CC-MUG-CREST` | Crest Mug | OS **0** | D | $3.50 | $14.00 | $10.50 (75%) |

Two sizes are sold out: the tee in S (which ticket 101 needs) and the mug (which no ticket mentions).
"OS" means one size.

### 1.6 Vendors

| Id | Vendor | Specialty | Lead time | Relevant to |
|---|---|---|---|---|
| 1 | Bulldog Print Co | apparel reprint | 5 days | tee and hoodie restocks; holds the open invoice |
| 2 | Elm City Gifts | mugs and small goods | 3 days | the mug |
| 3 | QuickShip CT | local courier | 1 day | delivering a customer order |

A restock ordered from Bulldog Print Co on the shop's today would arrive 2026-09-05; from Elm City
Gifts, 2026-09-03.

### 1.7 Money

- **Cash:** `checking`, $3,400.00, as of 2026-08-31.
- **Invoice 501:** Bulldog Print Co, $840.00, "Rush reprint CC-TEE-WHITE S", due 2026-08-28,
  status `open`. By the shop's clock it is **three days overdue**.
- **Lease 1:** Chapel Street shop, landlord Elm City Properties, $2,400.00 a month, next due
  **2026-09-02**, two days away.
- **Payments:** none yet.

The squeeze the data sets up:

| | Amount | Running balance |
|---|---|---|
| Opening cash | | $3,400.00 |
| Rent (due in 2 days) | $2,400.00 | $1,000.00 |
| Invoice 501 (overdue) | $840.00 | $160.00 |
| Hoodie restock for ticket 103: 12 × $22 | $264.00 | **not affordable** |

No revenue is modeled, so nothing comes in to change this picture.

### 1.8 Data quirks to design around

- **Tickets are polymorphic.** One table holds orders, rent notices, and discount requests; which of
  `sku`/`size`/`qty`/`lease_id`/`invoice_id` is filled depends on `type`. New ticket types (for
  example an unpaid vendor bill, or a restock the Inventory agent decides to raise) fit the same
  shape. Tools should accept any `type` string and the Boss should route on it.
- **Requesters are free text.** There is no customer table, so a customer message is addressed to
  the requester name on the ticket.
- **Dates are ISO text.** `created_at` carries a `-04:00` offset; the other dates are plain
  `YYYY-MM-DD`. Date math (overdue, arrival dates) should work on the date part only.
- **Amounts are REAL.** Compare money in cents or with rounding to two places; never test floats
  for equality.
- **Status values are plain strings.** Only `open` appears. The project will use lowercase words:
  `open`, `in_progress`, `waiting_approval`, `resolved` for tickets; `open`, `paid` for invoices.
- **`desk` has no key.** It is a one-row table; the tools read the first row and never insert.
- **`inventory` is keyed by (sku, size).** A restock updates `qty` on an existing row; it does not
  insert a second row for the same size.
- **Nothing in the schema records who is working a ticket, what was decided, or why.** See 1.9.

### 1.9 What the data does not have

The board, the approval queue, and the agents' working notes need storage the file does not provide.
The working copy will gain these on first start (section 3.3): `ticket_events` (the activity feed
and audit log), `approvals` (anything that needs a human decision), `drafts` (customer messages),
`purchase_orders`, and four columns on `tickets` (`assigned_to`, `priority`, `resolution`,
`updated_at`). The original file is never altered; a reset recreates the additions.

---

## 2. Shop rules and where each is enforced

The rules were set on 2026-11-02 (prompt log, "Shop rules"). The design principle: **a rule is
enforced in a tool, not in a prompt.** Prompts tell agents what the rules are so they plan sensibly,
but the MCP server refuses anything that breaks one, whatever an agent asks for.

| # | Rule | Enforced where | How it is tested |
|---|---|---|---|
| 1 | Agents read and write `data/campus_customs_new.db`; the original is untouched | `db_path()` in `mcp_server/db.py` points at the working copy and refuses to open the original even when `CAMPUS_DB_PATH` names it; the back end and the dashboard never open SQLite, they call tools | Every test runs on a temporary copy and re-checks the original's SHA-256 afterwards; the full run's end state (section 12) is read from the working copy |
| 2 | `desk.date_today` is today | `get_today` tool; every tool that judges "overdue" or computes an arrival date reads it; the real clock is used only for ordering log rows | Test: an invoice due 2026-08-28 is overdue by 3 days when `date_today` is 2026-08-31 |
| 3 | Lead times come from `vendors` | `create_purchase_order` sets `expected_date = today + lead_days` from the vendor row | Test: a Bulldog Print Co order on 2026-08-31 expects 2026-09-05 |
| 4 | A vendor with an open invoice will not ship | `create_purchase_order` refuses when the vendor has any invoice with status `open`; `pay` re-checks before marking a purchase order as ordered | Test: an order from vendor 1 is refused while invoice 501 is open and accepted once it is paid |
| 5 | Human approval for any payment; a payment updates the relevant tables | `request_approval` only creates a *pending* row in `approvals`; `pay` requires an approval with status `approved` by the same named human, then in one transaction inserts into `payments`, lowers `cash_accounts.balance`, and marks the invoice `paid`, advances the lease `next_due` by one month, or marks the purchase order `ordered`. `pay` and `decide_approval` are hidden from every agent's toolset; only the human's path calls them (`POST /approvals/{id}/approve`, the console runner) | Tests: `pay` on a pending approval is refused; after approval all the tables change together; the API's approve test pays the rent and sees the lease move |
| 6 | No negative balances | `pay` refuses when `balance < amount` and leaves every table unchanged | Test: with $160 in the account a $264 payment is refused |
| 7 | Cash only goes out | `pay` is the only tool that writes `cash_accounts`, and it only subtracts; there is no deposit or revenue tool | Review of the tool list; test that no tool raises the balance |
| 8 | Reset before a full run | `python -m mcp_server.reset` and `POST /reset` (the dashboard's two-click Reset) copy the original over the working copy and re-apply the schema additions; the reset is a script and a route, never a tool, so agents cannot reach it; refused while a run is in progress; every reset is written to the audit trail | Tests: after a reset the counts are the seed's and checking is $3,400; the original's hash is unchanged |
| 9 | No emails; drafts stay on the board | `draft_customer_message` writes to `drafts`; there is no send tool and the back end has no mail code | Review of the tool list; drafts appear in the dashboard only |
| 10 | One model through Portkey | One `get_model()` in the back end returning `gpt-6-luna` through `PORTKEY_BASE_URL` with `PORTKEY_API_KEY`; every agent is built from it | A first call at the back-end step confirms the gateway accepts the name; the audit trail records the model on every run |

---

## 3. Build outline (design as of 2026-11-03)

### 3.1 Three pieces, one working database

```
 React dashboard (Vite, :5173)        board · live activity · approvals · drafts · shop snapshot · run / reset
         │  REST + server-sent events
         ▼
 FastAPI back end (:8000)             five PydanticAI agents · delegation · run loop · approvals · audit trail
         │  MCP client (streamable HTTP)
         ▼
 MCP server (FastMCP, :8100)          every shop tool · every shop rule
         │
         ▼
 data/campus_customs_new.db           working copy   ◄── reset copies data/campus_customs.db over it
```

Why three processes rather than one: the assignment asks for three pieces that talk to each other,
and the separation is what makes the rules trustworthy. The agents cannot reach the database except
through the MCP server, so a rule enforced there holds no matter what an agent decides. The
dashboard cannot reach the MCP server at all; it only sees what the back end exposes.

Ports 8000 and 5173 are also used by the Homework 4 project. Its servers are stopped before this
project's are started, and this folder's `.claude/launch.json` will list only this project's three
servers.

### 3.2 MCP server: the tools

Python, the official MCP SDK (`mcp`, FastMCP), streamable HTTP on port 8100. One module opens the
database (working copy only), one module per table group holds the queries, and the tool functions
are thin wrappers that validate inputs, apply the rule, and return plain JSON.

Read tools (no rule, no side effects):

| Tool | Returns |
|---|---|
| `get_today` | the shop's date and the free-text desk notes |
| `list_tickets(status?)`, `get_ticket(id)` | tickets with their linked invoice or lease, assignee, priority, resolution |
| `get_stock(sku, size?)` | inventory rows, with the pricing row attached |
| `get_pricing(sku)` | unit cost, list price, margin |
| `list_vendors()` | vendors with lead times and whether each has an open invoice |
| `get_cash()` | balance and as-of date |
| `list_invoices(status?)` | invoices with vendor name and days overdue against the shop's today |
| `get_lease(id)` | the lease with days until next due |
| `list_purchase_orders(status?)`, `list_approvals(status?)`, `list_drafts(ticket_id?)` | the new tables |

Write tools, and the rule each carries:

| Tool | What it does | Rule |
|---|---|---|
| `open_ticket(type, requester, subject, notes, sku?, size?, qty?, lease_id?, invoice_id?)` | inserts a ticket with status `open` and logs an event | any agent may raise one (the brief: "they should be able to open tickets") |
| `assign_ticket(id, agent)`, `set_priority(id, n)` | Boss's routing; both log an event | |
| `log_event(ticket_id?, kind, message, data?)` | a note on the activity feed; also written by the back end for delegations and tool calls | the audit trail |
| `draft_customer_message(ticket_id, recipient, subject, body)` | inserts a draft | 9: there is no send tool |
| `create_purchase_order(ticket_id?, vendor_id, sku, size, qty)` | refuses if the vendor has an open invoice; otherwise inserts a `draft` purchase order priced at `unit_cost × qty` with `expected_date = today + lead_days` | 3, 4 |
| `request_approval(ticket_id, kind, ref_id?, amount, rationale)` | inserts a `pending` row in `approvals`; moves the ticket to `waiting_approval`; never touches money. Kinds: `invoice`, `rent`, `purchase_order`, `price_override` | 5 |
| `pay(approval_id, approved_by)` | requires the approval to be `approved` and the name non-empty; refuses if `balance < amount`; re-checks rule 4 for a purchase order; then, in one transaction, inserts the payment dated the shop's today, subtracts from `checking`, and marks the invoice `paid` / advances the lease one month / sets the purchase order to `ordered`; marks the approval `executed` | 5, 6, 7 (only subtracts) |
| `resolve_ticket(id, resolution)` | sets status `resolved` with the Boss's summary | |

Not a tool: `reset_demo_data.py` (rule 8) is a script and an admin endpoint. Agents cannot reset.

### 3.3 Schema additions (working copy only, created if missing)

```sql
CREATE TABLE IF NOT EXISTS ticket_events (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,                 -- NULL for shop-wide events (run started, reset)
    agent TEXT NOT NULL,               -- boss | inventory | accounting | facilities | customer_service | human | system
    kind TEXT NOT NULL,                -- note | assign | delegate | tool | approval_requested | approved | rejected | paid | resolved | error
    message TEXT NOT NULL,
    data TEXT,                         -- JSON details (tool arguments, amounts, ids)
    created_at TEXT NOT NULL           -- real wall-clock time, for ordering the feed
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,
    kind TEXT NOT NULL,                -- invoice | rent | purchase_order | price_override
    ref_id INTEGER,                    -- invoice id, lease id, purchase order id, or NULL
    amount REAL NOT NULL,              -- 0 for a price override
    account TEXT NOT NULL DEFAULT 'checking',
    rationale TEXT NOT NULL,
    requested_by TEXT NOT NULL,        -- agent name
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected | executed
    decided_by TEXT, decided_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
    author TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER, vendor_id INTEGER NOT NULL,
    sku TEXT NOT NULL, size TEXT NOT NULL, qty INTEGER NOT NULL,
    unit_cost REAL NOT NULL, total REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',     -- draft | waiting_approval | ordered | received
    expected_date TEXT,
    created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
ALTER TABLE tickets ADD COLUMN assigned_to TEXT;
ALTER TABLE tickets ADD COLUMN priority INTEGER;      -- 1 = most urgent
ALTER TABLE tickets ADD COLUMN resolution TEXT;
ALTER TABLE tickets ADD COLUMN updated_at TEXT;
```

Two clocks on purpose: `payments.paid_at`, `purchase_orders.expected_date`, and every business
date use the **shop's** today (rule 2); `ticket_events.created_at` and the `*_at` bookkeeping
columns use the **real** time so the feed orders correctly within a run.

### 3.4 FastAPI back end

**Model and gateway.** `get_model()` returns an `OpenAIChatModel("gpt-6-luna")` whose
`OpenAIProvider` wraps an OpenAI client pointed at `PORTKEY_BASE_URL` with `PORTKEY_API_KEY`, the
same construction Homework 4 used. Every agent is built from this one function (rule 10). The first
back-end step makes one real call to confirm the gateway accepts the model name.

**MCP client.** PydanticAI's streamable-HTTP MCP toolset connects to port 8100. Each agent gets the
toolset filtered to its role, so an agent cannot call a tool it was not given:

| Tool | Boss | Inventory | Accounting | Facilities | Customer Service |
|---|---|---|---|---|---|
| `get_today`, `list_tickets`, `get_ticket`, `log_event`, `open_ticket` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `assign_ticket`, `set_priority`, `resolve_ticket` | ✓ | | | | |
| `get_stock`, `get_pricing`, `list_vendors` | ✓ | ✓ | ✓ | | ✓ (read) |
| `list_invoices` | ✓ | ✓ | ✓ | | |
| `get_cash`, `list_approvals` | ✓ | | ✓ | | |
| `get_lease` | ✓ | | ✓ | ✓ | |
| `create_purchase_order`, `list_purchase_orders` | | ✓ | ✓ (list) | | ✓ (list) |
| `request_approval` | ✓ (price override) | | ✓ (payments) | | |
| `draft_customer_message`, `list_drafts` | ✓ (list) | | | | ✓ |
| `pay` | — | — | — | — | — |

`pay` is in no agent's toolset. Only the approve endpoint calls it.

**Full connectivity: `ask_colleague(agent, request)`.** A back-end tool (not an MCP tool) given to
all five agents. It runs the named agent on the request with the same ticket context and returns
that agent's answer as the tool result (PydanticAI's agent-as-tool pattern), so any agent can get
help from any other. Guards: an agent cannot ask itself; delegation depth is at most three; all
agents working one ticket share one token budget; and only Boss can resolve a ticket, so a specialist
that is asked for help returns advice rather than closing anything.

**Prompts.** `backend/prompts/<agent>.md`, one per agent, read on each run so an edit takes effect on
the next ticket without a restart (as in Homework 4). Each prompt states the agent's job, the rules
in plain words, which colleagues exist and what they are good for, and the shape of the answer Boss
expects back.

**Run loop.** `POST /api/run` starts a background run and returns at once. Boss first reads every
open ticket and sets a priority order (the rent notice outranks the overdue invoice, which outranks
the discount request), then works tickets one at a time so each cash decision sees the previous one.
Ticket statuses: `open` → `in_progress` → `waiting_approval` (if something needs a human) →
`resolved`. A ticket left `waiting_approval` does not block the run; the others continue.

**Approvals: a round trip.** `GET /api/approvals` lists pending items. `POST
/api/approvals/{id}/approve` with the approver's name calls `pay` through MCP (for a price override
there is nothing to pay; the decision is just recorded), then re-runs Boss on that ticket with the
outcome so it can finish: for example, ask Inventory to confirm the purchase order is now `ordered`
and Customer Service to draft the reply. `POST /api/approvals/{id}/reject` records the rejection and
re-runs Boss the same way. Nothing moves money without the click.

**Live feed and snapshots.** `GET /api/events/stream` is a server-sent-events stream of new
`ticket_events` rows; `GET /api/board` returns tickets grouped by status with the latest event per
ticket; `GET /api/shop` returns cash, inventory, invoices, lease, purchase orders, drafts.
`GET /api/health` reports the database file in use, the MCP server's reachability, and the model name.

**Admin.** `POST /api/admin/reset` performs rule 8 and is refused while a run is in progress.

**Audit trail.** One JSON line per agent run in `output/audit_trail.json` (agent, ticket, every tool
call with arguments and a result preview, delegations, the final answer, token usage, duration,
outcome), the Homework 4 format.

### 3.5 React dashboard

Vite + React + TypeScript, the Homework 4 stack, with the same proxy arrangement (`/api` forwarded to
port 8000). Panels:

- **Board:** four columns by status; a card shows type, requester, subject, assignee, priority, and
  the latest note; clicking opens the ticket's full event history, drafts, and approvals.
- **Activity:** the live feed, newest first, with the agent name and kind of each event.
- **Approvals:** pending items with amount, rationale, and the cash balance after payment;
  Approve and Reject buttons; a name field that must be filled (it becomes `approved_by`).
- **Drafts:** customer messages, read-only, grouped by ticket.
- **Shop:** cash, inventory table, invoices, lease, purchase orders.
- **Toolbar:** Run agents, Reset (with confirmation), New ticket (a small form that calls
  `open_ticket` through the back end, so a human can add "whatever the shop has to handle").

### 3.6 The story the data tells (what a good run looks like)

1. **Triage.** Boss ranks the rent notice first (eviction risk, due in two days), the tee order
   second (its vendor is blocked by the overdue invoice), the discount request third.
2. **Ticket 102, rent.** Facilities confirms lease 1: $2,400 due 2026-09-02. Accounting checks cash
   ($3,400) and requests a rent payment. Human approves. `pay` records payment 1, cash falls to
   $1,000, `next_due` becomes 2026-10-02. Boss resolves.
3. **Ticket 101, the tee.** Inventory finds size S at 0 and names Bulldog Print Co (5 days) as the
   restock vendor, but `create_purchase_order` is refused: the vendor's invoice 501 is open.
   Accounting notes the invoice is three days overdue, checks that $840 ≤ $1,000, and requests the
   payment. Human approves. Cash falls to $160; the invoice is `paid`. Boss re-runs: Inventory's
   order (or the reprint the invoice already describes) can ship, expected 2026-09-05; Customer
   Service drafts a note to Tauhid Zaman with that date. Boss resolves.
4. **Ticket 103, twenty hoodies.** Inventory: 8 mediums on hand, 12 short; a purchase order for 12
   costs $264. Accounting: only $160 left, so the order cannot be funded; margin check: cost $22,
   list $58, so even a 20% discount ($46.40) keeps a healthy margin. Boss decides between a partial
   offer (8 now at a discount, 12 later when cash allows) and a decline, raises the price override
   as an approval item, and has Customer Service draft the reply. Human approves or rejects; Boss
   resolves accordingly.
5. **The mug.** Nothing asks about it, but it is at 0 with a vendor three days out. Whether Inventory
   opens a restock ticket on its own is a good test of the team's initiative.

End state to verify after a full run: two rows in `payments`, cash $160, invoice 501 `paid`, lease
`next_due` 2026-10-02, three tickets `resolved`, at least two drafts, every approval `executed` or
`rejected`, and the original database file's hash unchanged.

### 3.7 Build order and status

| Step | What | Status |
|---|---|---|
| 1 | `AI_prompts.md` | done 2026-11-02 |
| 2 | This document, sections 1–3 | done 2026-11-03 |
| 3 | Skeleton: `mcp_server/`, `backend/`, `frontend/`; Python 3.14 virtual environment at the project root shared by the two Python pieces; pinned `requirements.txt` per piece; `.env` and `.env.example`; `.gitignore`; three entries in `.claude/launch.json`; README stub | Python half done 2026-11-03: `.venv`, `mcp_server/`, `pytest.ini`, `.gitignore`, the `mcp-server` launch entry, README stub. `backend/`, `frontend/`, and the `.env` files arrive with their own steps |
| 4 | MCP server, ticket tools (read and write) and the ticket-events feed; verified with 22 tests, through the functions and through an in-memory MCP client | done 2026-11-03, section 4 |
| 5 | MCP server, the remaining tools: stock, pricing, vendors, cash, invoices, lease, purchase orders, approvals, drafts, and `pay` carrying rules 4–7; the reset script; one test per rule (all tests run against a temporary copy, never the working copy) | done 2026-11-03, section 5 (26 tools, 31 tests) |
| 6 | Back end skeleton: `get_model()` and a first call to confirm `gpt-6-luna`; MCP client; health, board, shop, event stream | model, MCP client, and run loop done 2026-11-03 (section 6); the HTTP endpoints move to step 8 |
| 7 | Agents: Boss and Inventory with `ask_colleague` first; then Accounting, Facilities, Customer Service; prompts; role-based tool access | done 2026-11-03, section 6 (all five at once; same tools for all, three hidden) |
| 7b | Expected outcomes per ticket, written before the run: `output/desk_tickets.html` (one tab per ticket with first call, delegations, tools, end state; Actual slots for after the runs; Cash and Reflection tabs reserved) | done 2026-11-03, section 9 |
| 8 | Approval flow end to end through the API | done 2026-11-03, section 10 (`backend/main.py`, 14 routes; approve → pay → the Boss re-works the ticket in the background) |
| 9 | Dashboard | done 2026-11-03, section 11 (`frontend/`, React 19 + Vite 8 + TypeScript; the design and why in `output/design.md`, screenshots in `output/screens/`) |
| 10 | Full run from a reset; verify the end state in 3.6; operational check with screenshots; README; submission archive; public repository | done: the run 2026-11-03, section 12 (three tickets resolved from the dashboard, $3,400 → $152, `output/resolved_tickets.json`, `output/resolved_board.html`, the desk page's Actual, Cash and Reflection tabs); archive `campus-customs-hw5-submission.zip` and public repository https://github.com/AMR6958-coder/campus-customs-hw5 on 2026-11-04 (no `.env`; both database files under `data/` committed) |

### 3.8 Open items

- **Model name.** `gpt-6-luna` is used as instructed; Homework 4 ran on `gpt-5.6-luna`. Confirmed
  or corrected at step 6 with one real call.
- **Should the reprint on invoice 501 count as stock on the way?** The invoice describes a rush
  reprint of the tee in S but no quantity or arrival date. The design treats paying it as what
  unblocks the vendor, and lets Inventory decide whether a fresh purchase order is still needed.
- **Who may open tickets.** The brief says the team should be able to; the design gives
  `open_ticket` to every agent and a New ticket form to the human. If that proves noisy, it can be
  narrowed to Boss and Inventory.

---
- **fastmcp `Client` over HTTP fails on this machine** (body cut off; see 5.8). Use the `mcp` SDK
  client in the back end. Revisit if a later fastmcp release or a change to the local proxy fixes it.

## 4. The MCP server, part 1: ticket tools (2026-11-03)

The first piece of code. The server is written with FastMCP, works only on the working copy, and
for now exposes the tools needed to run the ticket board. Every agent may use every tool (the
user's instruction at this step); the rules that need a human will be enforced by the tools
themselves when they arrive in part 2.

### 4.1 Layout

```
.venv/                       Python 3.14 environment for both Python pieces (git-ignored)
mcp_server/
  __init__.py
  db.py                      the one database file, the schema additions, the per-call connection
  tickets.py                 ticket functions over a connection: validation, SQL, event log
  server.py                  the FastMCP server: thin tool wrappers, instructions, port 8100
  requirements.txt           fastmcp==4.1.6, pytest==9.2.0
  tests/test_tickets.py      22 tests on a temporary copy of the database
pytest.ini                   test path and import root
.claude/launch.json          mcp-server: .venv/Scripts/python -m mcp_server.server
.gitignore, README.md
```

The split matters: `tickets.py` does the work with plain functions that take a connection and
return dicts, so the tests call them directly and the MCP layer in `server.py` is only a wrapper
that opens a connection per call. `backend/` will connect to the server over MCP; it never imports
these modules.

### 4.2 The one-database rule, in code (rule 1)

`db.py` names two paths. `WORKING_DB_PATH` is `data/campus_customs_new.db` and is the default.
`ORIGINAL_DB_PATH` is `data/campus_customs.db`; `db_path()` raises if the configured path resolves
to it, so nothing in the package can open the original even by mistake. `CAMPUS_DB_PATH` overrides
the file for the tests. `connect()` opens the file for one call, turns foreign keys on, commits when
the call finishes, rolls back if it raises, and closes.

### 4.3 Schema additions

On every connection `ensure_schema()` adds what is missing and is harmless to re-run: the columns
`assigned_to`, `priority`, `resolution`, `updated_at` on `tickets`, and the `ticket_events` table
(id, ticket_id, agent, kind, message, data as JSON, created_at). Because the working copy has not
been opened yet, it is still byte-identical to the original; the additions will land the first time
a tool touches it. The other tables from section 3.3 (approvals, drafts, purchase orders) arrive
with their tools.

### 4.4 The tools

| Tool | Kind | Inputs | Refuses when |
|---|---|---|---|
| `get_today` | read | none | the desk table is empty |
| `list_tickets` | read | `status?` | the status is not one of the four |
| `get_ticket` | read | `ticket_id` | the ticket does not exist |
| `list_ticket_events` | read | `ticket_id?`, `since_id?`, `limit` | the ticket does not exist; limit outside 1–1000 |
| `open_ticket` | write | `type`, `requester`, `subject`, `notes?`, `sku?`, `size?`, `qty?`, `lease_id?`, `invoice_id?`, `agent` | a required text is blank; the sku (or sku and size) is not in inventory; the lease or invoice does not exist; qty is not positive; a size is given without a sku; the agent is unknown |
| `assign_ticket` | write | `ticket_id`, `assigned_to`, `agent` | the assignee is not one of the five agents; the ticket is resolved |
| `set_ticket_priority` | write | `ticket_id`, `priority`, `agent` | priority is below 1 |
| `set_ticket_status` | write | `ticket_id`, `status`, `agent` | the status is `resolved` (use `resolve_ticket`) or unknown |
| `add_ticket_note` | write | `ticket_id`, `note`, `agent` | the note is blank; the ticket does not exist |
| `resolve_ticket` | write | `ticket_id`, `resolution`, `agent` | the resolution is blank; the ticket is already resolved |

Every write tool takes `agent` (one of the five agents, or `human` or `system`) and records a row
in `ticket_events` saying who did what, with the details as JSON. A refusal is a `ValueError` with a
sentence that says what to fix; FastMCP returns it to the caller as a tool error, which an agent
sees as text and can act on.

### 4.5 Nothing is invented

`get_ticket` returns the ticket row plus a `links` object. Every added value traces to the
database:

| Value | Source |
|---|---|
| `shop_today` | `desk.date_today` |
| `links.invoice` | the `invoices` row joined to its `vendors` row; `days_overdue` = shop today − `due_date`, 0 unless the invoice is open and past due |
| `links.lease` | the `leases` row; `days_until_due` = `next_due` − shop today |
| `links.stock` | the `inventory` rows for the ticket's sku; `requested_size` marks the row whose size matches the ticket |
| `links.pricing` | the `pricing` row for the sku |

Two clocks, as designed in 3.3: a new ticket's `created_at` is the shop's date with the wall-clock
time of day and the `-04:00` offset the seed rows use; `updated_at` and `ticket_events.created_at`
are real time, for ordering.

### 4.6 Decisions made at this step

- **fastmcp 4.1.6.** The `fastmcp` package on PyPI is now a meta-package that installs
  `fastmcp-slim[client,server]` with the `mcp` SDK 2.3.0 underneath. The API used: `FastMCP(name,
  instructions)`, `@mcp.tool()`, `mcp.run(transport="http", host, port)` for streamable HTTP, and
  `Client(mcp)` as an in-memory client for the tests, with `ToolError` for refusals.
- **One virtual environment at the root**, shared by the MCP server and, later, the back end.
- **Every agent gets every tool.** The human-approval gate will sit on the `pay` tool's inputs (an
  approved approval and an approver's name), not on who is calling.
- **Tests never touch the working copy.** The fixture copies the original to a temporary file, points
  `CAMPUS_DB_PATH` at it, and asserts afterwards that the original's SHA-256 is unchanged.
- **Install workaround.** On this machine `pip install` failed every time with an
  `InvalidChunkLength` error while fetching one metadata file (the `httpx2` sidecar); the server
  serves the file correctly and the same URL reads fine with curl, and `uv` reported an unknown
  certificate issuer, which points to a certificate-intercepting proxy on the connection. Installing
  `uv` into the environment and running it with `--system-certs` worked. The README records this.

### 4.7 Verified (2026-11-03)

`.venv\Scripts\python -m pytest`: 22 passed in 3.2 s. What they cover:

- `db_path()` refuses the original; the schema additions appear on the copy only; the seed's three
  tickets and zero events are intact; the shop's date reads as 2026-08-31; a call that raises after a
  write is rolled back.
- `list_tickets` returns 101, 102, 103, all open; filtering by status works; a bad status is refused.
- `get_ticket` 101 links invoice 501 (Bulldog Print Co, 5-day lead, $840, open, 3 days overdue), the
  four tee sizes with S flagged at 0, and the tee's pricing; 102 links lease 1 (2 days until due);
  103 links the hoodie stock with M flagged at 8; 999 is refused.
- `open_ticket` creates ticket 104 dated the shop's today with one `opened` event; eight kinds of
  bad input are refused and leave the board at three tickets.
- Assigning sets the assignee and moves open to in_progress; priorities order the list; status
  changes and notes are logged in order with their details; `since_id` filters the feed; resolving
  records the resolution, a second resolve and an assignment are refused, and reopening clears the
  resolution while keeping the old text in the event.
- Through FastMCP's in-memory client: the ten tools are listed, `get_today` and `list_tickets`
  return the seed, `get_ticket(999)` surfaces as a tool error, and `add_ticket_note` writes through
  the protocol.

After the tests, both database files still have the original SHA-256. The server was not started
or connected to anything at this step (not required by the user); the launch entry and the run
command in the README are ready for when it is.

## 5. The MCP server, part 2: shop, money, and the rules (2026-11-03)

### 5.1 Layout

Two new modules beside `tickets.py`, same shape (every function takes an open connection, returns
plain dicts, logs an event for every write): `shop.py` for the read-only tables and `money.py` for
purchase orders, approvals, drafts, and `pay`. `reset.py` is the rule 8 script. `server.py` gained
sixteen thin wrappers, for 26 tools in all.

### 5.2 Schema additions

`approvals`, `drafts`, and `purchase_orders` exactly as in 3.3, with one extra column:
`approvals.decision_note` keeps the human's one-line reason. Created on the working copy only, the
first time a connection opens; the seed file is never touched.

### 5.3 The tools

| Tool | Returns / does | Where the values come from |
|---|---|---|
| `get_stock(sku, size?)`, `list_stock()` | inventory rows with pricing | `inventory`, `pricing` |
| `get_pricing(sku)` | unit cost, list price, margin, margin % | `pricing`; margin = list − cost |
| `list_vendors()` | vendors with `open_invoice_ids`, `open_invoice_total`, `can_ship` | `vendors`, `invoices`; `can_ship` = no open invoice |
| `list_invoices(status?)` | invoices with vendor name and `days_overdue` | `invoices`, `vendors`, `desk.date_today` |
| `get_lease(id)` | lease with `days_until_due` | `leases`, `desk.date_today` |
| `get_cash()`, `list_payments()` | balances and the payments made | `cash_accounts`, `payments` |
| `create_purchase_order(vendor_id, sku, size, qty, agent, ticket_id?)` | a `draft` order, `total = unit_cost × qty`, `expected_date = today + lead_days`; refused while the vendor has an open invoice | `pricing`, `vendors`, `invoices` |
| `request_approval(kind, rationale, agent, ref_id?, ticket_id?)` | a `pending` approval whose amount is read from the invoice, lease, or order; ticket → `waiting_approval`; one live approval per reference | the referenced row |
| `decide_approval(id, decision, decided_by, note?)` | `approved` or `rejected`; a rejection returns the order to `draft` and the ticket to `in_progress` | the human |
| `pay(approval_id, approved_by)` | the only cash movement (see 5.4) | `approvals`, `cash_accounts` |
| `draft_customer_message(ticket_id, recipient, subject, body, agent)`, `list_drafts(ticket_id?)` | a saved draft; nothing sends | the agent's text |
| `list_purchase_orders(status?)`, `list_approvals(status?)` | the restock orders (with vendor name and lead days) and the approval queue, filtered by status | `purchase_orders` + `vendors`, `approvals` |

### 5.4 Rules, in code

| Rule | Enforced in | How |
|---|---|---|
| 3 lead times from `vendors` | `create_purchase_order` | `expected_date = shop today + vendors.lead_days` |
| 4 unpaid vendor will not ship | `create_purchase_order`, and again in `pay` for an order | refused with the open invoice id and amount in the message |
| 5 human approval for payments | `pay` | approval must be `approved`; `approved_by` must equal `decided_by`; executed once; payments row, balance, invoice/lease/order, and approval all updated in one transaction |
| 6 no negative balances | `pay` | `balance < amount` refuses before any write; the message shows both figures |
| 7 cash only goes out | `request_approval`, `pay` | negative amounts refused; a price override carries no payment; no code path adds to a balance |
| 8 reset before a full run | `reset.py` | copies the original over the working copy, logs a `reset` event; not an MCP tool |
| 9 drafts stay on the board | the tool list | no send or email tool exists; a test asserts it |

Amounts are never typed in by an agent. An approval takes its amount from the row it refers to,
and `pay` re-reads that row and refuses if the figure has changed since the approval.

### 5.5 Decisions made at this step

- **`decide_approval` is a tool** so the back end's approve endpoint and the tests use the same
  code path, but it is meant for the human: the back end will expose it only through the dashboard.
  The same is true of `pay`, which section 3.4 already keeps out of every agent's tool list.
- **Rent advances the lease one month** on payment (`next_due` 2026-09-02 → 2026-10-02), the one
  interpretation of "update the relevant table" that leaves the lease consistent.
- **A rejected approval unwinds**: the order goes back to `draft`, the ticket to `in_progress`, so
  the Boss can try another plan.
- **Rule 10 is not tested here**: the model choice belongs to the back end and will be verified
  with one real call at that step.

### 5.6 Every tool: what it reads, what it writes, which ticket it unlocks

All 26 tools the server lists, checked against the running server with FastMCP's in-memory client.
The three seed tickets: **101** customer order (Tauhid Zaman, one `CC-TEE-WHITE` S; the S shelf is
empty and the reprint vendor is owed $840 on invoice 501), **102** rent notice (lease 1, $2,400 due
in two days), **103** price override (Yale AI Club, twenty `CC-HOOD-NAVY` M; the shelf holds eight).

| Tool | Reads | Writes | Ticket(s) | Why it is the right tool |
|---|---|---|---|---|
| `get_today` | `desk` | | 101, 102, 103 | Every overdue and due-date judgement (invoice 501 three days late, rent in two days, delivery dates) starts from the shop's own date, never the real calendar. |
| `list_tickets` | `tickets` | | 101, 102, 103 | The Boss's first move is to see the whole inbox, in priority order, before deciding who works what. |
| `get_ticket` | `tickets`, `invoices`, `vendors`, `leases`, `inventory`, `pricing`, `desk` | | 101, 102, 103 | One call hands the worker everything the ticket links to: 101's tee stock and overdue invoice, 102's lease and days until due, 103's hoodie stock and pricing. |
| `list_ticket_events` | `ticket_events` | | 101, 102, 103 | An agent (and the dashboard) can see what colleagues already did on a ticket before acting again. |
| `open_ticket` | `inventory`, `leases`, `invoices`, `desk` | `tickets`, `ticket_events` | 101, 103 | When Inventory finds tee S at zero or hoodie M twelve short, it raises a restock ticket instead of burying the finding in a note. |
| `assign_ticket` | `tickets` | `tickets`, `ticket_events` | 101, 102, 103 | The Boss routes 101 to Inventory and Customer Service, 102 to Facilities, 103 to Inventory and Accounting, and the board shows who has it. |
| `set_ticket_priority` | `tickets` | `tickets`, `ticket_events` | 101, 102, 103 | Rent due in two days outranks a one-tee order, and the Boss records that ranking so the board sorts by it. |
| `set_ticket_status` | `tickets` | `tickets`, `ticket_events` | 101, 102, 103 | Moves a ticket back to in_progress after a rejected approval, or reopens one the human sends back. |
| `add_ticket_note` | `tickets` | `ticket_events` | 101, 102, 103 | Findings and handoffs (a stock count, a margin, a vendor's status) go on the ticket where the Boss and the human read them. |
| `resolve_ticket` | `tickets` | `tickets`, `ticket_events` | 101, 102, 103 | The Boss's final call, with the written resolution the brief asks for. |
| `get_stock` | `inventory`, `pricing` | | 101, 103 | Shows tee S at 0, so 101 cannot ship today, and hoodie M at 8 against 20 wanted, so 103 is twelve short. |
| `list_stock` | `inventory`, `pricing` | | 101, 103 | The whole shelf at once, so Inventory can see the other sizes (tee M 5, L 3) when weighing a substitute. |
| `get_pricing` | `pricing` | | 103 | Hoodie cost $22 against list $58 is the margin Accounting checks before any club discount. |
| `list_vendors` | `vendors`, `invoices` | | 101, 103 | Shows Bulldog Print Co is the apparel reprint vendor for both (5-day lead) and that it will not ship until invoice 501 is paid. |
| `list_invoices` | `invoices`, `vendors`, `desk` | | 101 | Invoice 501, open, $840, three days overdue, is the thing blocking the tee reprint. |
| `get_lease` | `leases`, `desk` | | 102 | Lease 1: Elm City Properties, $2,400, next due 2026-09-02, two days out. |
| `get_cash` | `cash_accounts` | | 101, 102, 103 | $3,400 in checking is what Accounting must stretch across the invoice, the rent, and any restock. |
| `list_payments` | `payments` | | 101, 102, 103 | What has already gone out this run, so nothing is paid twice. |
| `list_purchase_orders` | `purchase_orders`, `vendors` | | 101, 103 | Which restock orders exist, and their status, before anyone drafts another. |
| `create_purchase_order` | `vendors`, `invoices`, `inventory`, `pricing`, `desk` | `purchase_orders`, `ticket_events` | 101, 103 | Prices the tee or hoodie reprint from the pricing table and dates it from Bulldog's 5-day lead, and refuses while invoice 501 is unpaid, which is exactly the shop's rule. |
| `list_approvals` | `approvals` | | 101, 102, 103 | The human's queue; the Boss can see what is still waiting before resolving anything. |
| `request_approval` | `invoices` / `leases` / `purchase_orders` (for the amount), `tickets` | `approvals`, `tickets`, `purchase_orders`, `ticket_events` | 101 (invoice 501), 102 (rent), 103 (hoodie order, price override) | Every dollar out goes past a human first, and the amount comes from the row, not from the agent. |
| `decide_approval` | `approvals` | `approvals`, `purchase_orders`, `tickets`, `ticket_events` | 101, 102, 103 | The human's yes or no from the dashboard, recorded with their name. |
| `pay` | `approvals`, `cash_accounts`, `invoices` / `leases` / `purchase_orders`, `vendors`, `desk` | `payments`, `cash_accounts`, `invoices` or `leases` or `purchase_orders`, `approvals`, `ticket_events` | 101 (pays 501, unblocking Bulldog), 102 (pays rent; lease moves to 2026-10-02), 103 (the hoodie order, if cash allows) | The only way money leaves; it refuses the $440 hoodie order when $160 is left, so the cash squeeze is enforced rather than merely noticed. |
| `draft_customer_message` | `tickets` | `drafts`, `ticket_events` | 101, 103 | Customer Service tells Tauhid the tee date and the AI Club the discount decision, on the board, never by email. |
| `list_drafts` | `drafts` | | 101, 103 | The human reads the drafts on the dashboard before deciding whether to send any by hand. |

Ticket 102 never touches stock or vendors, and 103 is the ticket that needs the most tools: stock,
pricing, vendor status, cash, a purchase order, and two kinds of approval.

### 5.7 Verified (2026-11-03)

`.venv\Scripts\python -m pytest`: 31 passed in 3.1 s. The 22 part 1 tests still pass (the MCP
client test now lists 26 tools). `test_rules.py`, one test per rule:

- rule 1: a full approve-and-pay changes the copy's hash and not the original's;
- rule 2: invoice 501 reads 3 days overdue and lease 1 reads 2 days until due, from the desk date;
- rule 3: a mug order from Elm City Gifts lands 2026-09-03 (3-day lead) at $3.50 × 10 = $35.00;
- rule 4: Bulldog Print Co shows `can_ship` false; ordering 20 hoodies is refused naming invoice 501;
  after that invoice is paid the same order succeeds at $440.00, expected 2026-09-05;
- rule 5: `pay` on a pending approval is refused with no payment written; after approval, a
  different name is refused; the right name pays $840.00 dated 2026-08-31, invoice 501 is `paid`,
  checking is $2,560.00, the approval is `executed`, a second `pay` is refused, and the ticket's
  timeline reads approval_requested → approved → paid;
- rule 6: after paying the invoice and the rent the balance is $160.00 and the $440.00 order is
  refused with both figures in the message; the balance and the payment count are unchanged;
- rule 7: a price override approval carries $0 and cannot be paid; the balance only falls;
- rule 8: after a payment and a draft, `reset_working_copy()` leaves 3 tickets, 0 payments, 0
  approvals, 0 orders, 0 drafts, $3,400.00, invoice 501 open, and a single system `reset` event;
- rule 9: a draft is stored with its author, and no tool name contains send, email, or mail.

Two first-run failures were in the tests, not the tools: a guessed mug SKU (the seed's is
`CC-MUG-CREST`) and a refusal message I then made more specific ("already executed"). After the
run, `data/campus_customs.db` and `data/campus_customs_new.db` still share the original SHA-256.
The server was not started or connected at this step.

### 5.8 Connected to the project (2026-11-03)

`.mcp.json` at the project root registers the server with Claude Code as a project-scoped MCP
server:

```json
{
  "mcpServers": {
    "campus-customs": {
      "type": "http",
      "url": "http://127.0.0.1:8100/mcp"
    }
  }
}
```

HTTP rather than stdio, so one running server serves both Claude Code and the back end, and the
tools can be watched from either side. The server must be running first (`mcp-server` launch entry
or `python -m mcp_server.server`); Claude Code reads `.mcp.json` when a session opens and asks once
to approve the project server, after which the tools appear as `mcp__campus-customs__<tool>`.

**Verified** from this project with the standard `mcp` SDK client (`streamable_http_client` +
`ClientSession`) against the running server: initialize returns "Campus Customs Shop"; 26 tools
listed; `get_today` returns 2026-08-31; `list_vendors` returns the three vendors with Bulldog Print
Co's `can_ship` false and invoice 501 listed. The server log shows the full sequence (initialize
200, initialized 202, list and calls 200, session delete 200). A raw `curl` initialize, `urllib`,
and `httpx2` POSTs all get the expected SSE reply at `/mcp`.

**First open of the working copy.** These were the first real calls on `data/campus_customs_new.db`,
so the schema additions were applied: it now has 13 tables (the nine seed tables plus
`ticket_events`, `approvals`, `drafts`, `purchase_orders`) and the four ticket columns. Its SHA-256
therefore differs from the original from here on; the seed rows are intact (3 tickets, 0 events,
checking $3,400) and the original still has its first hash.

**Quirk, recorded as an open item in 3.8.** fastmcp's own `Client` wrapper fails over HTTP on this
machine: its first POST gets a 200 whose body is cut off ("peer unexpectedly closed connection"),
with or without an explicit Accept header. Every other client works, so the cause is in the
environment, most likely the local web-shield proxy that also corrupted pip's chunked downloads.
The back end will use the `mcp` SDK client, which is verified above; the in-memory fastmcp client
the tests use is unaffected.

**Revised the same day: stdio for Claude Code, HTTP for the back end.** The HTTP entry worked in
principle but failed in practice in the desktop app: Claude Code dials project servers once, when
its process starts, and keeps a failed state until the next start; in the desktop app, closing and
reopening a session does not restart that process, while quitting the app kills any server started
in the app's own terminal. The session therefore kept reporting "connection refused" with a healthy
server on port 8100 (verified by `curl`, and visible in that server's log). `.mcp.json` now uses
stdio, so Claude Code owns its copy of the server:

```json
{
  "mcpServers": {
    "campus-customs": {
      "type": "stdio",
      "command": ".venv/Scripts/python.exe",
      "args": ["-m", "mcp_server.server", "--stdio"]
    }
  }
}
```

`server.py` gained the `--stdio` switch (banner off, nothing else on stdout); without it the module
serves HTTP on 8100 as before, which is what the back end and dashboard will use. Two processes
on one SQLite file is fine for this shop's load. **Verified:** spawning the exact command from
`.mcp.json` with the MCP SDK's stdio client, from the project root: initialize returns "Campus
Customs Shop", 26 tools, `get_today` 2026-08-31, `get_ticket(102)` with lease 1 due 2026-09-02 in
two days. 31 tests still pass. The connection from inside Claude Code itself is checked at the next
real start of the app.

**Verified inside Claude Code (2026-11-03, after an app restart).** The stdio entry connected on
startup; the session listed all 26 tools as `mcp__campus-customs__<tool>` and received the server's
instructions. Called from the session: `get_today` → 2026-08-31; `get_ticket(101)` → the tee order
with invoice 501 (Bulldog Print Co, $840, 3 days overdue), tee S flagged at 0, pricing $8/$28;
`list_vendors` → Bulldog Print Co `can_ship` false, the other two true. Step 5 of the build order
is complete and the server is wired into the project.

### 5.9 Smoke test through the connector (2026-11-03)

`output/mcp_smoke.json` records 35 calls made from inside the Claude Code session, covering all 26
tools: each entry has the prompt, the tool, its arguments, the output verbatim, and a `db_check`
with the SQL run afterwards against `data/campus_customs_new.db`, the expected value taken from
the output, the database's value, and `match`. `output/check_mcp_smoke.py` runs the checks and
writes the results back: **35 matched, 0 mismatched**.

Order of the run: the 15 read tools on the untouched seed; then the 11 write tools in the only
order the rules allow (approval requested → approved → paid, which unblocks Bulldog Print Co →
purchase order drafted); then the changed tables read again. For reads taken before the writes,
the SQL checks the columns the writes did not touch or reconstructs the earlier value (the seed
balance equals the current balance plus the payments made since; the vendor's earlier open invoice
is the one now in `payments`). The write checks recompute the derived figures from the source
tables: the order total from `pricing.unit_cost × qty`, the expected date from `desk.date_today +
vendors.lead_days`, the approval amount from `invoices.amount`.

End state of the working copy after the run: four tickets (102 open at priority 1, 101
waiting_approval with Inventory, 103 in_progress, 104 resolved), 11 events, one payment, checking
$2,560, invoice 501 paid, one draft purchase order, one executed approval, one draft message. The
original file is unchanged (same SHA-256 as on day one). The working copy is reset before the full
run, as rule 8 requires.

## 6. The back end: the agent team (2026-11-03)

### 6.1 Layout

```
backend/
  config.py        settings from backend/.env; the model name is a constant (rule 10) and any other
                   value in .env stops the back end; delegation limits; the three hidden tools
  llm.py           get_model(): gpt-6-luna through Portkey, built once (the Homework 4 construction)
  mcp_toolset.py   MCPToolset: every MCP tool becomes a PydanticAI tool, over the mcp SDK client
  models.py        AgentName, TriagePlan, BossDecision, RunEvent, Budget, TeamDeps
  prompts/         shared.md + boss.md, inventory.md, accounting.md, facilities.md, customer_service.md
  agents/          base.py (prompt loader, ask_colleague and its guards, the constructor), one file
                   per agent (boss.py also holds the two task prompts)
  team.py          Team: the connection, the five agents, delegation, triage / work_ticket /
                   run_board, and the human's decide / pay / approve_and_pay
  run.py           console runner; the API (next step) will call the same Team
  tests/           seven offline tests; requirements.txt; .env.example
```

### 6.2 Model and gateway (rule 10)

`get_model()` wraps an OpenAI client pointed at `PORTKEY_BASE_URL` with `PORTKEY_API_KEY` in
`OpenAIChatModel("gpt-6-luna")`, built once and shared by all five agents. The first live attempt
failed with HTTP 400 from the gateway: function tools on the chat-completions endpoint are not
supported for this model unless reasoning effort is "none". The setting is now part of the model
(`OpenAIChatModelSettings(openai_reasoning_effort="none")`); the plain probes had passed because they
carried no tools. The gateway reports the model as `gpt-6-luna-2026-09-22`.

### 6.3 Tools: one toolset, three tools hidden

PydanticAI's own MCP classes are not in the slim install, so `MCPToolset` is ours: on enter it
connects (streamable HTTP for the running server; stdio for the tests), lists the server's tools,
and turns each into a `ToolDefinition` with the server's name, description, and argument schema.
A refusal (`ValueError` on the server) comes back to the model as `{"error": "<sentence>"}` rather
than an exception, because "the vendor will not ship while invoice 501 is unpaid" is a fact to act
on, not a malformed call. Results are read from the SDK's `structured_content`, where FastMCP puts
the value (a list arrives as `{"result": [...]}`, even when empty).

Section 3.4 planned role-based tool access. The build gives every agent the same tools, as the user
asked at the MCP step ("every agent can use the tools in the MCP server"), minus three that
`Team` filters out: `pay` and `decide_approval` (the human's, rule 5) and `log_event` (the back
end's audit trail). Nothing in an agent's reach moves money or approves anything.

### 6.4 Full connectivity, and what keeps it from looping

Every agent carries `ask_colleague(colleague, request)` and may call any other agent with it. The
Team runs the colleague's agent with a child context: depth + 1, chain + colleague, the same
shared budget. `delegation_problem` refuses, with a sentence the model reads: an agent asking
itself; a colleague already in the chain (so boss → inventory → boss is impossible); a chain deeper
than 3; and more than 12 delegations on one ticket. On top of that, `UsageLimits` caps a ticket's
whole chain at 60 model requests and 120 tool calls. The request a colleague receives starts with
who asked, the ticket, and the chain so far. Both the request and the reply are logged.

### 6.5 Prompts

`shared.md` is appended to every agent's own file: the seven shop rules in the agents' terms, how
to work (read the ticket first, write notes the human can follow, one complete delegation rather
than several, read a refusal and do not repeat the call, finish with a short report), and who the
colleagues are. `boss.md` has the two jobs (triage; work one ticket) with the typical routes per
ticket type and the three possible calls: resolve, leave waiting for the human, or report blocked.
Each specialist file names its tools and what its report must contain.

### 6.6 The run loop

`triage()` runs the Boss with `TriagePlan` as structured output; the Boss sets priorities and
assignments with the tools and returns the plan. `work_ticket(id)` runs the Boss with
`BossDecision` as structured output. `run_board()` triages, then works every unresolved ticket in
board order. Usage-limit and model-behaviour errors become a `blocked` decision with the reason,
never a crash. The human's `approve_and_pay` is the only code path that calls the hidden tools.

### 6.7 Decisions made at this step

- **Same tools for everyone, three hidden**, instead of per-role lists (see 6.3).
- **Delegation is a tool, not a graph.** The model decides whom to ask and when; the Team only
  enforces the guards. That is what "full connectivity" asks for, and the live runs show the Boss
  choosing sensible routes without a hard-coded workflow.
- **Every tool call is logged to `ticket_events`** (kind `tool`, with the arguments and a preview
  of the result), not only delegations, so the dashboard can show the team working. A 27th MCP
  tool, `log_event`, was added for this and hidden from the agents.
- **Parallel delegations happen.** On ticket 103 the Boss asked Inventory and Accounting in the
  same turn and PydanticAI ran them concurrently; the server serialises the writes, and the log
  shows both. MCP tool calls themselves are marked sequential.
- **A refusal is data.** See 6.3.

### 6.8 Verified (2026-11-03)

**Offline** (`pytest`, 38 passed: 32 server tests including `log_event`, 7 back end tests on
scripted models and a stdio copy of the server, no gateway calls): every agent's prompt loads with
the shared rules; the agents' toolset is the server's minus exactly the three hidden tools; the
guards stop self-calls, cycles, depth 4, and an exhausted budget, and one budget is shared down the
chain; a scripted Boss delegating to a scripted Inventory round-trips, with `delegate` and
`delegate_reply` rows on ticket 101 carrying agent, target, depth, and chain; a tool call is logged
with the calling agent's name and the result; a refused purchase order reaches the model as the
server's sentence and leaves no order; the human path refuses `pay` before approval and pays after
it (checking $2,560).

**Live, ticket 102 only** (`output/agent_run_ticket102.txt`, 32 s): the Boss read the ticket,
assigned Facilities, asked Facilities (confirmed the lease, wrote a note) and then Accounting
(checked cash, approvals, payments; requested approval 1 for the $2,400 rent with "$1,000 would
remain"; wrote a note), wrote its own note, and returned `waiting_approval` with approval 1.

**Live, the board from a reset** (`output/agent_run_board.txt`, 1 min 57 s). Triage read the three
tickets and ranked 102 (rent, due in two days) first, 101 (tee order, empty shelf, overdue invoice)
second, 103 (discount) third, assigning Facilities, Inventory, Inventory. Then:

| Ticket | Delegations | What happened | Outcome |
|---|---|---|---|
| 102 rent | facilities, accounting | lease confirmed; approval 1, rent $2,400 | waiting_approval |
| 101 tee order | inventory, accounting, customer_service | S at 0, short 1; Bulldog Print Co 5 days → 2026-09-05 but blocked by invoice 501; approval 2, invoice $840; draft 1 to Tauhid Zaman with the date marked pending | waiting_approval |
| 103 discount | inventory, accounting, customer_service | 8 of 20 on hand, short 12; no order drafted (vendor blocked); 10% discount worked out ($52.20, $30.20 margin per unit); approval 3, price override; draft 2 to the Yale AI Club | waiting_approval |

End state: 119 timeline rows (67 tool calls, 8 delegations and 8 replies, 12 notes, 3 approval
requests, 2 drafts, 3 decisions); by agent, boss 49, accounting 35, inventory 18, customer service
12, facilities 4. No payment, no purchase order, checking still $3,400. Accounting's note on 103
reads rent plus the invoice would leave $160, which is the cash squeeze from 1.7 found by the team
itself. The original database still has its first hash.

What this step did not do: the API, the approve → pay → re-work round trip through it, and the
dashboard. Those are build steps 8 and 9.

## 7. Agents, tools, and tables (2026-11-03)

Shop facts come from the MCP server over `data/campus_customs_new.db` and from nowhere else: the
back end has no shop-data code of its own, and every read and write the agents make, every event
the Team logs, and every human decision and payment goes through an MCP tool. The one admin action
outside MCP is the reset script (rule 8), which agents cannot reach.

### 7.1 Each agent and what it leans on

Every agent sees the same 27 tools (the server's 30 minus `pay`, `decide_approval`, and
`log_event`) plus `ask_colleague`. The prompts steer each one to its part of the shop:

| Agent | Role | Tools it leans on | Tables those touch |
|---|---|---|---|
| boss | reads each ticket, decides who works it, makes the final call | get_today, list_tickets, get_ticket, set_ticket_priority, assign_ticket, add_ticket_note, resolve_ticket, ask_colleague | tickets, ticket_events (reads the linked invoices, vendors, leases, inventory, pricing, desk) |
| inventory | stock by SKU and size, shortfalls, vendor and delivery date, drafts purchase orders, opens restock tickets | get_ticket, get_today, get_stock, list_stock, get_pricing, list_vendors, get_vendor, list_purchase_orders, create_purchase_order, open_ticket, add_ticket_note | inventory, pricing, vendors, invoices (read), desk; writes purchase_orders, tickets, ticket_events |
| accounting | cash, invoices, margins; requests the human's approval for payments | get_cash, list_invoices, get_invoice, list_payments, get_pricing, list_approvals, list_purchase_orders, request_approval, add_ticket_note | cash_accounts, invoices, payments, pricing, purchase_orders; writes approvals, tickets (status), ticket_events |
| facilities | the lease, the rent, the landlord | get_lease, list_leases, get_today, add_ticket_note, ask_colleague (accounting for the rent approval) | leases, desk; writes ticket_events |
| customer_service | drafts messages to customers | get_ticket, draft_customer_message, list_drafts, add_ticket_note | tickets; writes drafts, ticket_events |
| the human (console now, dashboard next) | approves or rejects, and pays | decide_approval, pay | approvals, payments, cash_accounts, invoices / leases / purchase_orders, tickets, ticket_events |
| the Team (back end) | audit trail on the board | log_event | ticket_events |

### 7.2 Each MCP tool and the tables it uses

| Tool | Reads | Writes | Who |
|---|---|---|---|
| get_today | desk | | all |
| list_tickets | tickets | | boss |
| get_ticket | tickets, invoices, vendors, leases, inventory, pricing, desk | | all |
| list_ticket_events | ticket_events | | dashboard, boss |
| open_ticket | inventory, leases, invoices, desk | tickets, ticket_events | inventory (restocks), any agent |
| assign_ticket | tickets | tickets, ticket_events | boss |
| set_ticket_priority | tickets | tickets, ticket_events | boss |
| set_ticket_status | tickets | tickets, ticket_events | boss |
| add_ticket_note | tickets | ticket_events | all |
| resolve_ticket | tickets | tickets, ticket_events | boss |
| get_stock, list_stock | inventory, pricing | | inventory |
| get_pricing | pricing | | inventory, accounting |
| list_vendors, get_vendor | vendors, invoices | | inventory |
| list_invoices, get_invoice | invoices, vendors, desk | | accounting |
| get_lease, list_leases | leases, desk | | facilities |
| get_cash | cash_accounts | | accounting, inventory |
| list_payments | payments | | accounting |
| list_purchase_orders | purchase_orders, vendors | | inventory, accounting |
| create_purchase_order | vendors, invoices, inventory, pricing, desk | purchase_orders, ticket_events | inventory |
| list_approvals | approvals | | accounting, boss |
| request_approval | invoices / leases / purchase_orders (the amount), tickets | approvals, tickets, purchase_orders, ticket_events | accounting |
| decide_approval | approvals | approvals, purchase_orders, tickets, ticket_events | human only |
| pay | approvals, cash_accounts, invoices / leases / purchase_orders, vendors, desk | payments, cash_accounts, invoices or leases or purchase_orders, approvals, ticket_events | human only |
| draft_customer_message | tickets | drafts, ticket_events | customer_service |
| list_drafts | drafts | | customer_service, dashboard |
| log_event | tickets | ticket_events | back end only |

Three tools were added at this step so an agent can look a record up without a ticket link:
`get_vendor`, `get_invoice`, `list_leases` (30 tools, section 5.3's modules unchanged).

### 7.3 The audit trail

`output/audit_trail.json` (JSON Lines, append-only, the Homework 4 shape) is written by
`backend/audit_trail.py` as the agents run: a `run_started` line when the Boss starts a ticket or
a colleague starts on a delegation (agent, ticket, chain, parent run, the prompt, the prompt files
in force); a `step` line the moment each model response arrives (what went in: the user prompt or
the previous step's tool results and retries; what came out: text, tool calls with arguments,
tokens, the model name the gateway reported); a `run_finished` line with the outcome, the output,
total usage, and duration; and `human` lines for approvals, rejections, payments, and resets.
Nested runs carry `parent_run_id`, so a ticket's whole chain can be reassembled. Nothing in the
code base truncates the file; `python -m backend.audit_trail --tail 5` reads it.

### 7.4 Verified (2026-11-03)

40 tests pass: 33 server tests (the three new read tools, the 30-tool list over the in-memory
client) and 7 back end tests, one of which runs a scripted Boss → Facilities ticket through
`work_ticket` against a temporary trail and checks every line in order (run_started, step,
run_started with the parent run id, step, step, run_finished, step, run_finished, human), the
chain and depth on the nested run, a tool return in a step's request, usage on run_finished, and
that a line already in the file survives the run.

Live, on the board the earlier run left (`output/agent_run_rework102.txt`): the human approved and
paid approval 1 (rent $2,400, checking $3,400 → $1,000, lease 1 next due 2026-10-02); then the Boss
re-worked ticket 102, asked Facilities, Facilities asked Accounting, Accounting found approval 1
executed and the payment on record and requested nothing new, and the Boss resolved the ticket.
`output/audit_trail.json` then held 23 records: 2 human (decide, pay), 3 run_started / 3
run_finished linked by `parent_run_id` into boss → facilities → accounting (depth 0, 1, 2), 15
steps carrying 16 tool calls, every step naming `gpt-6-luna-2026-09-22`, and per-run usage
(boss 5 steps, 52,003 in / 1,093 out tokens, 32.8 s; facilities 6 steps; accounting 4 steps).

## 8. Safety: the guardrails a real business wants when agents touch real customers and real money

**Already in this build.**

- Money moves only through `pay`, which only the human's path can call, only against an approval
  a named human made, only when the balance covers it; the amount is read from the record, never
  typed by an agent; one approval per item; the vendor is re-checked at payment time.
- No tool sends anything. Customer messages are drafts a human reads first.
- Agents cannot approve, pay, reset, or delete. Their toolset is the server's minus the human-only
  tools, enforced in code, not in the prompt.
- Facts come from one database through one server; every tool refuses bad input with a sentence
  and never invents a value. The original data is never opened; a run starts from a reset copy.
- Every delegation and tool call goes to the ticket timeline, and every model step to an
  append-only audit trail, so what an agent did and why can be reconstructed after the fact.
- Runs are bounded: delegation depth and count per ticket, model requests and tool calls per
  ticket, timeouts on the gateway. A blocked ticket is reported, not forced through.

**What a real business adds before real customers and real money.**

- Least privilege per role (Accounting sees money tools, Customer Service does not), and a
  separate credential per agent so the audit trail names the actor at the database too.
- Spend controls: per-period limits, a second approver above a threshold, and payee verification
  against the vendor master before a payment can be requested.
- Idempotency keys on every write so a retried call cannot pay or order twice.
- Prompt-injection defences: ticket text and customer messages are untrusted input; the agents
  must not take instructions from them, and high-risk actions need confirmation outside the model.
- Customer data handling: minimise what the prompts and the audit trail hold, retention limits,
  and a review step before any draft reaches a customer.
- Operations: a kill switch, alerts on refusals and errors, budgets on model spend, replayable
  runs in a staging copy with synthetic data, and periodic review of the trail by someone who is
  not the agents' author.

## 9. Expected outcomes per ticket, written before the run (2026-11-03)

### 9.1 The desk page

`output/desk_tickets.html` is the written-down expectation for each open ticket, made before the
back end is wired to the API and before the full run, so the run can be judged against it rather
than the other way round. It is one self-contained HTML file (no libraries, no network, opens on a
double-click) with five tabs: Ticket 101, Ticket 102, Ticket 103, Cash, Reflection. The current tab
is kept in the URL hash (`#ticket-102` opens on that ticket), arrow keys move between tabs, and
printing lays all five out in order. Cash and Reflection hold a "Coming soon." note for later
problems. For the in-app preview, which cannot open `file://` paths, `.claude/launch.json` has a
`desk-page` entry: Python's `http.server` on port 8090 serving `output/`.

Every fact on the page was read through the MCP server after a reset (`get_ticket` 101, 102 and
103 with their links, `list_vendors`, `get_cash`, `get_pricing`); the routes follow the "typical
routes" in `backend/prompts/boss.md` and each specialist's remit. A strip above the tabs states the
shop date (2026-08-31), the cash ($3,400), the expected triage order (102, 101, 103) and the
two-pass rule: agents cannot approve or pay, so a ticket that needs money ends the first pass at
`waiting_approval`, the human decides on the dashboard, and the Boss re-works it to finish.

### 9.2 The expected routes

| Ticket | First call, and why | Delegations expected | Tools that decide it | End of pass 1 | After the human |
|---|---|---|---|---|---|
| 101 tee order (Tauhid Zaman, 1 × CC-TEE-WHITE S) | **Inventory.** S is at 0, so the order is a stock question before anything else; Inventory owns the shelf and the vendor match. | boss → inventory; inventory → accounting (or boss → accounting); boss → customer_service. Not Facilities. | `get_stock` (S 0; M 5, L 3, XL 2), `list_vendors`/`get_vendor` 1 (Bulldog, 5 days, `can_ship` false), `create_purchase_order` **refused** by invoice 501, `get_invoice` 501 ($840, 3 days overdue), `get_cash`, `request_approval` invoice 501, `draft_customer_message` to Tauhid Zaman | `waiting_approval`; approval $840 pending; one draft; cash $3,400 | invoice paid, cash −$840, vendor clear; a purchase order for the S tee dated 2026-09-05 (its payment is one more approval) or a resolution on the paid reprint; never a claim of shipment |
| 102 rent notice (Elm City Properties, lease 1) | **Facilities.** The lease and the landlord are its whole remit; it confirms the amount and date from the lease record, and its prompt has it ask Accounting for the approval. Ranked first on the board: due in 2 days. | boss → facilities; facilities → accounting. Not Inventory, not Customer Service (no goods; the landlord is not a customer). | `get_lease` 1 ($2,400, due 2026-09-02, 2 days), `get_cash` ($3,400), `list_payments` (none), `list_approvals` (none), `request_approval` rent lease 1 | `waiting_approval`; approval $2,400 pending; no draft, no order | payment $2,400, cash $1,000, lease `next_due` 2026-10-02; on the re-work Facilities sees the moved date, Accounting confirms the payment, the Boss resolves |
| 103 bulk discount (Yale AI Club, 20 × CC-HOOD-NAVY M) | **Inventory.** Eight mediums on hand, twelve short, through the same blocked vendor; the quantity-and-date answer shapes the offer Accounting prices. Accounting second, not first. Ranked last: no deadline. | boss → inventory; boss → accounting (or inventory → accounting); boss → customer_service. Not Facilities. | `get_stock` (M 8, short 12; L 14), `get_pricing` (cost $22, list $58, margin $36), `list_vendors`/`get_vendor` 1 (blocked), `get_cash` and `list_approvals` ($160 once rent and 501 are committed, so no purchase-order approval for a $264 reprint), `request_approval` price_override, `draft_customer_message` to the Yale AI Club | `waiting_approval`; approval price_override ($0) pending; one draft; stock unchanged | approved: resolved with the terms (8 now at the approved price, 12 later); rejected: back to `in_progress`, a list-price draft, then resolved or blocked; cash untouched |

### 9.3 Why the routes are not symmetric

Accounting appears on all three tickets because every ticket touches money, but it is never the
first call: it prices and requests against a fact another specialist has confirmed (a stock count,
a lease record). Facilities appears only on 102; Customer Service only where there is a customer to
write to (101 and 103); Inventory wherever there is a SKU (101 and 103) and never on the rent. The
deepest chain expected is two levels (boss → facilities → accounting, or boss → inventory →
accounting), inside the depth limit of three, and no ticket needs more than three delegations of
the twelve allowed. Tools that must not appear in any agent's run: `pay` and `decide_approval`
(hidden); `resolve_ticket` in the first pass of a ticket whose payment or override is still with
the human.

### 9.4 How the Actual sections will be filled

Each ticket tab ends with five empty slots: first call made, delegation chain seen, tools called,
end state, and match with expected. After the reset and a run per ticket they are filled from two
records: the ticket timeline (`list_ticket_events`: `delegate` and `delegate_reply` rows with the
chain, `tool` rows with arguments and a result preview, the `decision` row) and
`output/audit_trail.json` (`run_started` rows linked by `parent_run_id`, one `step` per model
response with the tool calls it made). The match slot states what differed and why; a difference
is not automatically a fault (Inventory asking Accounting directly instead of reporting back to the
Boss is within the design), but a wrong first call, a specialist on a ticket that does not need it,
or a tool that should not appear is.

### 9.5 Verified (2026-11-03)

- Opened through the `desk-page` server on port 8090 in the in-app browser. Each tab switches by
  click and by arrow keys; the hash follows; a deep link to `#ticket-103` opens that tab and keeps
  the tab strip in view; no console errors; no element wider than the viewport at 1024 px; light
  and dark colour schemes both render.
- The seed facts on the page match `get_ticket` 101, 102 and 103 called through the project
  connector in this session: tee S 0 (M 5, L 3, XL 2), cost $8 and list $28, invoice 501 $840
  open and 3 days overdue, Bulldog Print Co 5 days; lease 1 $2,400 due 2026-09-02 (2 days); hoodie
  M 8 (S 4, L 14, XL 6), cost $22 and list $58.

## 10. The API: `backend/main.py` (2026-11-03)

### 10.1 Layout and start

`backend/main.py` holds `create_app(team=None)`, which builds the FastAPI app, and the module-level
`app` uvicorn serves. Start it from `backend/` with the virtual environment active:

```
cd backend
uvicorn main:app --reload --port 8000
```

From the project root `.venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000` does
the same, and `backend` in `.claude/launch.json` starts it for the in-app preview. Interactive docs
at `/docs`. Run from `backend/`, uvicorn puts `backend/` on `sys.path` rather than the project
root, so the first lines of `main.py` add the root; the back end imports itself as `backend.*` and
the reset script as `mcp_server.reset` either way.

The API has no shop data of its own: every route reads and writes through the MCP tools on port
8100, the same tools the agents use (the reset is the one admin action outside MCP, as before). One
`Team` per process means one MCP connection, opened at startup. If the MCP server is down the API
still starts, prints the command to start the server, `/health` reports the error, and every other
route answers 503 until the server is reachable (the connection is retried on each request). The
request and response types (`TicketSummary`, `DecisionRequest`, `JobInfo`, `EventsPage`,
`CashView`) are in `backend/models.py` with the rest. CORS allows the dashboard's origin
(`localhost:5173`). The uvicorn console prints every run event as it happens, like the console
runner, so the window shows the team at work.

### 10.2 The routes, one line each

| Route | What it does |
|---|---|
| `GET /health` | The API, the model (`gpt-6-luna`), the MCP URL and whether it is connected, the shop's date, whether the team is busy and with what. |
| `GET /tickets` | The tickets on the board, each with its status and `open` (true unless resolved); `?status=` filters. |
| `GET /tickets/{id}` | One ticket with everything it links to (invoice, lease, stock, pricing) and the shop's date. |
| `POST /tickets/{id}/run` | The Boss works that ticket: a background job, answered 202 with the job; `?wait=true` waits and returns the Boss's decision in the job. Re-running a ticket (after an approval) is allowed. |
| `POST /board/run` | Triage, then every unresolved ticket in priority order; same job mechanics. |
| `GET /runs`, `GET /runs/{job_id}` | The background jobs, newest first, with status, result (the decision) or error. |
| `GET /events` | The timeline for the board to refresh from: runs, delegations and replies (what each agent said), every tool call with its arguments and a result preview, notes, approvals, payments, decisions. `?since=` returns only newer events and `last_id` is what to send next time; `?ticket_id=` for one ticket; without `since`, the most recent `limit`. |
| `GET /cash` | The checking balance from `cash_accounts`, with every account and the total. |
| `GET /approvals` | The human's queue; `?status=pending` for what is waiting. |
| `POST /approvals/{id}/approve` | The human approves: records the decision, then pays. This is the only route that changes cash. A price override carries no payment. A payment the rules refuse (not enough cash, vendor still owed) comes back in `refused` with the approval left approved for a retry. By default the Boss then re-works the ticket in the background (`rework: false` to skip). |
| `POST /approvals/{id}/reject` | The human rejects: no money moves, a purchase order returns to draft, the ticket to in_progress; the Boss re-works it by default. |
| `GET /drafts` | Customer messages waiting on the board; nothing is sent. |
| `POST /reset` | Copies the original database over the working copy for a fresh run (shop rule 8), records the reset on the audit trail, clears the job list. Refused while the team is working. |

### 10.3 Decisions made at this step

- **Runs are background jobs.** The Boss takes from forty seconds to a few minutes on a ticket,
  which is too long for a dashboard click to hang on. `POST .../run` returns the job at once, the
  board polls `/events?since=` and `/runs/{id}`; `?wait=true` exists for scripts and tests. One
  job at a time: a second run, or a reset, while the team is working is refused with 409, so two
  runs can never compete for the same cash or write over each other's ticket.
- **Approve is one click.** The human's approve records the decision and pays in one route,
  because that is what the button means; the two halves stay separate tools on the server, and a
  refused payment is reported in the response rather than hidden, with the approval left approved
  so the payment can be retried once cash allows. Then the Boss re-works the ticket, which is how
  a ticket goes from `waiting_approval` to `resolved` without anyone re-typing anything.
- **The feed is the timeline, not memory.** `/events` reads `ticket_events` through the MCP
  server rather than the Team's in-memory list, so it survives a restart, covers the console
  runner's runs too, and carries the notes and replies in full.
- **Tests.** Six offline tests in `backend/tests/test_api.py` (FastAPI's TestClient over a Team on
  stdio with PydanticAI's TestModel): the board and `open`; one ticket with links and a 404; a run
  as a job with `wait=true`, the timeline it writes, `since`/`last_id` polling; the cash view;
  approve pays and moves the lease date, a second approve is 409, reject, approve after reject is
  409, a payment the cash cannot cover comes back as `refused`; the busy guard; the reset.

### 10.4 Verified (2026-11-03)

- `python -m pytest`: 47 passed (33 server, 8 team, 6 API).
- Live, through the `backend` launch entry on port 8000 with the MCP server on 8100. Every call and
  its full response is appended to `output/api_live_check.jsonl`:
  - `GET /health`: ok, MCP connected, model `gpt-6-luna`, shop date 2026-08-31, not busy.
  - `POST /reset`: tickets 3, payments 0, approvals 0, purchase orders 0, drafts 0, checking $3,400.
  - `GET /tickets`: 101, 102, 103 all `open`; `GET /cash`: checking $3,400.
  - `POST /tickets/102/run?wait=true`: 202 after 40 s; outcome `waiting_approval`; delegated to
    facilities, then accounting. `GET /events?ticket_id=102`: 30 events (17 tool calls:
    `get_ticket` ×3, `assign_ticket`, `get_lease`, `get_cash` ×2, `list_payments`,
    `list_approvals`, `list_invoices`, `list_purchase_orders`, `request_approval` ×2,
    `add_ticket_note` ×4; 2 delegations with their replies; 4 notes; the decision).
    `GET /approvals`: 1 invoice 501 $840 pending (requested by accounting), 2 rent $2,400 pending
    (requested by boss). Cash unchanged; 102 `waiting_approval`, 101 and 103 still `open`.
  - Behaviour note for the desk page's Actual section: the first call went to Facilities as
    expected, but Accounting, asked for the rent approval, ranked the overdue invoice first and
    requested *that* (on ticket 102) instead, and the Boss then requested the rent itself. Within
    the rules (both approvals are valid, nothing was paid), but a deviation from the expected
    route worth a prompt adjustment before the full run.
  - `POST /approvals/2/approve` (Store Manager): approval `executed`; payment 1 of $2,400 on
    2026-08-31; checking $1,000; lease `next_due` 2026-10-02; re-work job started in the
    background.
  - The re-work job, polled through `GET /runs/{id}` every ten seconds the way the dashboard
    will: done after 30 s. The Boss asked Facilities, then Accounting; both confirmed the payment
    and no new approval was requested; the decision said `resolved`. But `GET /tickets/102` still
    said `waiting_approval` with no resolution: the Boss had never called `resolve_ticket`. The
    API reported both faithfully; the Boss had claimed work the tools did not show. The fix is in
    10.5.
  - After the fix, `POST /tickets/102/run?wait=true` once more: 202 after 33 s. The Boss claimed
    `resolved` again, the validator sent it back (a `retry` event on the timeline), it called
    `resolve_ticket`, and the decision was accepted. `GET /tickets/102`: `resolved`, with a
    resolution stating the $2,400 payment on 2026-08-31 and the next due date 2026-10-02. Board:
    101 open, 102 resolved, 103 open; checking $1,000; approval 1 (invoice 501) still pending.

### 10.5 What the live check forced: the Boss's decision must match the ticket

The Boss returning "resolved" without having resolved the ticket is shop rule 1 broken at the
last step: a claim the tools do not show. Prompting against it was already there ("never claim a
payment, a shipment, or a sent email that the tools do not show"); the live check showed that is
not enough for the final call, so it is now enforced in code.

`decision_matches_the_ticket` in `backend/agents/boss.py` is an output validator on the Boss's
ticket agent. When the Boss returns its decision, the validator reads the ticket through
`get_ticket` and compares: a decision of `resolved` while the ticket is not resolved, or of
`waiting_approval` while the ticket is not waiting, writes a `retry` event to the timeline and
raises `ModelRetry` with a sentence that tells the Boss what to do (call `resolve_ticket` with the
facts and figures, or have the approval requested, or return the outcome that matches the ticket).
The agent allows two retries; after that the run ends in `UnexpectedModelBehavior`, which
`work_ticket` turns into a `blocked` decision, so a Boss that will not do the work can never show
a resolved ticket. `blocked` itself is accepted without a status check: it is the outcome for
"the shop cannot do this", and nothing on the ticket has to change for it to be true.

PydanticAI ties output validators to the agent and refuses a per-run `output_type` on an agent
that has one, and until now the Team gave the single Boss agent a `TriagePlan` or a
`BossDecision` per run. So the Boss is now two `Agent` objects on the same prompt and tools: the
ticket agent (`BossDecision`, with the validator) in `Team.agents`, and `Team.triage_agent`
(`TriagePlan`). Every chain starts with the Boss and the delegation guard refuses a colleague who
is already in the chain, so the Boss never receives a delegation and never needs the plain-text
output the specialists have. `Team.run_agent` takes an optional agent object for this.

Tests: `test_the_boss_cannot_claim_resolved_until_resolve_ticket_was_called` scripts the false
claim, the retry, the `resolve_ticket` call and the accepted second claim, and checks the ticket's
status and resolution and the order of events (retry, then the tool call, then the decision). Two
older tests that had a scripted Boss answer in plain text, or claim `waiting_approval` without an
approval, now return `blocked`.

## 11. The dashboard: `frontend/` (2026-11-03)

### 11.1 What it is and where things are

React 19, Vite 8, TypeScript, no UI library, the same package versions the Homework 4 storefront
installed cleanly on this machine. `npm run dev` serves it on port 5173 (`strictPort`, so the
origin the API allows never drifts; file watching by polling because the folder is on OneDrive).
`frontend` in `.claude/launch.json` starts it for the in-app preview. The page talks to
`http://localhost:8000` (`VITE_API_URL` overrides; `frontend/.env.example`), and `backend/main.py`
allows that origin through CORS: the two `localhost:5173` origins explicitly, plus a regex for any
other local port so a `vite preview` works too.

| File | What it holds |
|---|---|
| `src/api.ts` | The typed client over `fetch`: one function per route, errors carried as `ApiError` with the API's `detail`. |
| `src/types.ts` | The shapes the API returns (`Ticket`, `ShopEvent`, `Approval`, `Cash`, `Job`, `BossDecision`, `Health`, `Draft`, …). |
| `src/agents.ts` | The roster (name, initial, role, colour) for the five agents plus "You" and "Shop"; the tool-to-plain-words dictionary; ticket type, status and approval labels. |
| `src/format.ts`, `src/hooks.ts` | Money and time formatting; `useInterval`, the cash tween, `usePrevious`. |
| `src/App.tsx` | State, polling, and the human's actions (run, approve, reject, reset); passes everything down. |
| `src/components/` | `TopBar` (brand, date, cash, team light, approver, two-click reset), `TicketBoard`, `LiveFloor` (team strip, feed, typing dots, jump pill), `ApprovalsPanel`, `AgentSummary`, `DraftsPanel`, `Toasts`, `Expandable`. |
| `src/index.css` | The HW4 visual system applied to a desk: variables, panels, board, floor, feed voices, approvals, toasts, responsive breakpoints, reduced motion. |

The brief's list, and where each item lives: all three tickets on the board; pick one and start
the team (the selected card's button posts `/tickets/{id}/run`); each agent and what it is saying
and doing while the ticket runs (the team strip and the feed, from `/events`); the ticket marked
resolved when the run finishes (the card's chip, stamp and resolution, from `/tickets` after the
job ends); a short summary of what each agent did ("Who did what", built from the same events);
approve and pay or purchase when asked ("Needs you", posting `/approvals/{id}/approve`); the
checking balance that drops after an approved payment (the top bar, from `/cash`, animated).
`output/design.md` is the design record: the look, the layout, how the agents read differently,
how resolved tickets and cash show up, and why.

### 11.2 How it stays live

Polling, not a stream: the API already had `since`/`last_id` on `/events`, and 1.5 seconds between
pulls is live enough to watch a tool call land. While a run is on the page pulls the timeline every
1.5 s and the board, cash, approvals, drafts and health every 2.5 s; idle, every 5 s and 8 s. A run
the page started is followed through `/runs/{id}` until it ends; a run started elsewhere (the
re-work the approve route starts, or the console runner) is adopted from `/health`'s `busy` field,
so the board shows it the same way. After an approval the new balance from the response is applied
at once and the counter glides down; the next poll confirms it.

### 11.3 Decisions made at this step

- **One colour per agent, everywhere.** The assignee on the card, the strip, the feed, the summary
  all use the same round serif initial in the same hue, so the eye learns who is who once.
- **Plain words with the receipt attached.** Every tool call reads as a verb a manager would say
  ("counted the shelf") with the real call in small monospace and the raw result one click down;
  a refused call turns red. The feed is readable and auditable at the same time.
- **Inline confirmations, no browser dialogs.** Reset is two clicks (arm, then a red "Yes, reset to
  seed" beside "Keep", disarming after fifteen seconds); reject opens a note field inside the card.
  This looks like the rest of the page, and it is also what made the automated check possible.
- **Resolved is stamped; cash is felt.** A rotated green stamp on the card (with a slam-in when it
  happens while you watch), the resolution text under it, the run button relabelled "Run the team
  again"; the balance counts down, turns amber while falling, and floats the difference for three
  seconds. Both are described, with the reasons, in `output/design.md`.
- **Nothing is computed in the browser.** Counts and balances are the server's; the page formats.
  No send button on a draft, no pay without an approval, no editing of shop facts.

### 11.4 Two fixes the first dashboard loop forced

- **The re-work after a decision now knows what was decided.** The first full loop through the
  dashboard (reset, run 102, approve the rent) ended with the Boss's re-work `blocked`: the team
  re-read "rent due in 2 days", saw $1,000 in checking against a $2,400 rent, and declared the
  shop short, even though it had just confirmed the payment. The same re-work had ended `resolved`
  through the API an hour earlier: model variance on a prompt that said only "work ticket 102".
  `Team.work_ticket` now takes a `context`, and the approve and reject routes compose it:
  "Approval 1 (rent for lease 1, $2,400.00) was approved by Store Manager and paid: payment 1 of
  $2,400.00; checking is now $1,000.00." The Boss's prompt appends it with "check it with the
  tools and finish the ticket; do not request the same money again", and the `run` event on the
  timeline carries it, so the human can see what the re-work was told.
- **Two prompt lines about money already out.** `boss.md`: if the money the ticket needed has
  already gone out (an executed approval, a payment row, a lease date that moved, an invoice marked
  paid), the ticket is done; a ticket's wording was written when it was opened; judge by the
  records now; never request the same payment twice. `accounting.md`: an executed approval with a
  matching payment means paid; report it and request nothing; judge by the lease or invoice record
  and the payments as they are now.

### 11.5 Verified (2026-11-03)

- `npm run build` (TypeScript project build plus Vite) passes; `python -m pytest`: 47 passed
  after the re-work change (33 server, 8 team, 6 API).
- Live, in the in-app browser at 1440 × 900 with the MCP server on 8100 and the API on 8000, the
  final code, from a reset done on the page:
  - **Reset:** two clicks; the toast "Shop reset to the seed"; checking $3,400; all three tickets
    `Open`; the floor empty; the approval queue empty.
  - **Run:** ticket 102 selected, "Run the team". The card turned amber with "Working…" and "Team
    is working…"; the top bar read "Team working on ticket 102"; the strip showed Boss at full
    strength and Facilities lifted with "read the ticket"; the feed showed the Boss reading the
    ticket, assigning it, asking Facilities (chain Boss → Fac), Facilities reading the ticket,
    then typing dots; "Who did what" filled in as it went. The run ended inside 48 s: chip "Needs
    approval", the Boss's call card "waiting approval", 24 events, and "Needs you" showing
    "Rent · lease 1 $2,400.00" with the agent's rationale and "Approve & pay $2,400".
  - **Approve:** one click. Toast "Paid $2,400.00 · Checking is now $1,000.00. The Boss is
    re-working ticket 102."; the counter went from $3,400 to $1,000 with "−$2,400.00" floating
    beside it; "approved" and "paid" receipt lines from "You" in the feed; the queue emptied and
    "Decided (1)" appeared; the top bar read "Team working on ticket 102" again, and the run line
    on the timeline carried the context sentence.
  - **Re-work:** done inside 45 s with no retry. Card chip `Resolved`, the stamp on the card, the
    resolution under it ("Rent for lease 1 … approved by Store Manager under approval 1 and paid
    as payment 1 on 2026-08-31. Checking is now $1,000.00 …"), the Boss's call in green, the floor
    header "Resolved · 19 tool calls · 2 delegations", "Who did what": Boss 9 tool calls, asked
    Facilities and Accounting, 2 notes; Facilities 3 tool calls, 1 note; Accounting 7 tool calls,
    1 note; You.
  - No console errors from the page itself; the only errors logged were connection-refused lines
    during the minute the API was stopped for its restart, after which the page recovered by
    itself, as designed.
- Screenshots of the five moments are in `output/screens/` and listed in `output/design.md`.
- Before the fix in 11.4 the same loop ended `blocked` (recorded there); the dashboard showed that
  truthfully too: a red "blocked" call card and the card still at "Needs approval".

## 12. The full run (2026-11-03)

### 12.1 Setup

Reset from the dashboard (two clicks): the toast "Shop reset to the seed", checking **$3,400**, all
three tickets open, the timeline and the approval queue empty. The audit trail held 163 records
before the run. Then one press of the new "Run the board" button (the Boss triages, then works every
open ticket, most urgent first; the page follows the Boss from ticket to ticket), followed by the
approvals on the page one at a time, each starting the Boss's re-work of that ticket, and two
manual re-runs after the prompt clarification in 12.4. Every step was done on the dashboard; the
back end appended to `output/audit_trail.json` as it went.

### 12.2 Triage

Priority 1 → 102 to Facilities, 2 → 101 to Inventory, 3 → 103 to Inventory: the order and the
assignments the desk page expected (9.2). The board re-sorted itself by priority as the assignments
landed.

### 12.3 Each ticket's path

| Ticket | Pass 1 (the board run) | The human | Later passes | Final |
|---|---|---|---|---|
| 102 rent notice | boss → facilities (confirmed lease 1, $2,400 due 2026-09-02), boss → accounting (approval 1, rent, $2,400); 11 tool calls; `waiting_approval` | approved and paid approval 1: payment 1 $2,400, checking $1,000, lease `next_due` 2026-10-02 | pass 2: no delegation; the Boss read the approval, the payment and the lease and resolved (6 tool calls) | **resolved**; cash −$2,400 |
| 101 tee order | boss → inventory (S 0, short 1, Bulldog 5 days, `can_ship` false, no order attempted), boss → accounting (approval 2, invoice 501, $840), boss → customer_service (draft 1); 17 tool calls; `waiting_approval` | paid approval 2: payment 2 $840, checking $160 | pass 2: boss → inventory drafted PO 1 (1 × CC-TEE-WHITE S, $8, expected 2026-09-05) and requested approval 4; `waiting_approval` (21). The human paid approval 4: payment 3 $8, checking $152, PO 1 `ordered`. Pass 3: boss → inventory; **blocked**, "await receipt, then fulfil" (24). After the prompt line in 12.4, pass 4: boss → inventory, inventory → accounting, boss → customer_service (draft 3); resolved (20) | **resolved** on PO 1, 2026-09-05, draft 3; cash −$848 |
| 103 bulk discount | boss → inventory (8 on hand, 12 short), inventory → accounting (asked for the invoice to be paid; Accounting declined to duplicate approval 2), boss → accounting (10% → $52.20, $30.20 margin; $160 left after rent and invoice, so no restock), boss → customer_service (draft 2); the Boss itself requested approval 3 (price override, $0); 41 tool calls; `waiting_approval` | approved approval 3; no payment | pass 2: boss → inventory; **blocked**, $264 against $152 (23). After the prompt line, pass 3: boss → inventory, boss → accounting, boss → customer_service (draft 4); resolved (27) | **resolved**: 8 now at $52.20, 12 when cash allows; cash $0 |

### 12.4 One prompt clarification the run forced

Twice the Boss declared a ticket `blocked` that the human would call handled: the tee on a paid
order with a date and a dated draft to the customer, and the hoodie order with an approved price,
eight on the shelf and twelve the shop cannot fund this period. Both are definitions of "done" the
prompt had not given: a customer order the shop can never fulfil inside a run (there is no
delivery in a run), and a discount ticket whose quantity the shop cannot afford. `boss.md` now says
that a customer order is done when the item is on the shelf or on a purchase order the human has
paid, with an expected date and a draft that tells the customer, and that an override ticket is
done once the human has decided and the customer has a draft with the decision and what can be
supplied now; the unfunded quantity goes in the resolution as the follow-up. `blocked` is for a
ticket where nothing it asked for can be done. No code changed; the API was restarted to load the
prompts and the two tickets were re-run from their cards.

### 12.5 End state, against what 3.6 predicted

| | 3.6 predicted | Actual |
|---|---|---|
| Payments | two | **three**: the two predicted plus the $8 tee order 3.6 had left open |
| Checking | $160 | **$152.00**, in `cash_accounts` (read directly), from `GET /cash`, and by arithmetic |
| Invoice 501 | paid | paid |
| Lease 1 `next_due` | 2026-10-02 | 2026-10-02 |
| Tickets | three resolved | three resolved |
| Drafts | at least two | four: 1 and 3 to Tauhid Zaman, 2 and 4 to the Yale AI Club; none sent |
| Approvals | every one executed or rejected | 1, 2 and 4 executed; 3 approved (a price override carries no payment, so there is nothing to execute) |
| Purchase orders | | PO 1, 1 × CC-TEE-WHITE S, $8, `ordered`, expected 2026-09-05 |
| Stock | | unchanged: S 0 until the delivery, M 8; the mug still at 0 and no restock ticket opened (3.6's initiative test was not taken) |
| Original database | hash unchanged | SHA-256 `23686a90…f360a`, unchanged |
| Records | | 314 timeline events; audit trail 163 → 374 records, appended, none rewritten; decision-validator retries 0; refused tool calls 0 |

### 12.6 Expected against actual, in short

- **Triage, first calls, and who stayed out: exact** on all three tickets. Facilities touched
  only 102; Inventory and Customer Service never touched 102.
- **Delegations:** 2, 8 and 8 against 2, 3 and 3 expected. The extra ones are the later passes;
  no single pass used more than four, and the deepest chain was boss → inventory → accounting on
  101 and 103, as expected.
- **Tools:** every expected tool appeared. The two refusals the desk page expected did not
  happen because the agents checked first (`can_ship` false, $264 against $152), which is better
  than expected. The Boss requested the price override itself; Facilities read the lease through
  the ticket's link rather than `get_lease`.
- **After the first pass: exact** on all three (the three approvals, the two drafts, cash
  untouched).
- **Where the team needed help:** the two "blocked" calls in 12.4, fixed with prose, not code.

### 12.7 Where the record is

`output/resolved_tickets.json` (per ticket: final status, outcome, each agent's tool calls and
reports, delegation chains, approvals, payments, drafts, orders; the cash ledger; the end state),
`output/resolved_board.html` (double-click: the end state and the React board at each resolved
ticket, screenshots embedded), the Actual and Cash tabs of `output/desk_tickets.html`,
`output/screens/resolved-101.jpg`, `-102.jpg`, `-103.jpg`, `output/audit_trail.json`, and the
working copy `data/campus_customs_new.db` as the run left it.

## 13. Where everything is covered

The brief asks this document to cover the tables, the MCP tools, every agent, the API routes, the
dashboard, and all the safety rules. This is the index.

| Topic | Where |
|---|---|
| The data: every table, its columns and seed rows, the relationships, the three tickets, stock and pricing, vendors, money, the quirks | 1.2 to 1.9 |
| Schema additions on the working copy (`ticket_events`, `approvals`, `drafts`, `purchase_orders`, the ticket columns) | 3.3, 4.3, 5.2 |
| The ten shop rules, where each is enforced in code, and how each is tested | 2 |
| MCP tools: the ticket tools (4.4), the shop and money tools (5.3), every tool with what it reads, what it writes and which ticket it unlocks (5.6), every tool with the tables it uses and who calls it (7.2); the server's own reference is `mcp_server/README.md` | 4.4, 5.3, 5.6, 7.2 |
| The rules in code: `pay` as the only cash movement, the vendor block, no negative balance, the amount read from the record | 5.4 |
| The agents: the five roles, prompts, one toolset with three tools hidden, delegation with full connectivity and its guards, the run loop | 6.1 to 6.7 |
| Each agent and what it leans on; the audit trail's layout | 7.1, 7.3 |
| The expected route per ticket, written before the run, and why the routes are not symmetric | 9 (and `output/desk_tickets.html`) |
| The API: layout and start, every route in one line, decisions, the decision validator and the two Boss agents | 10.1 to 10.5 |
| The dashboard: files, how it stays live, decisions, the re-work context fix, what was verified; the design and why | 11 (and `output/design.md`, `output/screens/`) |
| Safety: the guardrails in this build and what a real business adds | 8, with the rules in 2, the enforcement in 5.4, the validator in 10.5, one job at a time and the busy guard in 10.3, the re-work context in 11.4 |
| The full run: starting balance, triage, each ticket's path, approvals and payments, the end state against 3.6, expected against actual | 12 (and `output/resolved_tickets.json`, `output/resolved_board.html`, the Actual and Cash tabs of `output/desk_tickets.html`) |
| Verification at each step | 4.7, 5.7, 5.9, 6.8, 7.4, 9.5, 10.4, 11.5, 12 |
| What the run taught us: the reflection | the Reflection tab of `output/desk_tickets.html` |
