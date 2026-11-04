# AI Prompts Log — Campus Customs Agentic Shop Team

**Course:** MGT 409 E1 — AI Foundations for Managers, Homework 5
**Assistant:** Claude (Fable 5.1) via Claude Code
**Started:** 2026-11-02

This file records every prompt given to the AI assistant while building this project, in order,
along with a short note on what the assistant did in response. It is updated after each working step.

---

## Project brief (as given to the assistant)

Set up an agentic team that runs the Campus Customs shop. Tickets land on a board (customer orders,
rent, unpaid bills, discount requests, whatever the shop has to handle) and the agents work them
while a human watches and approves.

Three pieces that talk to each other:

- **MCP server:** exposes the shop's data and actions as tools.
- **FastAPI back end:** hosts the multi-agent team.
- **React dashboard:** lets a human watch the agents work and approve requests.

The team has **full connectivity**: any agent may delegate a task to any other agent for help.

| Agent | Job |
|---|---|
| **Boss** | Reads each ticket, decides who should work on it, and makes the final call. |
| **Inventory** | Checks stock by SKU and size, spots shortfalls, and figures out which vendor can restock. |
| **Accounting** | Watches cash and invoices, checks margins, and prepares payments and purchase orders for human approval. |
| **Facilities** | Handles the shop space side (rent, leases, and so on). |
| **Customer Service** | Drafts messages for customers. |

Working style: one problem at a time, step by step, so the setup is understood as it is built.

---

## Shop rules (set 2026-11-02)

1. **Working copy of the data.** The agents update the database as tickets get resolved. They read
   and write `data/campus_customs_new.db`; the MCP server and the back end point at that file.
   `data/campus_customs.db` is the untouched original and is used only to reset the working copy.
2. **The shop's clock.** `desk.date_today` is "today" for the shop. Anything overdue is measured
   against that date, not the real date.
3. **Lead times** come from the `vendors` table.
4. **Unpaid vendors do not ship.** A vendor will not ship new product while it still has an open,
   unpaid invoice.
5. **Human approval for every payment.** No payment goes out without a human approving it. When a
   payment is made, the relevant tables are updated (the payment is recorded, cash goes down, and
   the invoice or lease it settles is marked accordingly).
6. **No negative balances.** If there is not enough cash, the pay tool must refuse.
7. **Cash only goes out.** No revenue is modeled in this homework, so nothing comes in.
8. **Reset before a full run.** Before a full run to resolve the tickets, the working copy is reset
   to the original values.
9. **Drafts stay on the board.** No emails to customers or real vendors. Customer Service writes
   drafts; a human decides what to do with them.
10. **One model, one gateway.** Every AI call goes through Portkey with the user's `PORTKEY_API_KEY`,
    and every agent uses `gpt-6-luna`.

---

## Prompt log

### 1 — Session start
**Date:** 2026-11-02

> Good evening Claude

**Result:** Assistant confirmed it was working in the Homework 5 folder and asked what to work on.

---

### 2 — Pulling up the Homework 4 site
**Date:** 2026-11-02

> I am working on the campus customs website again. are you able to pull up the work we did in homework 4 and see the website and current status?

**Result:**
- Found the Homework 4 project in the sibling folder `Homework - 4` (React + Vite + TypeScript front
  end, FastAPI back end with two PydanticAI agents, SQLite data). Git history: three commits, clean
  tree, pushed to the public repository <https://github.com/AMR6958-coder/campus-customs-hw4>,
  submitted 2026-10-14.
- Added `.claude/launch.json` to the Homework 5 folder with two entries, `hw4-backend` (uvicorn on
  port 8000) and `hw4-frontend` (Vite on port 5173), pointing at the Homework 4 folders so both
  servers can be started from here. Started both and opened the storefront in the browser pane.
- Verified: health endpoint finds the database, all 102 products and photos serve, the home page
  renders, and the chat assistant answers through the Portkey gateway (asked for hoodies, it
  returned 27 matches with 24 product cards). Database at its seeded state with four accounts.
- Found one bug: a question containing a dollar figure ("under $60") makes the price-grounding
  validator reject the reply, because the model echoes "$60" and it is not a catalogue price. After
  two retries the chat returns its "having trouble" fallback. Not fixed; noted for later.
- Noticed that the `data.zip` in the Homework 5 folder is a different database from the storefront
  one: a small back-office dataset (tickets, invoices, leases, payments, vendors), which pointed
  toward a different kind of assignment.

---

### 3 — The assignment, and reading the data
**Date:** 2026-11-02

> I'd like to set up an agentic team that runs the shop. They should be able to open tickets and land on a board – customer orders, rent, unpaid bills, discount requests, whatever the shop has to handle. I want to build three pieces that talk to eachother. I want an MPC server, a fastapi backend with a multi agent team and a react dashboard so a human can watch the agents work and approve requests.
> I want the agent team to have full connectivity meaning any agent may delegate tasks to any other agent for help. I want to build the following agents:
> - Boss – Reads each ticket, decides who should work on it and makes the final call.
> - Inventory – Checks stock SKU, and size, spots shortfalls and figures out which vendor can restock.
> - Accounting – Watches cash and invoices, checks margins, and prepares payments for purchase orders for human approval.
> - Facilities – Handles the shop space side (rent, leases, etc.)
> - Customer Service – Drafts messages for customers
>
> Now as all of our other work, I want to go step by step to make sure we do this right and I learn how to properly set this up.
> Before we do anything else, can you read the data zip file I put into homework 5 folder?

**Result:** Unzipped `data.zip` in the project root, which produced `data/campus_customs.db`
(53 KB, dated 2026-10-03), and read the schema and every row. Findings:
- **Nine tables:** `tickets`, `inventory`, `pricing`, `vendors`, `invoices`, `leases`,
  `cash_accounts`, `payments`, `desk`. Foreign keys: `invoices.vendor_id -> vendors.id`,
  `tickets.invoice_id -> invoices.id`, `tickets.lease_id -> leases.id`. Integrity check passes.
- **The shop's clock:** `desk.date_today` is `2026-08-31`; `desk.notes` is empty.
- **Tickets (three, all open):**
  - 101 `customer_order`: Tauhid Zaman wants one `CC-TEE-WHITE` size S. Stock for that size is 0.
    Linked to invoice 501.
  - 102 `rent_notice`: Elm City Properties says rent on the Chapel Street shop is due in two days.
    Linked to lease 1.
  - 103 `price_override`: Yale AI Club wants 20 `CC-HOOD-NAVY` size M at a bulk discount. Only 8
    mediums in stock (32 hoodies across all sizes).
- **Inventory:** four SKUs by size and aisle. Hoodie `CC-HOOD-NAVY` S/M/L/XL = 4/8/14/6; tee
  `CC-TEE-WHITE` S/M/L/XL = 0/5/3/2; cap `CC-HAT-BLUE` one size = 40; mug `CC-MUG-CREST` one
  size = 0 (no ticket mentions it).
- **Pricing (unit cost / list price):** hoodie $22 / $58, tee $8 / $28, cap $6 / $22, mug
  $3.50 / $14.
- **Vendors:** Bulldog Print Co (apparel reprint, 5 days), Elm City Gifts (mugs and small goods,
  3 days), QuickShip CT (local courier, 1 day).
