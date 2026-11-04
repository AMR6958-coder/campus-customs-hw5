"""Reset the working copy to the original seed (shop rule 8).

Copies ``data/campus_customs.db`` over the working copy (or whatever
``CAMPUS_DB_PATH`` points at), re-applies the schema additions, and logs one
shop-wide ``reset`` event so the activity feed shows where a run began.

This is deliberately not an MCP tool: agents cannot reset the shop. Run it
before a full run::

    .venv\\Scripts\\python -m mcp_server.reset
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from mcp_server import db
from mcp_server.tickets import log_event


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reset_working_copy() -> dict:
    """Overwrite the working copy with the original and return a short summary."""
    target = db.db_path()  # refuses the original itself
    if not db.ORIGINAL_DB_PATH.exists():
        raise FileNotFoundError(f"Original database not found: {db.ORIGINAL_DB_PATH}. Unzip data.zip in the project root.")
    before = sha256(db.ORIGINAL_DB_PATH)
    shutil.copyfile(db.ORIGINAL_DB_PATH, target)
    with db.connect() as conn:
        event = log_event(conn, "system", "reset", "Working copy reset to the original seed data")
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("tickets", "payments", "approvals", "purchase_orders", "drafts")
        }
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()[0]
    assert sha256(db.ORIGINAL_DB_PATH) == before, "the original database changed during the reset"
    return {"target": str(target), "event_id": event["id"], "counts": counts, "checking_balance": cash}


if __name__ == "__main__":
    summary = reset_working_copy()
    print(f"Reset {summary['target']}")
    print(f"  tickets={summary['counts']['tickets']} payments={summary['counts']['payments']} checking=${summary['checking_balance']:.2f}")
