"""Offline tests for the API: FastAPI's TestClient over a Team on stdio against a temporary copy
of the original database, with PydanticAI's TestModel in place of gpt-6-luna. No gateway calls,
no running server. What is tested is each route's contract: the board and its `open` flag, one
ticket with links, a run as a background job and with wait=true, the timeline feed and its
since/last_id polling, the cash view, the human's approve (which pays) and reject, the refusals
(already decided, not enough cash), the busy guard, and the reset.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from backend.audit_trail import AuditTrail
from backend.main import create_app
from backend.mcp_toolset import MCPToolset
from backend.models import JobInfo
from backend.team import Team
from mcp_server import db

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def work_db(tmp_path, monkeypatch):
    target = tmp_path / "campus_customs_api_test.db"
    shutil.copyfile(db.ORIGINAL_DB_PATH, target)
    monkeypatch.setenv("CAMPUS_DB_PATH", str(target))
    before = sha256(db.ORIGINAL_DB_PATH)
    yield target
    assert sha256(db.ORIGINAL_DB_PATH) == before, "the original database was modified"


@pytest.fixture
def client(work_db):
    toolset = MCPToolset(
        command=sys.executable,
        args=["-m", "mcp_server.server", "--stdio"],
        env={"CAMPUS_DB_PATH": str(work_db)},
        cwd=str(PROJECT_ROOT),
    )
    team = Team(toolset=toolset, model=TestModel(call_tools=[]), audit=AuditTrail(work_db.parent / "audit_trail_api_test.json"))
    with TestClient(create_app(team=team)) as client:
        yield client


def mcp(client: TestClient, tool: str, arguments: dict | None = None):
    """Call an MCP tool through the app's own connection (for setting up a test)."""
    team = client.app.state.backend.team
    return client.portal.call(team.toolset.call, tool, arguments)


def test_health_board_and_one_ticket(client):
    health = client.get("/health").json()
    assert health["ok"] is True and health["mcp_connected"] is True
    assert health["model"] == "gpt-6-luna"
    assert health["shop"]["date_today"] == "2026-08-31"
    assert health["busy"] is None

    board = client.get("/tickets").json()
    assert sorted(t["id"] for t in board) == [101, 102, 103]
    assert all(t["status"] == "open" and t["open"] is True for t in board)

    ticket = client.get("/tickets/102").json()
    assert ticket["links"]["lease"]["id"] == 1 and ticket["links"]["lease"]["days_until_due"] == 2
    assert client.get("/tickets/999").status_code == 404


def test_cash_is_the_checking_balance(client):
    cash = client.get("/cash").json()
    assert cash["checking"] == 3400 and cash["total"] == 3400
    assert cash["accounts"][0]["name"] == "checking"


def test_run_ticket_is_a_job_and_writes_the_timeline(client):
    assert client.get("/events").json() == {"events": [], "last_id": None}

    response = client.post("/tickets/102/run?wait=true")
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["kind"] == "ticket" and job["ticket_id"] == 102 and job["status"] == "done", job
    assert job["result"]["ticket_id"] is not None and job["result"]["outcome"] in {"resolved", "waiting_approval", "blocked"}
    assert client.get(f"/runs/{job['id']}").json()["status"] == "done"
    assert [j["id"] for j in client.get("/runs").json()] == [job["id"]]

    page = client.get("/events").json()
    kinds = [e["kind"] for e in page["events"]]
    assert "run" in kinds and "decision" in kinds
    assert all(e["agent"] == "boss" for e in page["events"])
    assert page["last_id"] == page["events"][-1]["id"]
    assert client.get("/events", params={"ticket_id": 102}).json()["events"] == page["events"]
    assert client.get("/events", params={"since": page["last_id"]}).json() == {"events": [], "last_id": page["last_id"]}
    assert client.post("/tickets/999/run").status_code == 404


def test_approve_pays_and_the_refusals_hold(client):
    mcp(client, "request_approval", {"kind": "rent", "ref_id": 1, "ticket_id": 102, "rationale": "rent due in 2 days", "agent": "accounting"})
    mcp(client, "request_approval", {"kind": "invoice", "ref_id": 501, "ticket_id": 101, "rationale": "vendor blocked", "agent": "accounting"})
    pending = client.get("/approvals", params={"status": "pending"}).json()
    assert [a["id"] for a in pending] == [1, 2]

    # Approve 1: the decision is recorded and the rent is paid; cash falls; the lease moves a month.
    result = client.post("/approvals/1/approve", json={"by": "Store Manager", "note": "ok", "rework": False}).json()
    assert result["approval"]["status"] == "executed" and result["approval"]["decided_by"] == "Store Manager"
    assert result["payment"]["amount"] == 2400 and result["refused"] is None
    assert result["checking"] == 1000 and result["rework"] is None
    assert client.get("/cash").json()["checking"] == 1000
    assert mcp(client, "get_lease", {"lease_id": 1})["next_due"] == "2026-10-02"
    assert client.post("/approvals/1/approve", json={"rework": False}).status_code == 409

    # Reject 2: no money moves and the ticket goes back to in_progress.
    result = client.post("/approvals/2/reject", json={"by": "Store Manager", "note": "wait", "rework": False}).json()
    assert result["approval"]["status"] == "rejected"
    assert client.get("/cash").json()["checking"] == 1000
    assert client.post("/approvals/2/approve", json={"rework": False}).status_code == 409
    assert client.post("/approvals/2/reject", json={"rework": False}).status_code == 409
    assert client.post("/approvals/9/approve").status_code == 404

    # Approve 3, a second rent request with $1,000 left: approved, but the pay tool refuses.
    mcp(client, "request_approval", {"kind": "rent", "ref_id": 1, "ticket_id": 102, "rationale": "next month early", "agent": "accounting"})
    result = client.post("/approvals/3/approve", json={"rework": False}).json()
    assert result["payment"] is None and "Not enough cash" in result["refused"]
    assert result["approval"]["status"] == "approved" and result["checking"] == 1000

    timeline = [e["kind"] for e in client.get("/events").json()["events"]]
    assert timeline.count("paid") == 1 and "approved" in timeline and "rejected" in timeline


def test_busy_guard_refuses_a_second_run_and_a_reset(client):
    backend = client.app.state.backend
    backend.jobs["fake"] = JobInfo(id="fake", kind="ticket", ticket_id=101, started_at=datetime.now(timezone.utc))
    assert client.post("/tickets/102/run").status_code == 409
    assert client.post("/board/run").status_code == 409
    assert client.post("/reset").status_code == 409
    assert client.get("/health").json()["busy"]["id"] == "fake"
    backend.jobs["fake"].status = "done"
    assert client.get("/health").json()["busy"] is None


def test_reset_restores_the_seed(client, work_db):
    mcp(client, "request_approval", {"kind": "rent", "ref_id": 1, "ticket_id": 102, "rationale": "rent", "agent": "accounting"})
    client.post("/approvals/1/approve", json={"rework": False})
    assert client.get("/cash").json()["checking"] == 1000

    result = client.post("/reset").json()
    assert result["counts"] == {"tickets": 3, "payments": 0, "approvals": 0, "purchase_orders": 0, "drafts": 0}
    assert result["checking_balance"] == 3400 and Path(result["target"]) == work_db
    assert client.get("/cash").json()["checking"] == 3400
    assert client.get("/runs").json() == []
    events = client.get("/events").json()["events"]
    assert [(e["agent"], e["kind"]) for e in events] == [("system", "reset")]
