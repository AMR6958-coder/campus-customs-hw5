# Campus Customs — Agentic Shop Team

MGT 409 E1, Homework 5. An agent team that runs the Campus Customs shop's back office: tickets
land on a board, five agents (Boss, Inventory, Accounting, Facilities, Customer Service) work them,
and a human watches and approves payments from a dashboard.

Three pieces talk to each other:

| Piece | Folder | Port | Status |
|---|---|---|---|
| MCP server (FastMCP): the shop's data and actions as tools | `mcp_server/` | 8100 | done (30 tools, 33 tests) |
| FastAPI back end: the five PydanticAI agents, run loop, approvals | `backend/` | 8000 | done: agent team, audit trail, API (`backend/main.py`, 14 routes; 14 tests) |
| React dashboard: board, live floor, approvals, cash, drafts | `frontend/` | 5173 | done (React 19 + Vite 8 + TypeScript; `npm run dev`) |

**Data.** `data.zip` (provided with the assignment) unzips to `data/campus_customs.db`, the untouched
original. The agents work on a copy, `data/campus_customs_new.db`; resetting means copying the
original over it. Both files are committed under `data/`, the working copy as the full run left
it, so a clone can run, or reset and run again, without the course's `data.zip`.

**Repository:** https://github.com/AMR6958-coder/campus-customs-hw5 (public). **Submission
archive:** `campus-customs-hw5-submission.zip`, the same tree. Not in either: `data.zip`,
`backend/.env` (the gateway key; only `.env.example` is included), `.venv/`,
`frontend/node_modules/`, `frontend/dist/`.

## Quick start (clone and run)

1. `git clone https://github.com/AMR6958-coder/campus-customs-hw5.git` and `cd` into it.
2. The database files are already in `data/`: `campus_customs.db` (the untouched original) and
   `campus_customs_new.db` (the working copy, as the full run left it: three tickets resolved,
   checking $152). To start clean, `.venv\Scripts\python -m mcp_server.reset` after step 3, or
   press Reset shop on the dashboard.
3. `py -3.14 -m venv .venv`, then install both requirement files into it (commands below; use the
   `uv` fallback if pip fails behind a proxy).
4. `copy backend\.env.example backend\.env` and fill in `PORTKEY_API_KEY` (and `PORTKEY_BASE_URL`
   if yours differs). Every agent runs on `gpt-6-luna` through that gateway.
5. Three terminals: the MCP server (`.venv\Scripts\python -m mcp_server.server`, port 8100); the
   API (`cd backend`, then `uvicorn main:app --reload --port 8000` with the environment active);
   the dashboard (`cd frontend`, `npm install`, `npm run dev`, port 5173).
6. Open `http://localhost:5173`, press **Reset shop**, then **Run the board**, and approve what the
   team asks for in "Needs you". `python -m pytest` runs the 47 offline tests.

**Shop rules** are listed in `AI_prompts.md` ("Shop rules") and, with where each is enforced, in
`output/harness.md` section 2.

## Setting up

Python 3.14 and Node 20+. One virtual environment at the project root serves both Python pieces:

```
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r mcp_server\requirements.txt
```

If pip stops partway with an `InvalidChunkLength` error (seen on one machine behind a
certificate-intercepting proxy), install the `uv` installer into the environment and let it use the
system certificates:

```
.venv\Scripts\python -m pip install uv
.venv\Scripts\uv pip install --system-certs --python .venv\Scripts\python.exe -r mcp_server\requirements.txt
```

The database files are in `data/`. If you want to rebuild the working copy from the original:

```
copy data\campus_customs.db data\campus_customs_new.db
```

## The MCP server

```
.venv\Scripts\python -m mcp_server.server
```

serves the tools over streamable HTTP on port 8100 (also defined as `mcp-server` in
`.claude/launch.json`). Point it at another file with `CAMPUS_DB_PATH`. The tests run every tool
against a temporary copy of the original and check the original is untouched afterwards:

```
.venv\Scripts\python -m pytest
```

### Calling the tools from Claude Code

`.mcp.json` at the project root registers the server as a project MCP server named
`campus-customs`. It uses stdio: Claude Code starts its own copy of the server
(`.venv/Scripts/python.exe -m mcp_server.server --stdio`) when a session opens and stops it when the
session ends, so nothing has to be running first. Open the project in Claude Code, approve the
project server when asked, and the tools appear as `mcp__campus-customs__<tool>`, for example
`mcp__campus-customs__get_ticket`.

That copy and the HTTP server on port 8100 (which the back end and the dashboard use) are separate
processes reading and writing the same working copy, which SQLite handles. Claude Code reads
`.mcp.json` only when its process starts; in the desktop app, closing and reopening a session does
not restart it, so after a change to `.mcp.json` quit the app and open it again. To connect Claude
Code to the HTTP server instead, use `{"type": "http", "url": "http://127.0.0.1:8100/mcp"}`.

Before a full run, reset the working copy to the seed (this is a script, not a tool, so the agents
cannot do it):

```
.venv\Scripts\python -m mcp_server.reset
```

Money moves only through the `pay` tool, only against an approval a named human has marked
approved, and never below a zero balance. Customer messages are drafts on the board; there is no
send tool.

