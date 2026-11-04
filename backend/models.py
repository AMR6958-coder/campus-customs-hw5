"""Data types shared by the agents, the team, and (next step) the API.

Pydantic models are what the agents return as structured output (the Boss's
triage plan and ticket decision) and what the feed carries (RunEvent). The
dataclasses are the per-run context handed to every tool call (TeamDeps) and
the shared delegation budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentName(StrEnum):
    boss = "boss"
    inventory = "inventory"
    accounting = "accounting"
    facilities = "facilities"
    customer_service = "customer_service"


SPECIALISTS = (AgentName.inventory, AgentName.accounting, AgentName.facilities, AgentName.customer_service)


# --------------------------------------------------------------------------
# What the Boss returns
# --------------------------------------------------------------------------


class TriageItem(BaseModel):
    ticket_id: int
    priority: int = Field(ge=1, description="1 = most urgent")
    assigned_to: AgentName = Field(description="the specialist who should start on it")
    reason: str = Field(description="one sentence on why this priority and this agent")


class TriagePlan(BaseModel):
    items: list[TriageItem]
    summary: str = Field(description="two or three sentences on the state of the board")


TicketOutcome = Literal["resolved", "waiting_approval", "blocked"]


class BossDecision(BaseModel):
    ticket_id: int
    outcome: TicketOutcome = Field(
        description="resolved = closed with a resolution; waiting_approval = a human must approve a payment first; blocked = cannot proceed, see summary"
    )
    summary: str = Field(description="what was found, what was done, and what happens next, in plain sentences")
    delegated_to: list[AgentName] = Field(default_factory=list, description="colleagues asked for help on this ticket")
    approvals_requested: list[int] = Field(default_factory=list, description="approval ids waiting for the human")
    drafts_written: list[int] = Field(default_factory=list, description="draft ids left on the board")
    purchase_orders: list[int] = Field(default_factory=list, description="purchase order ids drafted")


# --------------------------------------------------------------------------
# The activity feed
# --------------------------------------------------------------------------


class RunEvent(BaseModel):
    """One thing that happened during a run; mirrors a ticket_events row."""

    kind: str
    agent: str
    message: str
    ticket_id: int | None = None
    data: dict[str, Any] | None = None
    at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


# --------------------------------------------------------------------------
# Per-run context (the `deps` every tool call receives)
# --------------------------------------------------------------------------


@dataclass
class Budget:
    """How many delegations the whole chain working one ticket may still make."""

    limit: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used


@dataclass
class TeamDeps:
    team: Any  # the Team (typed as Any to avoid an import cycle)
    agent: AgentName
    ticket_id: int | None
    depth: int = 0
    chain: tuple[AgentName, ...] = ()
    budget: Budget = field(default_factory=lambda: Budget(limit=12))
    run_id: str | None = None  # this agent run's id in the audit trail (set by the Team)
    parent_run_id: str | None = None  # the run that delegated to this one, if any

    def child(self, colleague: AgentName) -> TeamDeps:
        """The context a colleague works in when this agent asks them for help."""
        return replace(
            self,
            agent=colleague,
            depth=self.depth + 1,
            chain=self.chain + (colleague,),
            run_id=None,
            parent_run_id=self.run_id,
        )


# --------------------------------------------------------------------------
# The API (backend/main.py): what the dashboard sends and receives
# --------------------------------------------------------------------------


class TicketSummary(BaseModel):
    """One row of the board: the ticket as the MCP server lists it, plus `open`."""

    id: int
    type: str
    requester: str | None = None
    subject: str | None = None
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    notes: str | None = None
    status: str
    open: bool = Field(description="True unless the status is resolved")
    assigned_to: str | None = None
    priority: int | None = None
    resolution: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DecisionRequest(BaseModel):
    """The human's approve or reject from the dashboard."""

    by: str = Field(default="Store Manager", min_length=1, description="the human's name, recorded on the approval and the payment")
    note: str | None = None
    rework: bool = Field(default=True, description="after the decision, have the Boss re-work the ticket in the background")


JobKind = Literal["ticket", "board", "rework"]
JobStatus = Literal["running", "done", "error"]


class JobInfo(BaseModel):
    """A background run of the team: one ticket, the whole board, or a re-work after a decision."""

    id: str
    kind: JobKind
    ticket_id: int | None = None
    status: JobStatus = "running"
    started_at: datetime
    finished_at: datetime | None = None
    result: Any = None  # the Boss's decision(s) once done
    error: str | None = None


class EventsPage(BaseModel):
    """A page of the ticket timeline, oldest first; poll again with since=last_id."""

    events: list[dict[str, Any]]
    last_id: int | None = None


class CashView(BaseModel):
    checking: float
    accounts: list[dict[str, Any]]
    total: float
