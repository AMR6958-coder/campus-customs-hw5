"""The Campus Customs API: FastAPI over the agent team.

Start it from ``backend/`` with the project's virtual environment active::

    uvicorn main:app --reload --port 8000

or from the project root::

    .venv\\Scripts\\python -m uvicorn backend.main:app --reload --port 8000

The MCP server must be running on port 8100: the API reaches the shop only
through its tools, the same way the agents do. Interactive docs: /docs.

Routes
    GET  /health                          the API, the model, the MCP connection, the shop's date, whether the team is busy
    GET  /tickets                         the tickets on the board with their status and `open`
    GET  /tickets/{id}                    one ticket with everything it links to
    POST /tickets/{id}/run[?wait=true]    the Boss works that ticket (background job; wait=true returns the decision)
    POST /board/run[?wait=true]           triage, then every open ticket in priority order
    GET  /runs, GET /runs/{job_id}        background jobs and their results
    GET  /events?since=&limit=&ticket_id= the ticket timeline: what each agent said and which tools it used
    GET  /cash                            the checking balance (and every account) from cash_accounts
    GET  /approvals?status=               the human's queue
    POST /approvals/{id}/approve          the human approves; this is what moves cash (then the Boss re-works the ticket)
    POST /approvals/{id}/reject           the human rejects; the ticket goes back to in_progress
    GET  /drafts                          customer messages waiting on the board (nothing is sent)
    POST /reset                           copy the original database over the working copy for a fresh run

One run at a time: a second run, or a reset, while the team is working is refused with 409.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ``uvicorn main:app`` from backend/ puts backend/ on sys.path, not the project root, and the
# back end imports itself as a package (backend.*) and the server's modules as mcp_server.*.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import Depends, FastAPI, HTTPException, Query, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend import config  # noqa: E402
from backend.audit_trail import AuditTrail, new_run_id  # noqa: E402
from backend.models import CashView, DecisionRequest, EventsPage, JobInfo, JobKind, RunEvent, TicketSummary  # noqa: E402
from backend.team import Team, unwrap  # noqa: E402
from mcp_server.reset import reset_working_copy  # noqa: E402

START_COMMAND = ".venv\\Scripts\\python -m mcp_server.server"
DASHBOARD_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def is_error(result: Any) -> bool:
    """The MCP toolset returns a refused call as {"error": sentence}."""
    return isinstance(result, dict) and "error" in result


def print_event(event: RunEvent) -> None:
    """The uvicorn console shows the team at work, like the console runner does."""
    ticket = f" #{event.ticket_id}" if event.ticket_id is not None else ""
    print(f"{event.at:%H:%M:%S} [{event.agent}{ticket}] {event.kind}: {event.message}", flush=True)


# --------------------------------------------------------------------------
# The back end's state: one Team (one MCP connection) and the background jobs
# --------------------------------------------------------------------------


class Backend:
    def __init__(self, team: Team | None = None) -> None:
        self._given = team  # a prebuilt Team (the tests pass one on stdio with a scripted model)
        self.team: Team | None = None
        self.connect_error: str | None = None
        self.jobs: dict[str, JobInfo] = {}
        self.tasks: dict[str, asyncio.Task[Any]] = {}

    async def connect(self) -> Team:
        """Connect to the MCP server once; later calls reuse the connection."""
        if self.team is None:
            team = self._given or Team()
            try:
                await team.__aenter__()
            except Exception as exc:
                self.connect_error = f"{type(exc).__name__}: {exc}"
                raise
            team.listeners.append(print_event)
            self.team, self.connect_error = team, None
        return self.team

    async def try_connect(self) -> Team | None:
        try:
            return await self.connect()
        except Exception:
            return None

    async def close(self) -> None:
        if self.team is not None:
            await self.team.__aexit__(None, None, None)
            self.team = None

    @property
    def audit(self) -> AuditTrail:
        return self.team.audit if self.team is not None else AuditTrail()

    # ---- jobs ----

    @property
    def current(self) -> JobInfo | None:
        for job in self.jobs.values():
            if job.status == "running":
                return job
        return None

    def refuse_if_busy(self, doing: str) -> None:
        job = self.current
        if job is not None:
            about = f" on ticket {job.ticket_id}" if job.ticket_id is not None else ""
            raise HTTPException(409, f"Cannot {doing}: the team is busy ({job.kind}{about}, job {job.id}). Wait for it to finish.")

    def start_job(self, kind: JobKind, ticket_id: int | None, work: Callable[[], Awaitable[Any]]) -> JobInfo:
        """Run `work` in the background and track it; one job at a time."""
        self.refuse_if_busy(f"start a {kind} run")
        job = JobInfo(id=new_run_id(), kind=kind, ticket_id=ticket_id, started_at=now())
        self.jobs[job.id] = job

        async def runner() -> None:
            try:
                result = await work()
                if isinstance(result, list):
                    job.result = [item.model_dump(mode="json") for item in result]
                else:
                    job.result = result.model_dump(mode="json")
                job.status = "done"
            except Exception as exc:  # the Team already wrote the error to the audit trail
                job.error = f"{type(exc).__name__}: {exc}"
                job.status = "error"
            finally:
                job.finished_at = now()

        self.tasks[job.id] = asyncio.create_task(runner())
        return job

    async def finish(self, job: JobInfo) -> JobInfo:
        task = self.tasks.get(job.id)
        if task is not None:
            await task
        return job


# --------------------------------------------------------------------------
# The app
# --------------------------------------------------------------------------


def create_app(team: Team | None = None) -> FastAPI:
    backend = Backend(team)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.backend = backend
        if await backend.try_connect() is None:
            print(f"Could not reach the MCP server at {config.MCP_URL} ({backend.connect_error}). Start it with: {START_COMMAND}", flush=True)
            print("The API is up; every route except /health answers 503 until the server is reachable.", flush=True)
        yield
        await backend.close()

    app = FastAPI(
        title="Campus Customs API",
        version="0.1",
        description="The agent team's back end: the board, the runs, the timeline, the human's approvals, the cash, and the reset. Every shop fact comes from the MCP server.",
        lifespan=lifespan,
    )
    # The Vite dashboard runs on localhost:5173; the regex also admits any other local port, so a
    # `vite preview` or a second dev server on this machine can call the API too.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DASHBOARD_ORIGINS,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_backend(request: Request) -> Backend:
        return request.app.state.backend

    async def get_team(backend: Backend = Depends(get_backend)) -> Team:
        try:
            return await backend.connect()
        except Exception as exc:
            raise HTTPException(503, f"The MCP server at {config.MCP_URL} is not reachable ({exc}). Start it with: {START_COMMAND}") from exc

    async def call(team: Team, tool: str, arguments: dict[str, Any] | None = None, *, missing: int = 404) -> Any:
        """Call an MCP tool; a refused read is a 404 (or `missing`), a list comes back unwrapped."""
        result = unwrap(await team.toolset.call(tool, arguments))
        if is_error(result):
            raise HTTPException(missing, result["error"])
        return result

    async def find_approval(team: Team, approval_id: int) -> dict[str, Any]:
        for approval in await call(team, "list_approvals"):
            if approval["id"] == approval_id:
                return approval
        raise HTTPException(404, f"Approval {approval_id} does not exist.")

    def approval_label(approval: dict[str, Any]) -> str:
        """'rent for lease 1, $2,400.00' / 'invoice 501, $840.00' / 'price override' for the re-work prompt."""
        kind, ref, amount = approval["kind"], approval.get("ref_id"), float(approval.get("amount") or 0)
        head = {"rent": f"rent for lease {ref}", "invoice": f"invoice {ref}", "purchase_order": f"purchase order {ref}"}.get(kind, kind.replace("_", " "))
        return f"{head}, ${amount:,.2f}" if amount > 0 else head

    def checking_balance(cash: dict[str, Any]) -> float:
        for account in cash["accounts"]:
            if account["name"] == "checking":
                return float(account["balance"])
        raise HTTPException(500, "cash_accounts has no 'checking' row.")

    # ---- health ----

    @app.get("/health")
    async def health(backend: Backend = Depends(get_backend)) -> dict[str, Any]:
        team = await backend.try_connect()
        shop = await team.toolset.call("get_today") if team is not None else None
        return {
            "ok": team is not None,
            "model": config.MODEL_NAME,
            "mcp_url": config.MCP_URL,
            "mcp_connected": team is not None,
            "mcp_error": backend.connect_error,
            "shop": shop,
            "busy": backend.current,
            "jobs": len(backend.jobs),
        }

    # ---- the board ----

    @app.get("/tickets", response_model=list[TicketSummary])
    async def tickets(status: str | None = None, team: Team = Depends(get_team)) -> list[TicketSummary]:
        rows = await call(team, "list_tickets", {"status": status}, missing=400)
        return [TicketSummary(open=row["status"] != "resolved", **row) for row in rows]

    @app.get("/tickets/{ticket_id}")
    async def ticket(ticket_id: int, team: Team = Depends(get_team)) -> dict[str, Any]:
        return await call(team, "get_ticket", {"ticket_id": ticket_id})

    # ---- running the team ----

    @app.post("/tickets/{ticket_id}/run", response_model=JobInfo, status_code=202)
    async def run_ticket(ticket_id: int, wait: bool = False, backend: Backend = Depends(get_backend), team: Team = Depends(get_team)) -> JobInfo:
        """The Boss works one ticket: reads it, delegates, makes the final call. Re-running a ticket is allowed (after an approval, say)."""
        await call(team, "get_ticket", {"ticket_id": ticket_id})
        job = backend.start_job("ticket", ticket_id, lambda: team.work_ticket(ticket_id))
        return await backend.finish(job) if wait else job

    @app.post("/board/run", response_model=JobInfo, status_code=202)
    async def run_board(wait: bool = False, backend: Backend = Depends(get_backend), team: Team = Depends(get_team)) -> JobInfo:
        """Triage, then every unresolved ticket in priority order."""
        job = backend.start_job("board", None, team.run_board)
        return await backend.finish(job) if wait else job

    @app.get("/runs", response_model=list[JobInfo])
    async def runs(limit: int = Query(20, ge=1, le=200), backend: Backend = Depends(get_backend)) -> list[JobInfo]:
        return list(reversed(list(backend.jobs.values())))[:limit]

    @app.get("/runs/{job_id}", response_model=JobInfo)
    async def run(job_id: str, backend: Backend = Depends(get_backend)) -> JobInfo:
        if job_id not in backend.jobs:
            raise HTTPException(404, f"No job {job_id}.")
        return backend.jobs[job_id]

    # ---- the timeline ----

    @app.get("/events", response_model=EventsPage)
    async def events(
        since: int | None = Query(None, description="only events with an id above this one (poll with the last_id you were given)"),
        limit: int = Query(100, ge=1, le=1000),
        ticket_id: int | None = None,
        team: Team = Depends(get_team),
    ) -> EventsPage:
        """What happened, oldest first: runs, delegations and replies, every tool call with its arguments, notes, approvals, payments, decisions."""
        if since is None:
            rows = await call(team, "list_ticket_events", {"ticket_id": ticket_id, "since_id": None, "limit": 1000})
            rows = rows[-limit:]
        else:
            rows = await call(team, "list_ticket_events", {"ticket_id": ticket_id, "since_id": since, "limit": limit})
        return EventsPage(events=rows, last_id=rows[-1]["id"] if rows else since)

    # ---- money ----

    @app.get("/cash", response_model=CashView)
    async def cash(team: Team = Depends(get_team)) -> CashView:
        result = await call(team, "get_cash")
        return CashView(checking=checking_balance(result), accounts=result["accounts"], total=float(result["total"]))

    @app.get("/approvals")
    async def approvals(status: str | None = None, team: Team = Depends(get_team)) -> list[dict[str, Any]]:
        return await call(team, "list_approvals", {"status": status}, missing=400)

    @app.post("/approvals/{approval_id}/approve")
    async def approve(
        approval_id: int,
        body: DecisionRequest | None = None,
        backend: Backend = Depends(get_backend),
        team: Team = Depends(get_team),
    ) -> dict[str, Any]:
        """The human approves. Records the decision, then pays (the only place cash changes); a
        price override carries no payment. A payment the rules refuse (not enough cash, vendor
        still owed) comes back in `refused`, with the approval left approved so it can be retried.
        With rework (the default) the Boss then re-works the ticket in the background."""
        body = body or DecisionRequest()
        approval = await find_approval(team, approval_id)
        decision: Any = None
        if approval["status"] == "pending":
            decision = await team.decide(approval_id, "approved", body.by, body.note)
            if is_error(decision):
                raise HTTPException(409, decision["error"])
        elif approval["status"] == "approved":
            decision = {"note": f"Approval {approval_id} was already approved by {approval['decided_by']}; paying it now."}
        else:
            raise HTTPException(409, f"Approval {approval_id} is {approval['status']}; nothing to approve.")

        payment: Any = None
        refused: str | None = None
        if approval["kind"] != "price_override" and (approval["amount"] or 0) > 0:
            paid = await team.pay(approval_id, body.by)
            if is_error(paid):
                refused = paid["error"]
            else:
                payment = paid

        checking = checking_balance(await call(team, "get_cash"))
        rework = None
        if body.rework and approval["ticket_id"] is not None and backend.current is None:
            ticket_id = approval["ticket_id"]
            what = f"Approval {approval_id} ({approval_label(approval)}) was approved by {body.by}"
            if payment is not None:
                what += f" and paid: payment {payment.get('id')} of ${float(payment.get('amount', 0)):,.2f}; checking is now ${checking:,.2f}."
            elif refused:
                what += f", but the payment was refused: {refused}"
            else:
                what += "; it carries no payment."
            rework = backend.start_job("rework", ticket_id, lambda: team.work_ticket(ticket_id, what))

        return {
            "approval": await find_approval(team, approval_id),
            "decision": decision,
            "payment": payment,
            "refused": refused,
            "checking": checking,
            "rework": rework,
        }

    @app.post("/approvals/{approval_id}/reject")
    async def reject(
        approval_id: int,
        body: DecisionRequest | None = None,
        backend: Backend = Depends(get_backend),
        team: Team = Depends(get_team),
    ) -> dict[str, Any]:
        """The human rejects: no money moves, a purchase order goes back to draft, the ticket back to
        in_progress. With rework (the default) the Boss re-works the ticket with the answer."""
        body = body or DecisionRequest()
        approval = await find_approval(team, approval_id)
        if approval["status"] != "pending":
            raise HTTPException(409, f"Approval {approval_id} is {approval['status']}; only a pending approval can be rejected.")
        decision = await team.decide(approval_id, "rejected", body.by, body.note)
        if is_error(decision):
            raise HTTPException(409, decision["error"])
        rework = None
        if body.rework and approval["ticket_id"] is not None and backend.current is None:
            ticket_id = approval["ticket_id"]
            what = f"Approval {approval_id} ({approval_label(approval)}) was rejected by {body.by}"
            what += f" with the note: {body.note}" if body.note else "; no money moved and the ticket is back in progress."
            rework = backend.start_job("rework", ticket_id, lambda: team.work_ticket(ticket_id, what))
        return {"approval": await find_approval(team, approval_id), "decision": decision, "rework": rework}

    @app.get("/drafts")
    async def drafts(ticket_id: int | None = None, team: Team = Depends(get_team)) -> list[dict[str, Any]]:
        return await call(team, "list_drafts", {"ticket_id": ticket_id})

    # ---- a fresh run ----

    @app.post("/reset")
    async def reset(backend: Backend = Depends(get_backend)) -> dict[str, Any]:
        """Copy data/campus_customs.db over data/campus_customs_new.db (shop rule 8). Refused while
        the team is working. The original is never written; the audit trail records the reset."""
        backend.refuse_if_busy("reset the shop")
        try:
            result = reset_working_copy()
        except (FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(500, str(exc)) from exc
        backend.audit.human("reset", target=result["target"], counts=result["counts"], checking_balance=result["checking_balance"])
        backend.jobs.clear()
        backend.tasks.clear()
        if backend.team is not None:
            backend.team.events.clear()
        return result

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