## The back end: the agent team

Five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer Service), every one on
`gpt-6-luna` through the Portkey gateway, every one with the shop's MCP tools and an
`ask_colleague` tool that lets any agent hand work to any other. Prompts are in `backend/prompts/`
(one file per agent plus `shared.md`), data types in `backend/models.py`, the agents in
`backend/agents/`, the delegation and run loop in `backend/team.py`.

Setup: install the back end's packages into the same environment and create its `.env`:

```
.venv\Scripts\python -m pip install -r backend\requirements.txt
copy backend\.env.example backend\.env
```

Fill in `PORTKEY_API_KEY` (the `uv --system-certs` fallback above works here too). With the MCP
server running, the console runner drives the team; the dashboard will do the same through the
API:

```
.venv\Scripts\python -m backend.run --reset --board          # reset the shop, triage, work every ticket
.venv\Scripts\python -m backend.run --ticket 102             # one ticket
.venv\Scripts\python -m backend.run --approve 1 --by "Store Manager"   # the human approves and pays
```

Agents never see `pay` or `decide_approval`; those run only from the human's path. Every tool call
and every delegation is written to the ticket timeline, and every agent run, every model step
(what went in, what came out, tokens), every human decision, and every reset is appended to
`output/audit_trail.json` (JSON Lines; the file is never truncated). Read the end of it with
`python -m backend.audit_trail --tail 5`. `python -m pytest` runs the back end's
offline tests (scripted models, a stdio copy of the server, no gateway calls) with the server's.

### The API

`backend/main.py` is the FastAPI app the dashboard talks to. With the MCP server running and the
virtual environment active, start it from `backend/`:

```
cd backend
uvicorn main:app --reload --port 8000
```

(From the project root, `.venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000`
does the same, and `backend` in `.claude/launch.json` starts it for the in-app preview.)
Interactive docs are at `http://127.0.0.1:8000/docs`. The routes, one line each, are in
`output/harness.md` section 10: the board (`GET /tickets`), a run (`POST /tickets/{id}/run`, a
background job; add `?wait=true` to get the Boss's decision back), the timeline for the board to
refresh from (`GET /events?since=`), the cash (`GET /cash`), the human's approve, which is the
only thing that moves cash (`POST /approvals/{id}/approve`), reject, and `POST /reset` for a fresh
run. One run at a time: a second run or a reset while the team is working is refused with 409.

## The dashboard

`frontend/` is the React + Vite + TypeScript page a human runs the desk from: the three tickets on
a board, a live floor that shows each agent and what it is saying and doing while a ticket runs,
the Boss's call and the resolved stamp when a run finishes, a per-agent summary of who did what,
the approval queue with Approve & pay / Reject (the only place cash moves), the checking balance
counting down after a payment, drafts to customers (never sent), and a two-click reset. The look
follows the Homework 4 storefront: Yale Blue, EB Garamond, Source Sans 3, thin rules, square
corners. `output/design.md` describes the design and why; `output/screens/` holds screenshots.

With the MCP server (8100) and the API (8000) running:

```
cd frontend
npm install
npm run dev
```

opens `http://localhost:5173`. The page talks to `http://localhost:8000` (override with
`VITE_API_URL`, see `frontend/.env.example`); the API allows that origin through CORS. `frontend`
in `.claude/launch.json` starts it for the in-app preview.

## The full run

Done on 2026-11-03 from the dashboard: reset ($3,400), "Run the board" (triage ranked 102, 101,
103 and assigned Facilities, Inventory, Inventory), then every approval on the page. Rent $2,400,
invoice 501 $840 and a $8 purchase order for the size-S tee were paid; the 10% hoodie override was
approved with no payment; all three tickets ended resolved; checking ended at **$152.00**, which
matches `cash_accounts` in the working copy. The record: `output/resolved_tickets.json`,
`output/resolved_board.html` (double-click; the board at each resolved ticket), the Actual and
Cash tabs of `output/desk_tickets.html`, `output/audit_trail.json`, and section 12 of the harness.

## Documentation map

- `AI_prompts.md`: every prompt given to the AI assistant during the build, with what resulted.
- `output/harness.md`: the design record, step by step (data analysis, rules, design, each step's
  notes and what was verified).
- `output/design.md`: the dashboard's design: the look, the layout, how the agents read
  differently, how resolved tickets and cash show up, and why. Screenshots in `output/screens/`.
- `output/desk_tickets.html`: the desk page. One tab per ticket with what the team was expected
  to do (who the Boss calls first and why, the delegations, the MCP tools, the end state), written
  before the run, and the Actual section filled from the full run for comparison; the Cash tab
  itemises the money; the Reflection tab says what the run taught us. Double-click to open; for
  the in-app preview, `desk-page` in `.claude/launch.json` serves `output/` on port 8090.
- `output/resolved_tickets.json` and `output/resolved_board.html`: the full run's record per ticket
  (status, outcome, what each agent did, approvals, payments) and the board at each resolution.
- `output/audit_trail.json`: every agent run, model step, human decision and reset, appended.
- `output/github_url.txt`: the repository's URL.
