"""Inventory: stock by SKU and size, shortfalls, which vendor can restock and when.

Leans on get_stock, list_stock, get_pricing, list_vendors, get_today,
create_purchase_order (refused while the vendor has an open invoice), and
open_ticket for restocks. Asks accounting when an invoice blocks a vendor.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from backend.agents.base import build_agent
from backend.models import AgentName, TeamDeps

NAME = AgentName.inventory


def build(toolset: AbstractToolset[Any], model: Model | None = None) -> Agent[TeamDeps, Any]:
    return build_agent(NAME, toolset, model=model)
