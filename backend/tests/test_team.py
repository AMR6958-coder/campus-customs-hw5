"""Offline tests for the agent team: no gateway calls, no running server.

Each test spawns the MCP server over stdio against a temporary copy of the
original database, and drives the agents with PydanticAI's TestModel and
FunctionModel (scripted responses) instead of gpt-6-luna. What is tested is
the plumbing the live run depends on: prompts load, the human-only tools are
hidden, delegation guards hold, a delegation round-trips and is logged on both
sides, tool calls are logged with the agent's name, a refusal comes back as a
sentence, and the human's approve-and-pay path works.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from backend import config
from backend.agents.base import delegation_problem, load_prompt
from backend.audit_trail import AuditTrail, read_trail
from backend.mcp_toolset import MCPToolset
from backend.models import AgentName, Budget, TeamDeps
from backend.team import Team, unwrap
from mcp_server import db

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def work_db(tmp_path, monkeypatch):
    target = tmp_path / "campus_customs_test.db"
    shutil.copyfile(db.ORIGINAL_DB_PATH, target)
    monkeypatch.setenv("CAMPUS_DB_PATH", str(target))
    before = sha256(db.ORIGINAL_DB_PATH)
    yield target
    assert sha256(db.ORIGINAL_DB_PATH) == before, "the original database was modified"


def make_team(work_db: Path, audit_path: Path | None = None) -> Team:
    toolset = MCPToolset(
        command=sys.executable,
        args=["-m", "mcp_server.server", "--stdio"],
        env={"CAMPUS_DB_PATH": str(work_db)},
        cwd=str(PROJECT_ROOT),
    )
    audit = AuditTrail(audit_path or work_db.parent / "audit_trail_test.json")
    return Team(toolset=toolset, model=TestModel(call_tools=[]), audit=audit)


def _after_a_tool_return(messages: list[ModelMessage]) -> bool:
    return any(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)


# --------------------------------------------------------------------------
# Prompts and guards (no server needed)
# --------------------------------------------------------------------------


def test_every_agent_has_its_own_prompt_plus_the_shared_rules():
    for name in AgentName:
        text = load_prompt(name)
        assert text.startswith("# You are"), name
        assert "The shop's rules" in text and "ask_colleague" in text, name
    assert "Triage" in load_prompt(AgentName.boss)
    assert "never move it" in load_prompt(AgentName.accounting)


def test_delegation_guards_stop_self_calls_cycles_depth_and_budget():
    deps = TeamDeps(team=None, agent=AgentName.boss, ticket_id=101, chain=(AgentName.boss,), budget=Budget(limit=2))
    assert delegation_problem(deps, AgentName.boss) == "an agent cannot ask itself"
    assert delegation_problem(deps, AgentName.inventory) is None

    child = deps.child(AgentName.inventory)
    assert child.depth == 1 and child.chain == (AgentName.boss, AgentName.inventory)
    assert "already in this chain" in delegation_problem(child, AgentName.boss)
    assert delegation_problem(child, AgentName.accounting) is None  # any other colleague is fine

    deepest = child.child(AgentName.accounting).child(AgentName.facilities)
    assert deepest.depth == config.MAX_DELEGATION_DEPTH
    assert "depth limit" in delegation_problem(deepest, AgentName.customer_service)

    deps.budget.used = 2
    assert "budget" in delegation_problem(deps, AgentName.accounting)
    assert child.budget is deps.budget  # one budget shared by the whole chain


# --------------------------------------------------------------------------
# With the server over stdio
# --------------------------------------------------------------------------


def test_agents_never_see_pay_decide_approval_or_log_event(work_db):
    async def go():
        team = make_team(work_db)
        async with team:
            every_tool = set(team.toolset.tool_names)
            visible = set((await team.agent_toolset.get_tools(None)).keys())
        return every_tool, visible

    every_tool, visible = asyncio.run(go())
    assert config.HIDDEN_FROM_AGENTS <= every_tool
    assert not (config.HIDDEN_FROM_AGENTS & visible)
    assert {"get_ticket", "request_approval", "create_purchase_order", "draft_customer_message", "ask_colleague"} - {"ask_colleague"} <= visible
    assert len(visible) == len(every_tool) - len(config.HIDDEN_FROM_AGENTS)


def test_boss_delegates_to_inventory_and_both_sides_are_logged(work_db):
    def boss_script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _after_a_tool_return(messages):
            # The Boss's output is a BossDecision; "blocked" needs no matching ticket status.
            decision = {"ticket_id": 101, "outcome": "blocked", "summary": "Inventory says the S shelf is empty; done."}
            return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args=decision)])
        return ModelResponse(
            parts=[ToolCallPart(tool_name="ask_colleague", args={"colleague": "inventory", "request": "Ticket 101: how many CC-TEE-WHITE S are on hand?"})]
        )

    inventory_model = TestModel(call_tools=[], custom_output_text="Inventory: CC-TEE-WHITE S has 0 on hand, 1 requested, short by 1.")

    async def go():
        team = make_team(work_db)
        async with team:
            boss, inventory = team.agents[AgentName.boss], team.agents[AgentName.inventory]
            with boss.override(model=FunctionModel(boss_script)), inventory.override(model=inventory_model):
                result = await boss.run("Work ticket 101", deps=team.deps_for(101))
            logged = unwrap(await team.toolset.call("list_ticket_events", {"ticket_id": 101}))
        return result.output, [e.kind for e in team.events], logged

    output, kinds, logged = asyncio.run(go())
    assert output.outcome == "blocked" and output.summary == "Inventory says the S shelf is empty; done."
    assert kinds == ["delegate", "delegate_reply"]
    assert [e["kind"] for e in logged] == ["delegate", "delegate_reply"]
    assert logged[0]["agent"] == "boss" and logged[0]["data"] == {"to": "inventory", "depth": 1, "chain": ["boss", "inventory"]}
    assert logged[1]["agent"] == "inventory" and "short by 1" in logged[1]["message"]


def test_tool_calls_are_logged_with_the_agent_name(work_db):
    def inventory_script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _after_a_tool_return(messages):
            return ModelResponse(parts=[TextPart("checked")])
        return ModelResponse(parts=[ToolCallPart(tool_name="get_stock", args={"sku": "CC-TEE-WHITE", "size": "S"})])

    async def go():
        team = make_team(work_db)
        async with team:
            inventory = team.agents[AgentName.inventory]
            with inventory.override(model=FunctionModel(inventory_script)):
                result = await inventory.run("Check stock", deps=team.deps_for(101).child(AgentName.inventory))
            logged = unwrap(await team.toolset.call("list_ticket_events", {"ticket_id": 101}))
        return result.output, logged

    output, logged = asyncio.run(go())
    assert output == "checked"
    assert len(logged) == 1
    assert logged[0]["kind"] == "tool" and logged[0]["agent"] == "inventory"
    assert logged[0]["data"]["tool"] == "get_stock" and logged[0]["data"]["args"] == {"sku": "CC-TEE-WHITE", "size": "S"}
    assert '"qty": 0' in logged[0]["data"]["result"]


def test_a_refusal_reaches_the_model_as_a_sentence_not_an_exception(work_db):
    def inventory_script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _after_a_tool_return(messages):
            return ModelResponse(parts=[TextPart("blocked by the invoice")])
        return ModelResponse(
            parts=[ToolCallPart(tool_name="create_purchase_order", args={"vendor_id": 1, "sku": "CC-HOOD-NAVY", "size": "M", "qty": 20, "agent": "inventory", "ticket_id": 103})]
        )

    async def go():
        team = make_team(work_db)
        async with team:
            inventory = team.agents[AgentName.inventory]
            with inventory.override(model=FunctionModel(inventory_script)):
                result = await inventory.run("Order hoodies", deps=team.deps_for(103).child(AgentName.inventory))
            orders = unwrap(await team.toolset.call("list_purchase_orders"))
            logged = unwrap(await team.toolset.call("list_ticket_events", {"ticket_id": 103}))
        return result.output, orders, logged

    output, orders, logged = asyncio.run(go())
    assert output == "blocked by the invoice"
    assert orders == []
    assert "will not ship while invoice 501" in logged[0]["data"]["result"]


def test_every_agent_run_and_step_lands_on_the_audit_trail_and_the_file_is_never_wiped(work_db, tmp_path):
    trail_path = tmp_path / "audit_trail.json"
    trail_path.write_text('{"ts": "earlier", "record": "human", "action": "reset"}\n', encoding="utf-8")

    def boss_script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _after_a_tool_return(messages):
            # work_ticket asks for a BossDecision, which the model delivers as the final_result tool.
            # "blocked" is the one outcome the decision validator accepts without a matching ticket status.
            decision = {"ticket_id": 102, "outcome": "blocked", "summary": "Rent is due in 2 days; the approval has not been requested yet.", "delegated_to": ["facilities"]}
            return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args=decision)])
        return ModelResponse(parts=[ToolCallPart(tool_name="ask_colleague", args={"colleague": "facilities", "request": "Ticket 102: when is rent due?"})])

    def facilities_script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _after_a_tool_return(messages):
            return ModelResponse(parts=[TextPart("Rent $2,400 due 2026-09-02, in 2 days.")])
        return ModelResponse(parts=[ToolCallPart(tool_name="get_lease", args={"lease_id": 1})])

    async def go():
        team = make_team(work_db, trail_path)
        async with team:
            boss, facilities = team.agents[AgentName.boss], team.agents[AgentName.facilities]
            with boss.override(model=FunctionModel(boss_script)), facilities.override(model=FunctionModel(facilities_script)):
                await team.work_ticket(102)
            await team.decide(999, "approved", "Store Manager")  # refused by the server, still audited

    asyncio.run(go())
    records = read_trail(trail_path)
    assert records[0] == {"ts": "earlier", "record": "human", "action": "reset"}  # appended, not wiped
    kinds = [(r["record"], r.get("agent")) for r in records[1:]]
    assert kinds == [
        ("run_started", "boss"),
        ("step", "boss"),  # the Boss's first response: the ask_colleague call
        ("run_started", "facilities"),
        ("step", "facilities"),  # get_lease call
        ("step", "facilities"),  # the text report, after the tool return
        ("run_finished", "facilities"),
        ("step", "boss"),  # the Boss's final_result call, after the delegation returned
        ("run_finished", "boss"),
        ("human", None),
    ]
    boss_start, boss_step1, fac_start, fac_step1, fac_step2, fac_done, boss_step2, boss_done, human = records[1:]
    assert boss_start["mode"] == "ticket" and boss_start["ticket_id"] == 102 and boss_start["chain"] == ["boss"]
    assert [f["file"] for f in boss_start["prompt_files"]] == ["boss.md", "shared.md"]
    assert boss_step1["step"] == 1 and boss_step1["request"]["parts"][0]["part"] == "user_prompt"
    assert boss_step1["response"]["parts"][0] == {"part": "tool_call", "tool": "ask_colleague", "tool_call_id": boss_step1["response"]["parts"][0]["tool_call_id"], "args": {"colleague": "facilities", "request": "Ticket 102: when is rent due?"}}
    assert fac_start["parent_run_id"] == boss_start["run_id"] and fac_start["chain"] == ["boss", "facilities"] and fac_start["depth"] == 1
    assert fac_step2["request"]["parts"][0]["part"] == "tool_return" and fac_step2["request"]["parts"][0]["tool"] == "get_lease"
    assert '"next_due": "2026-09-02"' in json.dumps(fac_step2["request"]["parts"][0]["content"])
    assert fac_done["outcome"] == "ok" and fac_done["steps"] == 2 and fac_done["output"].startswith("Rent $2,400")
    assert boss_step2["request"]["parts"][0]["tool"] == "ask_colleague" and "Rent $2,400" in boss_step2["request"]["parts"][0]["content"]
    assert boss_done["outcome"] == "ok" and boss_done["steps"] == 2 and boss_done["output"]["outcome"] in {"resolved", "waiting_approval", "blocked"}
    assert human["action"] == "decide_approval" and "does not exist" in human["result"]["error"]
    assert boss_done["run_id"] == boss_start["run_id"] and len(records) == 10


def test_the_boss_cannot_claim_resolved_until_resolve_ticket_was_called(work_db):
    """The decision validator: a 'resolved' decision while the ticket is not resolved is sent back
    with a retry; the Boss then calls resolve_ticket and the decision is accepted."""

    def boss_script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        parts = [part for message in messages for part in message.parts]
        claim = ModelResponse(parts=[ToolCallPart(tool_name="final_result", args={"ticket_id": 102, "outcome": "resolved", "summary": "Rent paid; done."})])
        if any(isinstance(p, ToolReturnPart) and p.tool_name == "resolve_ticket" for p in parts):
            return claim  # second claim, now true
        if any(isinstance(p, RetryPromptPart) for p in parts):
            return ModelResponse(parts=[ToolCallPart(tool_name="resolve_ticket", args={"ticket_id": 102, "resolution": "Rent of $2,400 for lease 1 is paid; next due 2026-10-02.", "agent": "boss"})])
        return claim  # first claim: nothing has been resolved yet

    async def go():
        team = make_team(work_db)
        async with team:
            with team.boss.override(model=FunctionModel(boss_script)):
                decision = await team.work_ticket(102)
            ticket = await team.toolset.call("get_ticket", {"ticket_id": 102})
            events = unwrap(await team.toolset.call("list_ticket_events", {"ticket_id": 102}))
        return decision, ticket, events

    decision, ticket, events = asyncio.run(go())
    assert decision.outcome == "resolved" and decision.ticket_id == 102
    assert ticket["status"] == "resolved" and ticket["resolution"].startswith("Rent of $2,400")
    kinds = [(e["agent"], e["kind"]) for e in events]
    retry = kinds.index(("boss", "retry"))
    resolve = next(i for i, e in enumerate(events) if e["kind"] == "tool" and e["data"]["tool"] == "resolve_ticket")
    assert retry < resolve < kinds.index(("boss", "decision"))
    assert "still 'open'" in events[retry]["message"]


def test_the_human_path_approves_and_pays_through_the_hidden_tools(work_db):
    async def go():
        team = make_team(work_db)
        async with team:
            approval = await team.toolset.call(
                "request_approval", {"kind": "invoice", "ref_id": 501, "ticket_id": 101, "rationale": "overdue", "agent": "accounting"}
            )
            refused = await team.pay(approval["id"], "Store Manager")
            payment = await team.approve_and_pay(approval["id"], "Store Manager", note="ok")
            cash = await team.toolset.call("get_cash")
        return refused, payment, cash

    refused, payment, cash = asyncio.run(go())
    assert "a human must approve it" in refused["error"]
    assert payment["amount"] == 840 and payment["settled"] == "invoice 501 marked paid"
    assert cash["accounts"][0]["balance"] == 2560
