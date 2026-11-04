"""Command line for the agent team (the dashboard does the same through the API next step).

    .venv\\Scripts\\python -m backend.run --reset --board        # reset the shop, triage, work every ticket
    .venv\\Scripts\\python -m backend.run --triage               # the Boss ranks and assigns the board
    .venv\\Scripts\\python -m backend.run --ticket 102           # the Boss works one ticket
    .venv\\Scripts\\python -m backend.run --approve 1 --by "Store Manager"   # the human approves and pays
    .venv\\Scripts\\python -m backend.run --reject 1 --by "Store Manager" --note "wait"

Add ``--log output/agent_run.txt`` to append everything printed to a file.
The MCP server must be running: ``.venv\\Scripts\\python -m mcp_server.server``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from backend import config
from backend.models import RunEvent
from backend.team import Team, unwrap


class Printer:
    """Prints run events as they happen, optionally appending them to a file."""

    def __init__(self, log_path: Path | None) -> None:
        self.log_path = log_path
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)

    def line(self, text: str) -> None:
        print(text, flush=True)
        if self.log_path is not None:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")

    def event(self, event: RunEvent) -> None:
        ticket = f" #{event.ticket_id}" if event.ticket_id is not None else ""
        self.line(f"{event.at:%H:%M:%S} [{event.agent}{ticket}] {event.kind}: {event.message}")


def server_is_up(url: str) -> bool:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "backend.run", "version": "0"}}}
    ).encode()
    request = urllib.request.Request(
        url, body, {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


async def summary(team: Team, out: Printer) -> None:
    tickets = unwrap(await team.toolset.call("list_tickets"))
    cash = await team.toolset.call("get_cash")
    approvals = unwrap(await team.toolset.call("list_approvals"))
    orders = unwrap(await team.toolset.call("list_purchase_orders"))
    drafts = unwrap(await team.toolset.call("list_drafts"))
    out.line("")
    out.line("Board now:")
    for ticket in tickets:
        who = ticket["assigned_to"] or "-"
        priority = ticket["priority"] if ticket["priority"] is not None else "-"
        out.line(f"  #{ticket['id']} {ticket['type']:<15} {ticket['status']:<17} assigned={who:<17} priority={priority}")
    out.line(f"Cash: {', '.join(f'{a['name']} ${a['balance']:.2f}' for a in cash['accounts'])}")
    for approval in approvals:
        out.line(f"Approval {approval['id']}: {approval['kind']} {approval['ref_id'] or ''} ${approval['amount']:.2f} {approval['status']} (ticket {approval['ticket_id']})")
    for order in orders:
        out.line(f"Purchase order {order['id']}: {order['qty']} x {order['sku']} {order['size']} ${order['total']:.2f} {order['status']}, expected {order['expected_date']}")
    for draft in drafts:
        out.line(f"Draft {draft['id']} to {draft['recipient']}: {draft['subject']} (ticket {draft['ticket_id']})")


async def run(args: argparse.Namespace) -> int:
    out = Printer(args.log)
    if not server_is_up(config.MCP_URL):
        out.line(f"Could not reach the MCP server at {config.MCP_URL}. Start it with: .venv\\Scripts\\python -m mcp_server.server")
        return 2
    team = Team()
    team.listeners.append(out.event)
    out.line(f"=== {datetime.now().astimezone():%Y-%m-%d %H:%M:%S} backend.run {' '.join(sys.argv[1:])} (model {config.MODEL_NAME}) ===")
    async with team:
        if args.approve is not None:
            out.line(json.dumps(await team.approve_and_pay(args.approve, args.by, args.note), indent=2))
        elif args.reject is not None:
            out.line(json.dumps(await team.decide(args.reject, "rejected", args.by, args.note), indent=2))
        elif args.triage:
            out.line((await team.triage()).model_dump_json(indent=2))
        elif args.ticket is not None:
            out.line((await team.work_ticket(args.ticket)).model_dump_json(indent=2))
        else:
            for decision in await team.run_board():
                out.line(decision.model_dump_json(indent=2))
        await summary(team, out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team.")
    parser.add_argument("--reset", action="store_true", help="copy the original database over the working copy first (shop rule 8)")
    what = parser.add_mutually_exclusive_group()
    what.add_argument("--board", action="store_true", help="triage, then work every open ticket (default)")
    what.add_argument("--triage", action="store_true", help="the Boss ranks and assigns the open tickets")
    what.add_argument("--ticket", type=int, metavar="ID", help="the Boss works one ticket")
    what.add_argument("--approve", type=int, metavar="APPROVAL_ID", help="the human approves and pays")
    what.add_argument("--reject", type=int, metavar="APPROVAL_ID", help="the human rejects")
    parser.add_argument("--by", default=config.DEFAULT_APPROVER, help="the human's name for approve/reject")
    parser.add_argument("--note", help="the human's note on an approve/reject")
    parser.add_argument("--log", type=Path, help="append everything printed to this file")
    args = parser.parse_args(argv)
    if args.reset:
        from backend.audit_trail import AuditTrail
        from mcp_server.reset import reset_working_copy

        result = reset_working_copy()
        AuditTrail().human("reset", target=result["target"], counts=result["counts"], checking_balance=result["checking_balance"])
        print(f"Reset {result['target']}: tickets={result['counts']['tickets']} payments={result['counts']['payments']} checking=${result['checking_balance']:.2f}")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
