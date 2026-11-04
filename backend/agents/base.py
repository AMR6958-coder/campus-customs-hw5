"""What all five agents share: the prompt loader, the delegation tool, and the constructor.

Full connectivity means every agent carries the same ``ask_colleague`` tool
and may call any other agent with it. What keeps that from looping is in
``delegation_problem``: no agent asks itself, no agent asks someone already in
the chain that led to it, the chain cannot go deeper than
``config.MAX_DELEGATION_DEPTH``, and one ticket has a shared budget of
delegations. A refused delegation is returned to the model as a sentence, so
it can finish with what it has.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from backend import config
from backend.llm import get_model
from backend.models import AgentName, TeamDeps


def load_prompt(name: AgentName) -> str:
    """The agent's own instructions first, then the shared rules every agent gets."""
    own = (config.PROMPTS_DIR / f"{name.value}.md").read_text(encoding="utf-8").strip()
    shared = (config.PROMPTS_DIR / "shared.md").read_text(encoding="utf-8").strip()
    return f"{own}\n\n{shared}\n"


def delegation_problem(deps: TeamDeps, colleague: AgentName) -> str | None:
    """Why this delegation must be refused, or None if it may go ahead."""
    if colleague == deps.agent:
        return "an agent cannot ask itself"
    if colleague in deps.chain:
        chain = " > ".join(deps.chain)
        return f"{colleague} is already in this chain ({chain}); answer with what you have"
    if deps.depth + 1 > config.MAX_DELEGATION_DEPTH:
        return f"the delegation depth limit ({config.MAX_DELEGATION_DEPTH}) is reached; finish with what you have"
    if deps.budget.remaining <= 0:
        return f"this ticket's delegation budget ({deps.budget.limit}) is used up; finish with what you have"
    return None


async def ask_colleague(ctx: RunContext[TeamDeps], colleague: AgentName, request: str) -> str:
    """Hand a specific request to another agent and get their written report back.

    colleague: boss, inventory, accounting, facilities, or customer_service.
    request: say what you need, and include the ticket id and the facts you
    already have. Refused when an agent asks itself, when the colleague is
    already in the chain that led to you, past the depth limit, or when the
    ticket's delegation budget is used up; then finish with what you have.
    """
    deps = ctx.deps
    problem = delegation_problem(deps, colleague)
    if problem is not None:
        return f"Delegation refused: {problem}."
    return await deps.team.delegate(deps, colleague, request, ctx.usage)


def build_agent(
    name: AgentName,
    toolset: AbstractToolset[Any],
    *,
    model: Model | None = None,
    output_type: Any = str,
) -> Agent[TeamDeps, Any]:
    """One agent: gpt-6-luna, its prompt, the shop tools, and ask_colleague."""
    return Agent(
        model or get_model(),
        name=name.value,
        instructions=load_prompt(name),
        deps_type=TeamDeps,
        output_type=output_type,
        tools=[ask_colleague],
        toolsets=[toolset],
        retries=2,
    )
