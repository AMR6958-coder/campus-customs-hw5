"""Facilities: the shop space, the lease, rent due dates, the landlord.

Leans on get_lease and get_today, and asks accounting to request the rent
approval. A paid rent shows as the lease's next_due moving one month.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from backend.agents.base import build_agent
from backend.models import AgentName, TeamDeps

NAME = AgentName.facilities


def build(toolset: AbstractToolset[Any], model: Model | None = None) -> Agent[TeamDeps, Any]:
    return build_agent(NAME, toolset, model=model)
