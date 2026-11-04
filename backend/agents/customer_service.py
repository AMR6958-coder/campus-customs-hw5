"""Customer Service: drafts messages to customers. Nothing is sent (shop rule 9).

Leans on get_ticket and draft_customer_message, and asks inventory for a
delivery date before promising one.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from backend.agents.base import build_agent
from backend.models import AgentName, TeamDeps

NAME = AgentName.customer_service


def build(toolset: AbstractToolset[Any], model: Model | None = None) -> Agent[TeamDeps, Any]:
    return build_agent(NAME, toolset, model=model)
