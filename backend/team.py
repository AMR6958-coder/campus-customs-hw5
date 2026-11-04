"""The Team: five agents, one MCP connection, delegation, and the run loop.

- Builds the five agents from ``backend/agents`` on one shared toolset that
  hides the human-only tools (pay, decide_approval) and the back end's own
  log_event from every agent.
- ``delegate`` is what ``ask_colleague`` calls: it runs the colleague's agent
  with a child context (depth + 1, chain + colleague, same budget) and logs
  both the request and the reply to the activity feed.
- ``triage`` and ``work_ticket`` run the Boss; ``run_board`` does both for
  every open ticket in priority order.
- ``decide`` / ``pay`` / ``approve_and_pay`` are the human's path, used by the
  console runner now and the API next step. They are the only callers of the
  hidden tools.

Every tool call an agent makes and every delegation is written to the
``ticket_events`` table through log_event, so the dashboard can show the team
at work and the record survives the run.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.run import AgentRunResult
from pydantic_ai.usage import RunUsage, UsageLimits

from backend import config
from backend.agents import AGENT_MODULES
from backend.agents import boss as boss_module
from backend.audit_trail import AuditTrail, new_run_id
from backend.mcp_toolset import MCPToolset
from backend.models import AgentName, BossDecision, Budget, RunEvent, TeamDeps, TriagePlan

Listener = Callable[[RunEvent], None]


def unwrap(result: Any) -> Any:
    """FastMCP wraps a list result as {"result": [...]}; give back the list."""
    if isinstance(result, dict) and set(result) == {"result"}:
        return result["result"]
    return result


class Team:
    def __init__(self, toolset: MCPToolset | None = None, *, model: Model | None = None, audit: AuditTrail | None = None) -> None:
        self.toolset = toolset or MCPToolset(config.MCP_URL)
        self.toolset.on_call = self._on_tool_call
        self.audit = audit or AuditTrail()
        self.agent_toolset = self.toolset.filtered(lambda ctx, tool_def: tool_def.name not in config.HIDDEN_FROM_AGENTS)
        self.agents: dict[AgentName, Agent[TeamDeps, Any]] = {
            name: module.build(self.agent_toolset, model) for name, module in AGENT_MODULES.items()
        }
        # The Boss's second job, triage, is its own Agent: PydanticAI ties the output type and its
        # validators to the agent, and the ticket agent's decision validator must not apply here.
        self.triage_agent: Agent[TeamDeps, Any] = boss_module.build_triage(self.agent_toolset, model)
        self.events: list[RunEvent] = []
        self.listeners: list[Listener] = []
        self.usage_limits = UsageLimits(
            request_limit=config.REQUEST_LIMIT_PER_TICKET,
            tool_calls_limit=config.TOOL_CALLS_LIMIT_PER_TICKET,
        )

    @property
    def boss(self) -> Agent[TeamDeps, Any]:
        return self.agents[AgentName.boss]

    async def __aenter__(self) -> Team:
        await self.toolset.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.toolset.__aexit__(*exc)

    # ---- the activity feed -------------------------------------------------

    async def log(
        self,
        kind: str,
        message: str,
        agent: AgentName | str = "system",
        ticket_id: int | None = None,
        data: dict[str, Any] | None = None,
        *,
        persist: bool = True,
    ) -> RunEvent:
        event = RunEvent(kind=kind, agent=str(agent), message=message, ticket_id=ticket_id, data=data)
        self.events.append(event)
        for listener in self.listeners:
            listener(event)
        if persist:
            await self.toolset.call(
                "log_event",
                {"kind": kind, "message": message, "agent": str(agent), "ticket_id": ticket_id, "data": data},
            )
        return event

    async def _on_tool_call(self, deps: Any, name: str, args: dict[str, Any], result: Any) -> None:
        agent = deps.agent if isinstance(deps, TeamDeps) else "system"
        ticket_id = deps.ticket_id if isinstance(deps, TeamDeps) else None
        preview = json.dumps(result, default=str)
        if len(preview) > 300:
            preview = preview[:300] + "..."
        arg_text = ", ".join(f"{key}={value!r}" for key, value in args.items())
        await self.log(
            "tool",
            f"{agent} called {name}({arg_text})",
            agent,
            ticket_id,
            {"tool": name, "args": args, "result": preview},
        )

    # ---- running one agent, with every step on the audit trail -------------

    async def run_agent(
        self,
        deps: TeamDeps,
        prompt: str,
        *,
        mode: str,
        output_type: Any = None,
        usage: RunUsage | None = None,
        agent: Agent[TeamDeps, Any] | None = None,
    ) -> AgentRunResult[Any]:
        """Run `deps.agent` (or the given agent object) on `prompt`, writing run_started, one step per model response, and run_finished."""
        agent = agent or self.agents[deps.agent]
        deps.run_id = run_id = new_run_id()
        started = time.monotonic()
        self.audit.run_started(
            run_id=run_id,
            agent=str(deps.agent),
            mode=mode,
            ticket_id=deps.ticket_id,
            depth=deps.depth,
            chain=[str(a) for a in deps.chain],
            parent_run_id=deps.parent_run_id,
            prompt=prompt,
        )
        steps, pending_request = 0, None
        try:
            async with agent.iter(prompt, deps=deps, output_type=output_type, usage=usage, usage_limits=self.usage_limits) as agent_run:
                async for node in agent_run:
                    if Agent.is_model_request_node(node):
                        pending_request = node.request
                    elif Agent.is_call_tools_node(node):
                        steps += 1
                        self.audit.step(run_id=run_id, agent=str(deps.agent), ticket_id=deps.ticket_id, step=steps, request=pending_request, response=node.model_response)
            result = agent_run.result
            assert result is not None
        except BaseException as exc:
            self.audit.run_finished(
                run_id=run_id, agent=str(deps.agent), ticket_id=deps.ticket_id, outcome="error", output=None,
                steps=steps, usage=usage, duration_ms=int((time.monotonic() - started) * 1000), error=f"{type(exc).__name__}: {exc}",
            )
            raise
        output = result.output
        self.audit.run_finished(
            run_id=run_id, agent=str(deps.agent), ticket_id=deps.ticket_id, outcome="ok",
            output=output if isinstance(output, str) else output.model_dump(mode="json"),
            steps=steps, usage=result.usage, duration_ms=int((time.monotonic() - started) * 1000),
        )
        return result

    # ---- delegation (full connectivity) ------------------------------------

    async def delegate(self, deps: TeamDeps, colleague: AgentName, request: str, usage: RunUsage | None) -> str:
        """Run a colleague on a request from `deps.agent` and return their report."""
        deps.budget.used += 1
        child = deps.child(colleague)
        chain = " > ".join(child.chain)
        await self.log(
            "delegate",
            f"{deps.agent} asked {colleague}: {request}",
            deps.agent,
            deps.ticket_id,
            {"to": str(colleague), "depth": child.depth, "chain": [str(a) for a in child.chain]},
        )
        about = f" about ticket {deps.ticket_id}" if deps.ticket_id is not None else ""
        prompt = f"Request from {deps.agent}{about} (chain: {chain}):\n\n{request}"
        try:
            result = await self.run_agent(child, prompt, mode="delegation", usage=usage)
            output = result.output
            reply = output if isinstance(output, str) else output.model_dump_json()
        except (UsageLimitExceeded, UnexpectedModelBehavior) as exc:
            reply = f"{colleague} could not finish: {exc}"
            await self.log("error", reply, colleague, deps.ticket_id)
        await self.log(
            "delegate_reply",
            f"{colleague} replied to {deps.agent}: {reply}",
            colleague,
            deps.ticket_id,
            {"to": str(deps.agent)},
        )
        return reply

    # ---- the run loop ------------------------------------------------------

    def deps_for(self, ticket_id: int | None) -> TeamDeps:
        """A fresh context for the Boss: depth 0, chain (boss,), a new delegation budget."""
        return TeamDeps(
            team=self,
            agent=AgentName.boss,
            ticket_id=ticket_id,
            chain=(AgentName.boss,),
            budget=Budget(limit=config.MAX_DELEGATIONS_PER_TICKET),
        )

    async def triage(self) -> TriagePlan:
        await self.log("run", "Boss is triaging the board", AgentName.boss)
        result = await self.run_agent(self.deps_for(None), boss_module.TRIAGE_PROMPT, mode="triage", agent=self.triage_agent)
        plan: TriagePlan = result.output
        await self.log("triage", f"Triage: {plan.summary}", AgentName.boss, data=plan.model_dump(mode="json"))
        return plan

    async def work_ticket(self, ticket_id: int, context: str | None = None) -> BossDecision:
        """The Boss works one ticket. `context` is what just happened when this is a re-work after a
        human's decision (the approval, the payment, the balance), so the Boss finishes rather than
        starting from the ticket's original wording."""
        deps = self.deps_for(ticket_id)
        await self.log("run", f"Boss starts ticket {ticket_id}" + (f" after: {context}" if context else ""), AgentName.boss, ticket_id)
        try:
            result = await self.run_agent(deps, boss_module.work_prompt(ticket_id, context), mode="ticket")
            decision: BossDecision = result.output
        except (UsageLimitExceeded, UnexpectedModelBehavior) as exc:
            decision = BossDecision(
                ticket_id=ticket_id, outcome="blocked", summary=f"The run stopped before a decision: {exc}"
            )
            await self.log("error", decision.summary, AgentName.boss, ticket_id)
        await self.log(
            "decision",
            f"Ticket {ticket_id}: {decision.outcome}. {decision.summary}",
            AgentName.boss,
            ticket_id,
            decision.model_dump(mode="json"),
        )
        return decision

    async def open_ticket_ids(self) -> list[int]:
        """Unresolved tickets in the board's order (prioritised first, then by id)."""
        tickets = unwrap(await self.toolset.call("list_tickets"))
        return [ticket["id"] for ticket in tickets if ticket["status"] != "resolved"]

    async def run_board(self) -> list[BossDecision]:
        await self.triage()
        decisions = [await self.work_ticket(ticket_id) for ticket_id in await self.open_ticket_ids()]
        summary = ", ".join(f"{d.ticket_id} {d.outcome}" for d in decisions) or "nothing open"
        await self.log("run", f"Board run finished: {summary}", AgentName.boss)
        return decisions

    # ---- the human's path (the only caller of the hidden tools) ------------

    async def decide(self, approval_id: int, decision: str, decided_by: str, note: str | None = None) -> Any:
        result = await self.toolset.call(
            "decide_approval",
            {"approval_id": approval_id, "decision": decision, "decided_by": decided_by, "note": note},
        )
        self.audit.human("decide_approval", approval_id=approval_id, decision=decision, decided_by=decided_by, note=note, result=result)
        return result

    async def pay(self, approval_id: int, approved_by: str) -> Any:
        result = await self.toolset.call("pay", {"approval_id": approval_id, "approved_by": approved_by})
        self.audit.human("pay", approval_id=approval_id, approved_by=approved_by, result=result)
        return result

    async def approve_and_pay(self, approval_id: int, approved_by: str, note: str | None = None) -> Any:
        decided = await self.decide(approval_id, "approved", approved_by, note)
        if isinstance(decided, dict) and "error" in decided:
            return decided
        return await self.pay(approval_id, approved_by)
