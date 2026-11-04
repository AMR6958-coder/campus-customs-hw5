"""The Boss: reads each ticket, decides who works it, makes the final call.

The Boss is the only agent the Team runs directly. It has two jobs, and each
is its own Agent object on the same prompt and tools, because PydanticAI ties
the output type and its validators to the agent: ``build`` gives the ticket
agent (output BossDecision, checked against the ticket by
``decision_matches_the_ticket``) and ``build_triage`` the triage agent (output
TriagePlan). Every chain starts with the Boss, so the Boss never receives a
delegation and never needs a plain-text output. Everything else it does
through the specialists with ask_colleague.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from backend.agents.base import build_agent
from backend.models import AgentName, BossDecision, TeamDeps, TriagePlan

NAME = AgentName.boss

TRIAGE_PROMPT = (
    "Triage the board. Look at every open ticket, set a priority (1 = most urgent) and assign each "
    "one to the specialist who should start, then return the plan."
)


def work_prompt(ticket_id: int, context: str | None = None) -> str:
    prompt = (
        f"Work ticket {ticket_id}. Read it, bring in the specialists you need through ask_colleague, "
        "make sure anything that needs money is requested for the human's approval, write a note "
        "the human can follow, and make the final call."
    )
    if context:
        prompt += (
            f"\n\nWhat just happened: {context} Check it with the tools (list_approvals, list_payments, "
            "get_lease or get_invoice as the ticket needs) and finish the ticket: if what it asked for is "
            "now done, resolve it with the figures. Do not request the same money again."
        )
    return prompt


async def decision_matches_the_ticket(ctx: RunContext[TeamDeps], output: Any) -> Any:
    """The Boss's final call must agree with the ticket as the tools show it (shop rule 1).

    A decision that says "resolved" while the ticket still sits in waiting_approval with no
    resolution, or "waiting_approval" while nothing was requested, is a claim the tools do not
    show. The Boss is sent back to make the call for real (resolve_ticket, request the approval)
    or to return the outcome that matches the ticket.
    """
    if not isinstance(output, BossDecision):
        return output
    ticket_id = ctx.deps.ticket_id if ctx.deps.ticket_id is not None else output.ticket_id
    output.ticket_id = ticket_id
    ticket = await ctx.deps.team.toolset.call("get_ticket", {"ticket_id": ticket_id})
    status = ticket.get("status") if isinstance(ticket, dict) else None
    problem = None
    if output.outcome == "resolved" and status != "resolved":
        problem = (
            f"You returned outcome 'resolved', but ticket {ticket_id} is still '{status}' and has no resolution on record. "
            "If the work is done, call resolve_ticket with a resolution that states the facts and the figures, then return "
            "the decision again. If it is not done, return the outcome that matches the ticket."
        )
    elif output.outcome == "waiting_approval" and status != "waiting_approval":
        problem = (
            f"You returned outcome 'waiting_approval', but ticket {ticket_id} is '{status}'. A ticket waits for the human "
            "only once request_approval has been called for it. Either have the approval requested, or return the outcome "
            "that matches the ticket."
        )
    if problem is not None:
        await ctx.deps.team.log("retry", f"Boss's decision did not match the ticket: {problem}", NAME, ticket_id, {"outcome": output.outcome, "status": status})
        raise ModelRetry(problem)
    return output


def build(toolset: AbstractToolset[Any], model: Model | None = None) -> Agent[TeamDeps, Any]:
    """The Boss working one ticket: returns a BossDecision that must match the ticket."""
    agent = build_agent(NAME, toolset, model=model, output_type=BossDecision)
    agent.output_validator(decision_matches_the_ticket)
    return agent


def build_triage(toolset: AbstractToolset[Any], model: Model | None = None) -> Agent[TeamDeps, Any]:
    """The Boss triaging the board: returns a TriagePlan."""
    return build_agent(NAME, toolset, model=model, output_type=TriagePlan)
