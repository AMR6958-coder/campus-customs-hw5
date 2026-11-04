"""Accounting: cash, invoices, margins; prepares payments for the human's approval.

Leans on get_cash, list_invoices, list_payments, get_pricing, list_approvals,
list_purchase_orders, and request_approval. It never has pay or
decide_approval: those stay with the human (shop rule 5).
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from backend.agents.base import build_agent
from backend.models import AgentName, TeamDeps

NAME = AgentName.accounting


def build(toolset: AbstractToolset[Any], model: Model | None = None) -> Agent[TeamDeps, Any]:
    return build_agent(NAME, toolset, model=model)