- **Money:** checking balance $3,400 as of 2026-08-31. Invoice 501 from Bulldog Print Co for
  $840, "Rush reprint CC-TEE-WHITE S", due 2026-08-28 (three days overdue by the shop's clock),
  status open. Lease 1: Chapel Street shop, landlord Elm City Properties, $2,400 a month, next due
  2026-09-02. Paying both leaves $160.
- **Payments:** empty. Columns `id, kind, ref_id, amount, account, paid_at, approved_by`;
  `approved_by` is NOT NULL, so no payment row can exist without a named approver.
- **What the data does not have:** no tables for ticket assignments, agent notes, drafted customer
  messages, purchase orders, or an audit log; no customer table (requesters are plain text); no
  users or chat tables. The board, the approval queue, and the agents' working notes will need new
  storage.
- Dates are ISO text; `tickets.created_at` carries a `-04:00` offset.

---

### 4 — Working copy, shop rules, model choice, and this log
**Date:** 2026-11-02

> before those openers, I'd like to confirm that i want these agents to update the database as tickets get resolved. please make a copy of the database file called data/campus_customs_new.db and point your mcp server and backend at that working copy. keep campus_customs.db untouched so you can reset it when you want to start resolving the tickets.
>
> Also, the rules for this shop are:
> - the field desk.date_today is today for the shop. use this date to determine what is over due.
> - Vendor lead times come from the "vendors" table
> - A vendor will not ship a new product while they still have an open unpaid invoice.
> - A human approval is required for any payments. If any payment is made, make sure to update the relevant table.
> - if there isn't enough cash, the pay tool must refuse - no negative balances.
> - cash only goes out in this homework. no revenue was modeled so no revenue comes in
> - before a full run to resolve the tickets, make sure to reset the database to the original values.
> - do not email customers or real vendors. drafts stay on the board.
>
> I wan to use my PORTKEY_API_Key for all AI calls. for this assignment, use only gpt-6-luna through portkey for every agent.
>
> As noted earlier, I want to work on this one problem at a time.
>
> No for the first step in this assignment lets create AI_prompts.md and save it to the homework 5 folder.

**Result:**
- Copied `data/campus_customs.db` to `data/campus_customs_new.db`. Both files have SHA-256
  `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`, which is the fingerprint of
  the untouched original; any later check that the original still has this hash confirms it was
  never written to.
- Recorded the ten shop rules above (the working-copy rule, the eight operating rules, and the
  gateway/model rule). The MCP server and back end do not exist yet; when they are built they will
  be pointed at the working copy, and a reset step will copy the original over it.
- Model note: the Homework 4 project used `gpt-5.6-luna` through Portkey; this project uses
  `gpt-6-luna` as instructed. The model name will be confirmed against the gateway when the first
  agent is wired up.
- Created this file, seeded with prompts 1–4. The assistant will append a new entry after each
  subsequent step.

---

### 5 — The build outline
**Date:** 2026-11-02

> Outline the build

**Result:** Checked two facts first: Homework 4 reaches Portkey with PydanticAI's `OpenAIChatModel`
plus an `OpenAIProvider` whose OpenAI client points at `PORTKEY_BASE_URL`, so that `get_model()`
pattern carries over unchanged; and PydanticAI already ships its MCP client module, but the MCP SDK
(`mcp` package) is not installed, so the new environment adds `pydantic-ai-slim[openai,mcp]` and
`mcp`. Then wrote the outline below. No code was created.

**Architecture: three processes, one working database**

```
React dashboard (Vite, :5173)         watch the board, approve payments, read drafts
        │  REST + server-sent events
        ▼
FastAPI back end (:8000)              five PydanticAI agents, run loop, approvals, audit trail
        │  MCP client (streamable HTTP)
        ▼
MCP server (FastMCP, :8100)           every shop tool; every shop rule enforced here
        │
        ▼
data/campus_customs_new.db            working copy; reset = copy data/campus_customs.db over it
```

Ports 8000 and 5173 are the ones Homework 4 uses, so its servers are stopped before Homework 5's
start.

**Piece 1: MCP server (`mcp_server/`).** Python, the official MCP SDK (FastMCP), served over
streamable HTTP on port 8100 so it is visibly its own process and can be opened in the MCP
Inspector. One setting names the database file, and it is the working copy (rule 1).
- *Read tools:* `get_today`, `list_tickets`, `get_ticket`, `get_stock`, `get_pricing`,
  `list_vendors`, `get_cash`, `list_invoices`, `get_lease`, `list_purchase_orders`,
  `list_approvals`, `list_drafts`.
- *Write tools, each carrying a rule:* `log_event` (activity and audit); `assign_ticket`;
  `draft_customer_message` (writes to a drafts table; there is no send tool, rule 9);
  `create_purchase_order` (refuses while the vendor has an open invoice, rule 4; expected date =
  shop today + the vendor's `lead_days`, rules 2 and 3); `request_payment` (creates a *pending*
  approval, never moves money, rule 5); `pay` (needs an approved approval and an approver name,
  refuses if balance < amount, rule 6; then inserts the payment, lowers cash, marks the invoice paid
  or advances the lease's next due date, rule 5; no tool ever adds cash, rule 7); `resolve_ticket`.
- *Schema additions*, created on startup if missing: `approvals`, `drafts`, `purchase_orders`,
  `ticket_events`; `tickets` gains `assigned_to`, `priority`, `resolution`.
- *Reset:* `reset_demo_data.py` copies the original over the working copy and re-applies the
  additions (rule 8). It is a script and an admin endpoint, not an agent tool.
- *Tests:* pytest, one test per rule (pay refuses at $3,401; a purchase order is refused while
  invoice 501 is open; "overdue" is judged against `desk.date_today`; a payment needs an approver).

**Piece 2: FastAPI back end (`backend/`).**
- *Model:* one `get_model()` returning `gpt-6-luna` through Portkey for every agent (rule 10);
  the first call confirms the gateway accepts that name.
- *MCP client:* PydanticAI's streamable-HTTP MCP toolset, filtered per agent so each role sees
  only its tools. Boss: tickets, assign, log, resolve. Inventory: stock, pricing, vendors, invoices
  (read), create purchase order. Accounting: cash, invoices, pricing, purchase orders, request
  payment. Facilities: lease, tickets. Customer Service: draft message plus read access to tickets,
  stock, and purchase orders. **No agent gets `pay`.** Only the approval endpoint calls it, after a
  human clicks approve.
- *Full connectivity:* one `ask_colleague(agent, request)` tool on all five agents, implemented
  as agent-as-tool (the called agent runs with the same ticket context and shared token budget).
  Guards: no self-calls, delegation depth of at most three, and a per-ticket budget so a loop
  cannot run away.
- *Prompts:* `backend/prompts/<agent>.md`, re-read on change as in Homework 4.
- *Run loop:* `POST /api/run`. Boss first triages every open ticket and orders them by urgency,
  then works them one at a time so each cash decision sees the previous one. Ticket statuses:
  open, in progress, waiting approval, resolved.
- *Approvals:* `GET /api/approvals`; `POST /api/approvals/{id}/approve` and `/reject` with the
  approver's name. Approve calls `pay` through MCP, then re-runs Boss on that ticket to finish it.
- *Live feed:* `GET /api/events/stream` (server-sent events from `ticket_events`) and
  `GET /api/board` for a full snapshot. `GET /api/health` reports the database file in use and the
  model name. `POST /api/admin/reset` refuses while a run is in progress.
- *Audit trail:* one JSON line per agent run, as in Homework 4.

**Piece 3: React dashboard (`frontend/`).** Vite + React + TypeScript, the Homework 4 stack.
Panels: the Board (columns by status; cards show assignee, priority, and the latest note), the
Activity feed (live), Approvals (approve or reject, typing your name), Drafts (customer messages,
read-only), a Shop snapshot (cash, inventory, invoices, lease), and a toolbar with Run agents and
Reset.

**The story the data tells, to test against.** Rent first: Facilities confirms the lease,
Accounting requests $2,400, a human approves, cash falls to $1,000. The tee order: Inventory finds
size S at zero and the reprint vendor blocked by its unpaid $840 invoice; Accounting requests that
payment; approval leaves $160; the reprint can now ship with an expected date of 2026-09-05;
Customer Service drafts a delay note. The hoodie bulk request: eight mediums on hand, twelve short;
a purchase order would cost $264 against $160 in cash, so Boss must choose between a partial offer
(eight now, priced above the $22 cost) and a decline, with the price override itself as an approval
item and a drafted reply. The mug at zero stock has no ticket, which tests whether Inventory opens
one on its own.

**Build order (one problem at a time)**
1. `AI_prompts.md` (done).
2. `output/harness.md`: the design record (data analysis, rules, this outline).
3. Skeleton: `mcp_server/`, `backend/`, `frontend/`; Python 3.14 virtual environment; pinned
   dependencies; `.env` and `.env.example`; `.gitignore`; three entries in `.claude/launch.json`;
   README stub.
4. MCP server, read tools only; verified with a small client script and the MCP Inspector.
5. MCP server, write tools with the rules, schema additions, reset script, and the rule tests.
6. Back end skeleton: model factory (confirm `gpt-6-luna`), MCP client, health, board, event stream.
7. Agents: Boss and Inventory with delegation first; then Accounting, Facilities, Customer Service;
   prompts and role-based tool access.
8. The approval flow end to end through the API (request, approve, pay, resolve).
9. The dashboard.
10. Full run: reset, run, approve, verify every table; an operational check with screenshots as in
    Homework 4; README; submission archive; public repository.

---

### 6 — End of session
**Date:** 2026-11-02

> lets pause here for now. I need sleep. will continue this in the morning.

**Result:** Session closed after the outline (step 1 of the build order done, step 2 next). The
Homework 4 servers that were started earlier in the evening for the status check were stopped.
State of the folder: `AI_prompts.md`, `.claude/launch.json` (Homework 4 entries only, to be
replaced by this project's three servers at the skeleton step), `data.zip`, and `data/` with the
untouched original and the working copy, still identical. No code yet.

**Resume here:** create `output/harness.md` with the data analysis (entry 3), the shop rules, and
the build outline (entry 5); then the skeleton.

---

### 7 — Morning restart and the harness notes
**Date:** 2026-11-03

> good morning claude i am back
>
> lets finish this up

**Result:**
- Checked the folder first: `AI_prompts.md` with six entries, `data.zip`, `.claude/launch.json`,
  and `data/` with the original and the working copy still carrying the same SHA-256. Nothing had
  changed overnight.
- Created `output/harness.md` in the Homework 4 format. Section 1 is the full analysis of the data
  (tables and exact schema, relationships declared and by convention, the three tickets, stock and
  margins, vendors, the cash squeeze, quirks to design around, what the data lacks). Section 2 is
  the ten shop rules as a table: each rule, the tool or module that enforces it, and the test that
  proves it. Section 3 is the design: the three-process diagram, the MCP tool list (read tools and
  write tools with the rule each carries, plus `open_ticket` because the brief says the team should
  be able to open tickets), the exact schema additions for the working copy, the back end (model
  factory, role-based tool matrix with `pay` in no agent's hands, `ask_colleague` with its guards,
  run loop with Boss triage, the approval round trip, feed and snapshot endpoints, audit trail), the
  dashboard panels, the expected story of a good run with the end state to verify, the build order
  with status, and three open items (the model name, whether the reprint invoice counts as stock on
  the way, who may open tickets).
- Two design details settled while writing: business dates (`paid_at`, `expected_date`) use the
  shop's clock while feed rows use real time so the feed orders correctly; and tests run against a
  temporary copy of the database, never the working copy.
- Step 2 of the build order is done; step 3 (the skeleton) is next.

---

### 8 — One step at a time; four confirmations before the MCP server
**Date:** 2026-11-03

> Lets go one step at a time. Yes we are following that homework 4 format. Please confirm the following:
> Confirm you have opened data/campus_customs.db and looked through each table and its fields.
> confirm you have copied the original file to data/campus_customs_new.db so that we can use this copy to update files later.
> confirm you have studied the open tickets and how they link to other tables.
> confirm you started output/harness.md and for each table you have the fields listed and a short line on why they matter to the agents (I think this is what you have in section 1 above).
> Once confirmed the next step will be to start working on the mcp server.

**Result:** Working mode set: one step at a time, Homework 4 format. The four confirmations:
1. **Database opened and read.** Every table's `CREATE` statement, column list, foreign keys, and
   every row were read on 2026-11-02 (prompt 3) with a read-only connection; integrity check `ok`.
   Recorded in harness 1.2.
2. **Working copy made.** `data/campus_customs_new.db` was copied from the original on 2026-11-02
   (prompt 4); both files still share SHA-256 `23686a90…f360a`, re-checked this morning.
3. **Tickets and their links studied.** Ticket 101 links to invoice 501, which links to vendor 1
   (Bulldog Print Co), and by SKU and size to the tee's inventory and pricing rows; ticket 102 links
   to lease 1; ticket 103 links by SKU to the hoodie's inventory and pricing rows and to no invoice
   or lease. Recorded in harness 1.3 and 1.4.
4. **Harness started, with per-table relevance.** Section 1 already listed every table's fields and
   contents; it did not yet say in one place why each table matters to the agents, so a table was
   added to harness 1.2 giving, for each of the nine tables, its fields and a short line on which
   agents use it and for what. Now confirmed as asked.

Next step, when the user says go: the MCP server. Because it needs a Python environment and a
folder to live in, the Python half of the skeleton (project virtual environment, `mcp_server/`,
pinned dependencies, `.env` files, `.gitignore`, launch entry) is done as the first part of that
step; the dashboard scaffold waits for its own step.

---

### 9 — The MCP server, part 1: ticket tools
**Date:** 2026-11-03

> Yes lets start the MCP server. Please write the MCP server in mcp_server/ using fastmcp. we want it to talk to data/campus_customs_new.db. You dont need to connect or run it in this assignment.
>
> Every agent can use the tools in the mcp server. for now lets write th tools needed for the tickets in the database. Keep the names clear, never invert any data, and only use information in the database.

**Result:**
- **Environment.** Created `.venv` (Python 3.14.10) at the project root. `pip install` failed three
  times with the same `InvalidChunkLength` error; diagnosis showed small and large wheels download
  fine and the break is on one file, the metadata sidecar for `httpx2` (a fastmcp dependency), which
  the server serves correctly and curl reads fine. `uv` then rejected the TLS certificate as an
  unknown issuer, which points to a certificate-intercepting proxy on this connection. Installing
  `uv` into the environment and running `uv pip install --system-certs` worked: fastmcp 4.1.6
  (a meta-package over `fastmcp-slim` and the `mcp` SDK 2.3.0) and pytest 9.2.0, pinned in
  `mcp_server/requirements.txt`. The workaround is in the README.
- **Code.** `mcp_server/db.py` (the working copy as the only database, a guard that refuses the
  original, `CAMPUS_DB_PATH` override, per-call connection with commit/rollback, schema additions:
  four ticket columns and the `ticket_events` table), `mcp_server/tickets.py` (the ticket functions
  with validation and an event log entry for every write), `mcp_server/server.py` (FastMCP server,
  streamable HTTP on port 8100, ten tools as thin wrappers). Tools: `get_today`, `list_tickets`,
  `get_ticket` (with the linked invoice and vendor, lease, stock, and pricing, plus days overdue and
  days until due computed against the shop's clock), `list_ticket_events`, `open_ticket`,
  `assign_ticket`, `set_ticket_priority`, `set_ticket_status`, `add_ticket_note`, `resolve_ticket`.
  Names say what they do; nothing is invented (every returned value is a column or arithmetic on
  columns); refusals are plain sentences.
- **Skeleton items done alongside:** `.gitignore`, `pytest.ini`, `.claude/launch.json` with an
  `mcp-server` entry (the Homework 4 entries removed), and a README stub with setup, run, and test
  commands.
- **Verified:** 22 tests in `mcp_server/tests/test_tickets.py` pass against a temporary copy of the
  database, including one that drives the tools through FastMCP's in-memory client (ten tools
  listed, seed data returned, a missing ticket surfaces as a tool error, a note written over MCP).
  The original and the working copy still share the same SHA-256. The server was not started or
  connected, as instructed. Harness section 4 records the layout, the tools, where each value comes
  from, the decisions, and the verification; section 3.7's status table is updated.

---

### 10 — Pause
**Date:** 2026-11-03

> lets pause here. I need to run out for an errand. will be back in about an hour

**Result:** Paused after the ticket tools. Nothing is running. Both database files are untouched.

**Resume here:** MCP server part 2, the remaining tools (stock, pricing, vendors, cash, invoices,
lease, purchase orders, approvals, drafts, `pay` carrying rules 4–7), the reset script, and one test
per rule. See harness 3.2 and 3.3 for the agreed tool list and schema additions.

---

### 11 — MCP server, part 2: shop, money, and the rules
**Date:** 2026-11-03

> ok claude im back but only have 20 minutes. lets see how much we can get done

**Result:** The rest of the MCP server, built on the resume point from entry 10.
- **Schema additions** (`db.py`): `approvals`, `drafts`, and `purchase_orders` tables, created on
  the working copy the first time a connection opens, exactly as drafted in harness 3.3 (plus a
  `decision_note` on approvals).
- **Read tools** (`shop.py`): `get_stock`, `list_stock`, `get_pricing` (margin computed from the two
  pricing columns), `list_vendors` (each with `can_ship`, false while an invoice is open),
  `list_invoices` (days overdue by the shop's clock), `get_lease` (days until due), `get_cash`,
  `list_payments`.
- **Money tools** (`money.py`): `create_purchase_order` (priced from `pricing.unit_cost`, dated
  today + `vendors.lead_days`, refused while the vendor has an open invoice), `request_approval`
  (amount read from the invoice, lease, or order it names, never typed in; moves the ticket to
  waiting_approval), `decide_approval` (the human's yes or no), `pay` (the only tool that moves
  cash: approved by a named human, same name at pay time, balance must cover it, vendor re-checked,
  then payment row + balance + invoice/lease/order + approval updated in one transaction),
  `draft_customer_message` and `list_drafts` (no send tool exists). 26 tools in all.
- **Reset** (`mcp_server/reset.py`, run as `python -m mcp_server.reset`): copies the original over
  the working copy and logs a system `reset` event. Not an MCP tool, so agents cannot reset.
- **Verified:** 31 tests pass (22 from part 1 plus `test_rules.py`, one test per shop rule 1–9;
  rule 10 belongs to the back end). Two first-run failures were test mistakes (a guessed mug SKU,
  which is `CC-MUG-CREST`, and a refusal message) and were fixed. Both database files still carry
  the original SHA-256. Harness section 5 has the details.

**Next:** the FastAPI back end skeleton (model via Portkey, confirm `gpt-6-luna` with one call, MCP
client, health/board/shop endpoints).

---

### 12 — Check the tool list in the harness; a README for the MCP server
**Date:** 2026-11-03

> can you confirm that in the output/harness.md, each of the tools are listed. please also list
> which table it reads, which ticket it helps unlock, and in one sentence describe why that too is
> the tight tool for each ticket. also confirm that mcp_server/README.md is the file that explains
> what the mcp server is for, which database file it uses and the tools it has.

**Result:** Checked the 26 tools the running server lists against the harness tables: 24 were
there; `list_purchase_orders` and `list_approvals` were missing from 5.3 and are now in it. Added
harness 5.6, a table of all 26 tools with the tables each reads and writes, the seed ticket(s) it
helps unlock (101 order, 102 rent, 103 price override), and one sentence on why it is the right
tool; the old 5.6 Verified became 5.7. `mcp_server/README.md` did not exist (the project README
covered the server in a few lines), so it was written: what the server is for, which database file
it uses and why the original is never opened, the run/test/reset commands, and all 26 tools grouped
by module with the rule each carries.

---

### 13 — Connect the MCP server to the project
**Date:** 2026-11-03

> ok great. Now lets add this mcp server to this project so that we can call the tools. save the
> connection JSON text in .mcp.json at the project root.

**Result:** `.mcp.json` at the project root registers the server as a project-scoped MCP server
named `campus-customs`, type `http`, at `http://127.0.0.1:8100/mcp` (the streamable-HTTP endpoint
the server already serves; the same one the back end will use). The server was started for the
first time from the `mcp-server` launch entry and the connection was proved from this project with
the standard `mcp` SDK client: initialize, 26 tools listed, `get_today` and `list_vendors` called
over HTTP. Opening the working copy applied the schema additions (four tables, four ticket columns),
so its hash now differs from the original; the seed rows are unchanged and the original is untouched.
One quirk found: on this machine fastmcp's own `Client` wrapper fails over HTTP (first POST's body
cut off, "peer unexpectedly closed connection"; direct `httpx2`, `urllib`, `curl`, and the `mcp`
SDK client all work; a local web-shield proxy is the likely cause, the same family as the pip
chunk error). The back end will use the `mcp` SDK client, which works. Harness 5.8.

To use the tools from Claude Code: start the server (`mcp-server` launch entry), reopen the session
so `.mcp.json` is read, approve the project server when asked; tools appear as
`mcp__campus-customs__<tool>`.

---

### 14 — The connector would not come up; switched Claude Code to stdio
**Date:** 2026-11-03

> im back / i dont think its working / ok im back

**Result:** Diagnosis first: the server on port 8100 was healthy the whole time (started by the
user in the app's Terminal 1 at 14:23; `curl` got 200; the probes show in its log), but the
session's `campus-customs` connector stayed "connection refused" from its first dial. Claude Code
dials project servers once per process start; reopening the session in the desktop app does not
restart that process (the terminal tabs and the server survived the reopen), the app has no
reconnect dialog for project servers, and quitting the app would kill a server started in its
terminal. Fix: `.mcp.json` now uses stdio, so Claude Code starts its own copy of the server
(`.venv/Scripts/python.exe -m mcp_server.server --stdio`); `server.py` gained the `--stdio` switch
and still serves HTTP on 8100 without it (for the back end). Verified by spawning that exact
command with the MCP SDK's stdio client: 26 tools, `get_today`, `get_ticket(102)`. 31 tests pass.
READMEs and harness 5.8 updated; one wrong instruction (type `/mcp` to reconnect) corrected, since
the desktop app has no such dialog. Remaining: quit and reopen the Claude app so the new
`.mcp.json` is read, then call a tool from inside the session.

---

### 15 — Tools called from inside Claude Code
**Date:** 2026-11-03

> ok just restarted

**Result:** After the app restart the `campus-customs` server connected on startup over stdio and
its 26 tools appeared in the session as `mcp__campus-customs__<tool>`, with the server's
instructions text attached. Three were called from inside Claude Code: `get_today` returned
2026-08-31; `get_ticket(101)` returned the tee order with invoice 501 (Bulldog Print Co, $840, 3
days overdue), the four tee sizes with S flagged at 0, and the tee's pricing; `list_vendors`
returned the three vendors with Bulldog Print Co's `can_ship` false. The MCP server step is
complete and connected. Next: the back end skeleton (build step 6).

---

### 16 — Smoke test of every tool through the connector, saved as output/mcp_smoke.json
**Date:** 2026-11-03

> can you re-test the tools to make sure they work and save the test confirmations in
> output/mcp_smoke.json. for every tool include the prompt, the tool name, and the tool output.
> make sure the outputs match values in data/campus_customs_new.db

**Result:** All 26 tools were called from inside the Claude Code session through the
`campus-customs` connector: 35 calls in all (15 reads on the untouched seed, the 11 write tools in
dependency order, then 9 re-reads of the changed tables). The writes form one story: restock
ticket 104 opened for the empty tee shelf; 101 assigned, 102 set to priority 1, 103 moved to
in_progress with a stock note; approval 1 requested for invoice 501 ($840, read from the invoice),
approved by "Store Manager", paid (checking $3,400 → $2,560, invoice paid, approval executed);
purchase order 1 drafted for 12 tees at $96, expected 2026-09-05 (now allowed, since the vendor is
paid); a customer draft saved for Tauhid Zaman; 104 resolved. `output/mcp_smoke.json` holds every
entry with the prompt, tool, arguments, verbatim output, and a `db_check`: the SQL run against the
working copy, the value expected from the output, the value the database returned, and whether they
match. `output/check_mcp_smoke.py` runs those checks and writes the results back: 35 of 35 match.
The original database still has its first hash. The working copy now carries this run's writes;
`python -m mcp_server.reset` restores the seed before the full run (rule 8).

---

### 17 — The back end: the five-agent team on gpt-6-luna
**Date:** 2026-11-03

> Yes, lets begin the backend. Please build the agentic team using Pydantic API: Boss, Inventory,
> Accounting, Facilities, and Customer Service. include prompts, models, and agent loops so they can
> delegate work to each other with full connectivity. Put the agent prompts in backend/prompts - one
> file per agent. put data types in backend/models.py, and the agent files under backend/. use
> PORTKEY_API_KEY and only gpt-6-luna for every agent.

**Result:** `backend/` built with PydanticAI 2.55 (the Homework 4 construction: an OpenAI client at
the Portkey URL wrapped in `OpenAIChatModel`, one `get_model()` for every agent, model name a
constant and any other value in `.env` refused).
- `prompts/`: `boss.md`, `inventory.md`, `accounting.md`, `facilities.md`, `customer_service.md`,
  plus `shared.md` (the shop's rules, how to work, who the colleagues are) that every agent gets.
- `models.py`: `AgentName`, `TriagePlan`/`TriageItem`, `BossDecision`, `RunEvent`, `Budget`,
  `TeamDeps` (the per-run context: agent, ticket, depth, chain, shared budget).
- `agents/`: `base.py` (prompt loader, the `ask_colleague` tool and its guards, the constructor) and
  one file per agent. `mcp_toolset.py` turns every MCP tool into an agent tool over the `mcp` SDK
  client; `team.py` owns the connection, hides `pay`, `decide_approval`, and `log_event` from the
  agents, runs delegations (depth ≤ 3, no self-calls, no cycles, 12 per ticket), logs every tool
  call and delegation to the ticket timeline, and runs triage / one ticket / the board. `run.py`
  is the console runner (`--reset --board`, `--ticket N`, `--approve ID --by NAME`).
- The MCP server gained a 27th tool, `log_event`, for that audit trail (32 server tests pass).
- **Found on the way:** the gateway's chat-completions endpoint rejects function tools for
  gpt-6-luna unless reasoning effort is "none" (HTTP 400 says so); set in `llm.py`. PydanticAI's
  own MCP classes are not in the slim install, hence the small toolset of our own. The model
  reports itself as `gpt-6-luna-2026-09-22`.
- **Verified:** 7 offline back end tests (scripted models, stdio server on a temp copy): prompts
  load, hidden tools stay hidden, the delegation guards, a Boss→Inventory round trip logged on both
  sides, tool calls logged with the agent's name, a refusal arriving as a sentence, the human's
  approve-and-pay path; 38 tests in all. Then live: ticket 102 alone (32 s; Facilities confirmed
  the lease, Accounting requested approval 1 for the $2,400 rent, the Boss left it waiting), and a
  full board run from a reset (2 min): triage ranked 102 > 101 > 103 and assigned them; all three
  ended waiting_approval with approvals 1 (rent $2,400), 2 (invoice 501 $840), 3 (10% price
  override), drafts to Tauhid Zaman and the Yale AI Club, no payment, cash still $3,400, and
  Accounting noting rent plus the invoice would leave $160. Logs: `output/agent_run_ticket102.txt`,
  `output/agent_run_board.txt`. Harness section 6.

**Next:** the FastAPI app (board, feed, approvals endpoints, approve → pay → Boss re-works the
ticket) and then the dashboard.

---

### 18 — Missing tools, the audit trail, the agent/tool/table map, and a safety section
**Date:** 2026-11-03

> add any tools will need to the MCP server so that they can work on open tickets. shop facts come
> from the mcp server over data/campus_customs_new.db - do not invent a second shop-tools layer that
> bypasses MCP. Wire all agents so that they append to output/audit_trail.json as they run. For each
> agent loop step, record enough to audit later. append to this file - do not wipe it each run. in
> output/harness.md, list each agent and each mcp tool along with which table the tool uses. also
> add a short safety section [...]. update mcp_server/README.md so the tool matches.

**Result:**
- **Tools.** The board run showed the agents could work all three tickets with what they had; the
  gap was looking a record up without a ticket link. Added `get_vendor`, `get_invoice`, and
  `list_leases` (functions already in `shop.py`), so the server has 30 tools. The back end has no
  shop-data code of its own: every read, write, event, human decision, and payment goes through an
  MCP tool; the only thing outside MCP is the rule 8 reset script, which agents cannot reach.
- **Audit trail.** `backend/audit_trail.py` appends JSON Lines to `output/audit_trail.json` (the
  Homework 4 shape): `run_started` for every agent run (the Boss on a ticket or the board, each
  colleague on a delegation) with agent, ticket, chain, parent run, the prompt and the prompt
  files; a `step` the moment each model response arrives (the request that went in, the text and
  tool calls with arguments that came out, tokens, the model name reported); `run_finished` with
  outcome, output, usage, duration or the error; `human` lines for decisions, payments, resets.
  The Team runs every agent through `run_agent`, which walks the agent graph node by node, so
  steps are written live, not reconstructed afterwards. The file is opened in append mode only.
- **Harness.** Section 7: each agent with the tools it leans on and the tables they touch; every
  MCP tool with the tables it reads and writes and who uses it; how the audit trail is laid out.
  Section 8: the guardrails in this build and what a real business adds before real customers and
  real money.
- **README.** `mcp_server/README.md` lists the 30 tools; the project README describes the trail.
- **Verified:** 40 tests pass (33 server, 7 back end, one of them writing a scripted ticket run
  to a temporary trail and checking every record, the parent link, and that an existing line
  survives). Live, on the board the earlier run left: the human approved and paid approval 1
  (rent $2,400; checking $1,000; lease moved to 2026-10-02), then the Boss re-worked ticket 102:
  it asked Facilities, Facilities asked Accounting (a two-level chain), Accounting found approval
  1 executed and the payment on record and requested nothing new, and the Boss resolved the
  ticket. `output/audit_trail.json` holds 23 records from that: 2 human, 3 runs linked by
  `parent_run_id` into boss → facilities → accounting, 15 steps with 16 tool calls, every step
  naming `gpt-6-luna-2026-09-22`, usage and duration per run. Log: `output/agent_run_rework102.txt`.

**Next:** the FastAPI app and the dashboard (steps 8 and 9).

---

### 19 — Expected outcomes per ticket, written before the run: output/desk_tickets.html

> before we build the fast API app and then dashboard there are a few items i need done. Before
> wiring the backend, lets make sure we write down what is expected of the team in each open
> ticket. build output/desk_tickets.html - a page where you can double click with one tab per
> ticket. add empty "cash" and "reflection" tabs for later problems. leave these two tabs blank or
> a "coming soon" note. On each tab fill an "expected" section only (leave room for an "actual"
> section you will fill in after we run each agent). For each expected section note who the boss
> should call first and why, note all the agent delegations expected, identify which mcp tools
> are expected to be used for the run. Dont just send every agent to every ticket, make sure the
> right agent goes to the right ticket.

**Result:**
- **The page.** `output/desk_tickets.html` is one self-contained file (no libraries, no network):
  double-click it and it opens. Five tabs: Ticket 101, Ticket 102, Ticket 103, Cash, Reflection.
  The tab is kept in the URL hash, so `desk_tickets.html#ticket-102` opens on that ticket, arrow
  keys move between tabs, and printing lays all five out one after another. A strip above the tabs
  states the shop date (2026-08-31), the cash ($3,400), the expected triage order (102, 101, 103)
  and the two-pass rule: agents cannot approve or pay, so a ticket that needs money ends the first
  pass at `waiting_approval`, the human decides, and the Boss re-works it.
- **Facts.** Every number on the page was read through the MCP server (`get_ticket` 101, 102,
  103 with their links, the vendors, the cash, the pricing); the routes follow the "typical
  routes" in `backend/prompts/boss.md` and each specialist's remit.
- **Expected, per ticket.** Each ticket tab has: who the Boss should call first and why; the
  delegations expected as an ordered chain with each request's substance; a table of the MCP
  tools expected with the caller and what each should show, including the refusals that are
  expected (`create_purchase_order` while invoice 501 is open) and the tools that should *not*
  appear; and the end state after the first pass and after the human's decision. The routes are
  not symmetric: **101** Inventory first (the S shelf is empty, so the order is a stock question
  before anything else), then Accounting for invoice 501, then Customer Service for the draft;
  Facilities never. **102** Facilities first (lease and landlord are its whole remit; it confirms
  the date from the lease record), then Accounting for the rent approval; Inventory and Customer
  Service never (no goods, and the landlord is not a customer). **103** Inventory first (eight
  mediums on hand, twelve short, through the same blocked vendor), then Accounting for the margin,
  the cash left after the two payments already pending and the `price_override` approval, then
  Customer Service; Facilities never.
- **Actual.** Each ticket tab ends with an Actual section holding five empty slots (first call
  made, delegation chain seen, tools called, end state, match with expected) to be filled from
  `ticket_events` and `output/audit_trail.json` after the runs.
- **Cash and Reflection** tabs hold a "Coming soon." note and nothing else.
- **Preview.** `.claude/launch.json` gained `desk-page`: Python's `http.server` on port 8090
  serving `output/`, because the in-app browser cannot open `file://` paths. The page itself does
  not need a server.
- **Harness.** Section 9: the page, the routes in one table, why the routes are not symmetric,
  how Actual will be filled, and what was verified.
- **Verified:** opened through the `desk-page` server; every tab switches by click and by arrow
  keys, the hash follows, a deep link to `#ticket-103` opens that tab, no console errors, nothing
  wider than the viewport at 1024 px, light and dark both render. The seed facts on the page
  match `get_ticket` 101, 102 and 103 called through the connector in this session (tee S 0, M 5,
  L 3, XL 2; invoice 501 $840 open, 3 days overdue; lease 1 $2,400 due 2026-09-02; hoodie M 8,
  cost $22, list $58).

**Next:** the FastAPI app (step 8), then the dashboard; after the reset-and-run, fill the Actual
sections.

---

### 20 — The API: backend/main.py

> Yes lets now build the API. In backend/main.py, use fast API and add routs that do the
> following: Return the three tickets and give a status of that ticket (whether it is open or
> resolved). Take a ticket ID and run the agent team on that ticket. Return recent agent events -
> what each agent said and which tools were used - so that the board can refresh. Approve a
> payment or purchase after a human clicks approve (agents only to prepare the pay. this route is
> what actually changes cash. return the current checking balance from cash_accounts. reset the
> database to the original values when you want to try a fresh run. from the backend/ start the
> server with - uvicorn main:app --reload --port 8000. in output/harness.md list each route in one
> line (what url / what it does)

**Result:**
- **The app.** `backend/main.py` is a FastAPI app over the existing `Team`: `create_app(team=None)`
  builds it, `app` is what uvicorn serves. From `backend/` with the environment active,
  `uvicorn main:app --reload --port 8000` starts it (the first lines of the file put the project
  root on `sys.path`, since uvicorn run from `backend/` would not); from the root,
  `python -m uvicorn backend.main:app --reload --port 8000`; `backend` in `.claude/launch.json`
  for the preview. The MCP server must be running on 8100: the API has no shop data of its own and
  reads and writes only through the MCP tools. Request and response types (`TicketSummary`,
  `DecisionRequest`, `JobInfo`, `EventsPage`, `CashView`) went into `backend/models.py`.
- **The six routes asked for.** `GET /tickets` lists the tickets with their status and an `open`
  flag (true unless resolved). `POST /tickets/{id}/run` runs the Boss on that ticket as a
  background job (answered at once with the job; `?wait=true` waits and returns the decision), so
  a dashboard click never hangs for the minutes a run takes. `GET /events` returns the ticket
  timeline, which carries what each agent said (delegations and replies, notes) and every tool
  call with its arguments and a result preview; `?since=` and the returned `last_id` let the board
  poll for only what is new. `POST /approvals/{id}/approve` records the human's decision and then
  pays: the only route that changes cash; a payment the rules refuse (not enough cash, vendor
  still owed) comes back as `refused` with the approval left approved for a retry, a price
  override carries no payment, and by default the Boss then re-works the ticket in the background.
  `GET /cash` returns the checking balance from `cash_accounts` with every account. `POST /reset`
  copies the original over the working copy, records the reset on the audit trail, and is refused
  while the team is working. Supporting routes: `GET /health`, `GET /tickets/{id}`,
  `POST /board/run`, `GET /runs` and `/runs/{id}`, `GET /approvals`,
  `POST /approvals/{id}/reject`, `GET /drafts`. All fourteen are listed one line each in
  `output/harness.md` section 10.2. One run at a time: a second run or a reset while the team is
  busy is 409.
- **Packages.** `fastapi==0.162.0` and `httpx==0.28.1` (for FastAPI's test client) installed with
  `uv --system-certs` and pinned in `backend/requirements.txt`; uvicorn 0.54.0 was already there.
- **Tests.** Six offline API tests (`backend/tests/test_api.py`): the board and `open`, one ticket
  with links and a 404, a run as a job and the timeline it writes with `since`/`last_id` polling,
  the cash view, approve pays and moves the lease date with the refusals (second approve, approve
  after reject, not enough cash), the busy guard, the reset.
- **Live check** through the API on port 8000, every call and response appended to
  `output/api_live_check.jsonl`: reset (3 tickets, 0 payments, $3,400); the Boss on ticket 102
  with `wait=true` in 40 s, ending `waiting_approval` with two pending approvals and 30 timeline
  events (17 tool calls, 2 delegations); approve of the rent: payment $2,400, checking $1,000,
  lease moved to 2026-10-02, re-work started in the background and finished in 30 s.
- **A finding and a fix.** The re-work's decision said `resolved`, but the ticket was still
  `waiting_approval`: the Boss had not called `resolve_ticket`. The API reported both truthfully;
  the Boss had claimed work the tools did not show. Added `decision_matches_the_ticket`, an output
  validator on the Boss's ticket agent that reads the ticket and sends the Boss back (a `retry`
  event on the timeline) when the decision says `resolved` or `waiting_approval` and the ticket
  does not agree; after the agent's two retries the run ends `blocked`. PydanticAI forbids a
  per-run output type on an agent with validators, so the Boss is now two agent objects on the
  same prompt: a ticket agent (decision) and a triage agent (plan). Details in harness 10.5. On
  the re-run the Boss claimed `resolved` again, was sent back, called `resolve_ticket`, and ticket
  102 ended `resolved` in the database with a written resolution.
- **Behaviour notes for the desk page's Actual sections.** First call Facilities, as expected.
  Accounting, asked for the rent approval, ranked the overdue invoice first and requested that
  instead (on ticket 102); the Boss then requested the rent itself. On the re-work the agents
  read the moved lease date (2026-10-02) as a conflict with the notice's "due in 2 days" rather
  than as the consequence of the payment they had just confirmed. Both are within the rules and
  worth a prompt adjustment before the full run.
- **Verified:** 47 tests pass (33 server, 8 team, 6 API); the live sequence above; the original
  database untouched.

**Next:** the dashboard (step 9); then reset, the full run, and the Actual sections.

---

### 21 — The dashboard: frontend/ (React + Vite + TypeScript) and output/design.md

> build the frontend dashboard in frontend/ with react + vite + TypeScript. The page should call
> the routes we previously built. Lets make sure it: Lists all three tickets. Lets you pick one
> ticket and start the agent team on it. show each agent and what they are saying / doing while
> the ticket runs. Mark a ticket resolved when the run finishes. show a short summary of what each
> agent did on that ticket. let a human approve and pay or purchase when asked. show the checking
> balance (it should drop after an approved pay). Make the dashboard look very sophisticated with
> a clean look to match the style and them of the website we built in HW4. tell the frontend to
> talk to the backend at http://localhost:8000. on the backend allow the vite page origin so the
> browser is allowed to call those routes. start the board with npm run dev. write
> output/design.md with the final look, layout, how agents read differently, how resolved tickets
> and cash show up, and why. make sure to include the cool features that makes it feel special and
> users would enjoy using.

**Result:**
- **The page.** `frontend/` is React 19 + Vite 8 + TypeScript with no UI library, on the same
  package versions as the HW4 storefront. `npm run dev` serves it on 5173; `frontend` in
  `.claude/launch.json` starts it for the preview. `src/api.ts` talks to `http://localhost:8000`
  (`VITE_API_URL` overrides), and the API now allows the Vite origin through CORS (the two
  `localhost:5173` origins plus a regex for any other local port).
- **The brief's list.** The board lists the three tickets; the selected card's button starts the
  team on that ticket; the live floor shows each agent (a team strip with the active one lit and
  its current action in words) and what it says and does (asks and reports as colour-coded cards,
  tool calls as plain-word lines with the real call and result one click down, notes, the Boss's
  call); when a run ends the card is re-read from the API and a resolved ticket gets the chip, a
  green stamp and its resolution text; "Who did what" summarises each agent's tool calls, who it
  asked, its notes and the last thing it said; "Needs you" lists pending approvals with
  "Approve & pay $2,400" and Reject (with an inline note); the checking balance in the top bar
  counts down after a payment and floats the difference.
- **The look.** The HW4 system: Yale Blue, EB Garamond headlines, Source Sans 3 uppercase labels,
  white panels with thin gray rules, square corners, a blue stripe at the top; one colour per
  agent everywhere; colour otherwise spent only on meaning (green done, amber waiting on you, red
  refused). `output/design.md` records the look, the layout, how the agents read differently, how
  resolved tickets and cash show up, and why, with the features that make it feel special and a
  table of screenshots in `output/screens/`.
- **Two fixes the first loop forced.** The first dashboard loop ended with the Boss's re-work
  `blocked` (the team re-read "rent due in 2 days" against the $1,000 left and called the shop
  short, after confirming the very payment). The re-work after a decision now carries what was
  decided (`Team.work_ticket(ticket_id, context)`, composed by the approve and reject routes and
  shown on the timeline's run line), and `boss.md` and `accounting.md` each gained a line: money
  already out means the ticket is done; the ticket's wording was written when it was opened;
  judge by the records now; never request the same payment twice. Harness 11.4.
- **Harness.** Section 11: what it is and where things are, how it stays live, decisions, the two
  fixes, and what was verified. Section 3.7 row 9 marked done. README: a dashboard section and the
  design doc in the documentation map.
- **Verified:** `npm run build` passes; the back-end tests pass; live in the in-app browser at
  1440 × 900 with the final code: reset on the page (two clicks, $3,400, all open), run ticket
  102 (card amber, "Team working on ticket 102", Facilities lit, the feed filling, done inside
  48 s at "Needs approval" with the rent card in "Needs you"), approve (toast "Paid $2,400.00 ·
  Checking is now $1,000.00. The Boss is re-working ticket 102.", counter $3,400 → $1,000 with
  "−$2,400.00", receipts in the feed, "Decided (1)"), re-work (done inside 45 s, no retry: chip
  `Resolved`, the stamp, the resolution text naming approval 1 and payment 1, the Boss's call in
  green, "Who did what": Boss 9 tool calls asked Facilities and Accounting; Facilities 3;
  Accounting 7). No page errors; the only console errors were connection-refused lines from the
  minute the API was restarted, after which the page recovered on its own.

**Next:** step 10: reset, the full board run from the dashboard, fill the desk page's Actual
sections and the Cash and Reflection tabs, the end-state check (harness 3.6), README, submission.

---

### 22 — The full run: reset, board, approvals, Actual and Cash tabs, resolved_tickets.json, resolved_board.html

> lets now run the board. lets make sure we reset the working database data/campus_customs_new.db
> again so we start clean. note the starting checking balance then run all three tickets until
> they are resolved. open output/desk_tickets.html and on each tab fill the actual section from
> this run (which agents worked, what they delegated, and what tools were used). keep the expected
> section to compare the two. On the cash tab of the same output/desk_tickets.html itemize the
> money. starting checking balance (after reset), for each ticket, how cash changed when the ticket
> was resolved and why, ending checking balance - must match cash_accounts in the working database.
> save output/resolved_tickets.json - for each ticket. include id, final status, short outcome,
> what each agent contributed and any human approvals. save output/resolved_board.html - make sure
> you can double click with a screenshot of the react board for each resolved ticket. append real
> runs to output/audit_trail.json. finish output/harness.md so it covers tables, mcp tools, all
> agents, API routes, the dashboard and all safety rules.

**Result:**
- **A "Run the board" button** on the dashboard (the API already had `POST /board/run`): the Boss
  triages, then works every open ticket, and the page follows the Boss from ticket to ticket; the
  top bar reads "Team working on the board, ticket N".
- **The run**, all from the dashboard: reset (checking **$3,400**), Run the board (triage 102 P1 →
  Facilities, 101 P2 → Inventory, 103 P3 → Inventory, as expected), all three ended waiting on the
  human with rent $2,400, invoice 501 $840 and a price override; then the approvals one at a time:
  rent paid → 102 resolved; invoice paid → the re-work drafted purchase order 1 (one size-S tee,
  $8) and asked again → paid → 101 resolved on the order, expected 2026-09-05, with a dated draft;
  override approved (no payment) → 103 resolved as 8 now at $52.20 and 12 when cash allows.
  Checking ended at **$152.00** = `cash_accounts` in the working copy = $3,400 − 2,400 − 840 − 8.
- **One prompt clarification the run forced** (harness 12.4): twice the Boss called a ticket
  `blocked` that a manager would call handled (a paid back-order with a date; a partial fill with
  an approved price). `boss.md` now defines "done" for both; no code changed; the API was restarted
  and the two tickets re-run from their cards.
- **The desk page**: the Actual section on each ticket tab filled from the run (first call made,
  delegation chain pass by pass, every tool per agent with counts, end state, match with
  expected), the Expected sections untouched; the Cash tab itemises starting balance, each
  payment with its ticket and reason, the running balance, the ending balance and the check
  against the database.
- **`output/resolved_tickets.json`**: per ticket id, type, final status, the Boss's decisions
  (the short outcome), each agent's tool calls and reports, delegation chains, approvals with who
  decided, payments, drafts, purchase orders, cash change; plus the cash ledger and the whole end
  state (approvals, payments, orders, drafts, invoices, leases, stock).
- **`output/resolved_board.html`**: one self-contained file (screenshots embedded) with the end
  state, the cash ledger and its match against the database, and the React board at each resolved
  ticket with its resolution.
- **Audit trail**: 163 → 374 records, appended during the run, none rewritten.
- **Harness**: section 12 (setup, triage, each ticket's path, the prompt clarification, the end
  state against 3.6, expected against actual, where the record is) and section 13, an index of
  where the tables, the MCP tools, the agents, the API routes, the dashboard and the safety rules
  are covered; the rules table in section 2 corrected to the tools' real names.
- **Verified:** the ending balance read three ways agrees ($152.00); the original database's
  SHA-256 is unchanged; 314 timeline events; 0 validator retries; 0 refused tool calls; the three
  resolved tickets' screenshots are in `output/screens/`.

**Left for the submission:** the Reflection tab, the archive, and the public repository.

---

### 23 — The Reflection tab

> Write the reflection

**Result:** the Reflection tab of `output/desk_tickets.html` (about 1,250 words, eight short
sections), written from the run's own record rather than in general terms. It opens with the run
in numbers (3 tickets, 9 Boss passes, 18 delegations, 190 tool calls, 314 timeline events, 211
audit records, 3 payments totalling $3,248, 4 drafts; 0 refused calls, 0 validator retries, 2
"blocked" calls fixed with two sentences; 40 to 90 seconds a pass). Then: what the team got right
unprompted (triage, the right specialists, the cash squeeze found and respected, no duplicate
request, refusals avoided by checking first); that facts came from tools while judgment, the
meaning of "done", had to be written down; enforce in code what cannot be got wrong, prompt the
rest, and verify the seam (the decision validator fired zero times in the final run); the human
as the one who keeps the pen, and the dashboard built around that; variance as the cost of the
technology and visibility as the answer; cost and chattiness, and the initiative the team did not
take (the empty mug shelf); what to build next (a regression harness scored against the Expected
sections, least privilege, spend limits, a standing restock rule, an agreed meaning of "done");
and a one-sentence close: treat agents like new staff.

**Verified:** the tab opens from the hash, the intro and tab label now name it, no console errors.

**Left for the submission:** the archive and the public repository.

---

### 24 — The reflection, rebuilt around five questions, with the page as evidence

> Make sure we include the following in the reflection: How we evaluate performance of the agents
> on each ticket and why? for each ticket, how did the actual compare to the expected plan? Is
> there a simpler option than one agent with tools? if so why? what are three new problems campus
> customs might face that this agent team can solve with the tools already built. what are three
> new problems that cannot be resolved with the tools built? open output/desk_tickets.html and
> fill in the reflection tab.

> tie every answer to this app and the three tickets run. use ticket tabs and cash tab on the same
> page as evidence.

**Result:** the Reflection tab of `output/desk_tickets.html` rewritten (about 2,500 words) with
one numbered section per question, each tied to this app and the three tickets, with in-page
links to the 101, 102 and 103 tabs and the Cash tab wherever a claim rests on them (the page's
tabs switch on the hash, so a link opens the evidence).
1. **How we evaluate, and why:** expectations written before the run; Actual filled from the
   timeline, the audit trail and the tables, never from the agents' summaries; five checks per
   ticket (first call; who worked it and who stayed off; tools, none forbidden, no avoidable
   refusal; end state in the database after each pass; the final call is true, enforced by the
   validator) plus cost (passes, tool calls) and the human's load; why outcome and process are
   scored together (a false "resolved" would pass an outcome test; 103's "blocked" was wrong on
   outcome and right on every fact).
2. **Actual against expected per ticket:** a table (first call, delegations expected → actual,
   tools, end state, verdict) and the pattern: the plan was right about who and with what on
   every ticket; every deviation was about when to stop.
3. **A simpler option:** yes, two. Rules for the two predictable paths (102 and 101's money
   path, already half-encoded as the server's refusals) and one agent with the same tools and
   the same human gate instead of a team, with the run's own evidence (the Boss resolved 102's
   re-work alone; specialists mostly read tools and reported; hand-offs were where context
   thinned); when a team becomes worth it.
4. **Three new problems the tools can solve:** the empty mug shelf (Elm City Gifts, 3 days, 40
   mugs for $140 inside the $152 left, the 101 path), the next rent notice or a second lease (the
   102 path, cash the only question), a customer order filled or substituted from stock (101 and
   103 without the vendor).
5. **Three the tools cannot:** receiving and selling (PO 1 can never be received or sold; cash
   only goes out), changing a deal with an outsider (no send tool, no channel, lease, invoice and
   vendor rows read-only), money coming in or new things (no deposit, refund or new-SKU tool;
   103's $112 shortfall can be reported, never relieved); why the gaps are deliberate.
6. What else the run taught us (facts from tools, judgment from conventions; enforce, prompt,
   verify the seam; the human kept the pen; same prompt, different path; slower, chattier, no
   initiative). 7. What we would build next. One sentence to close.

**Verified:** the tab opens from the hash with the seven sections and the comparison table; the
evidence links switch to the ticket and Cash tabs; no console errors.

**Left for the submission:** the archive and the public repository.

---

### 25 — The submission archive and the public repository

> Archive and repo

> lets push this code to a public github repository so the graders can clone it.

> as before, do not push the real .env to the github repo. but do include the database files
> under data/

**Result:**
- **Checks first.** `gh` signed in as AMR6958-coder (the HW4 account), git identity set, and the
  Portkey key value found nowhere in the tree except `backend/.env` (`.env.example` holds a
  placeholder; `config.py` only reads the variable).
- **README.** A "Quick start (clone and run)" for graders: clone, the database files already in
  `data/`, the virtual environment and both requirement files, `backend/.env` from the example
  with `PORTKEY_API_KEY`, three terminals (MCP server 8100, API 8000 from `backend/` with
  `uvicorn main:app --reload --port 8000`, dashboard 5173 with `npm run dev`), then Reset shop and
  Run the board; `python -m pytest` for the 47 tests. The repository URL and what is and is not
  included.
- **Archive.** `campus-customs-hw5-submission.zip` at the project root: 92 files, 848 KB; the
  source, prompts, tests, outputs (harness, design, desk page, resolved tickets, resolved board,
  audit trail, screenshots), `.mcp.json`, `.claude/launch.json`, both database files; not
  `.venv/`, `frontend/node_modules/`, `frontend/dist/`, `backend/.env`, `data.zip`.
- **Repository.** https://github.com/AMR6958-coder/campus-customs-hw5, public, branch `main`.
  Commit 1: the whole tree per `.gitignore` (no `.env`, no databases, no archives); the staging
  list was checked for `.env`, `.db`, `.zip`, `node_modules`, `.venv` and `dist` before the
  commit. Commit 2, on the instruction above: `.gitignore` no longer excludes `data/*.db`, so
  `data/campus_customs.db` (the untouched original) and `data/campus_customs_new.db` (the working
  copy as the full run left it) are committed; `backend/.env` remains excluded and only
  `.env.example` is in the repository. Verified on GitHub: `data/` lists both files; `backend/`
  lists `.env.example` and no `.env`.

**Verified:** `gh repo view` reports PUBLIC on `main`; the GitHub contents API shows the two
database files and no `.env`; the archive lists both databases and no `.env`.

---

### 26 — The repository URL in output/github_url.txt

> when complete can you also out the repo URL in output/github_url.txt

**Result:** `output/github_url.txt` holds the one line
`https://github.com/AMR6958-coder/campus-customs-hw5`. Committed and pushed; the archive rebuilt
so it carries the file too.

---
