"""The five agents, one module each. Each module exposes NAME and build(toolset, model=None)."""

from __future__ import annotations

from backend.agents import accounting, boss, customer_service, facilities, inventory
from backend.models import AgentName

AGENT_MODULES = {
    AgentName.boss: boss,
    AgentName.inventory: inventory,
    AgentName.accounting: accounting,
    AgentName.facilities: facilities,
    AgentName.customer_service: customer_service,
}

__all__ = ["AGENT_MODULES", "boss", "inventory", "accounting", "facilities", "customer_service"]
