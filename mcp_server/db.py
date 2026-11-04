"""Database access for the Campus Customs MCP server.

Shop rule 1 lives here: the server works on the WORKING COPY,
``data/campus_customs_new.db``. The original ``data/campus_customs.db`` is the
reset source; this module refuses to open it, so nothing in the server can
ever write to it by mistake.

``CAMPUS_DB_PATH`` overrides the file. The tests set it to a temporary copy.

The working copy also receives a few schema additions the seed file does not
have (an assignee, a priority, a resolution, and a timestamp on each ticket,
plus a ``ticket_events`` table for the activity feed). They are created the
first time a connection is opened and are harmless to re-run.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

ORIGINAL_DB_PATH = DATA_DIR / "campus_customs.db"  # never opened by this package
WORKING_DB_PATH = DATA_DIR / "campus_customs_new.db"  # what every tool reads and writes


def db_path() -> Path:
    """The database file in use: the working copy, unless CAMPUS_DB_PATH says otherwise."""
    override = os.environ.get("CAMPUS_DB_PATH", "").strip()
    path = Path(override).expanduser().resolve() if override else WORKING_DB_PATH
    if path == ORIGINAL_DB_PATH.resolve():
        raise RuntimeError(
            "Refusing to work on data/campus_customs.db: that file is the untouched original. "
            "Point CAMPUS_DB_PATH at the working copy, data/campus_customs_new.db."
        )
    return path


# --------------------------------------------------------------------------
# Schema additions (working copy only)
# --------------------------------------------------------------------------

# Columns the seed's tickets table lacks. Added with ALTER TABLE if missing.
TICKET_COLUMNS_ADDED: dict[str, str] = {
    "assigned_to": "TEXT",  # which agent is working the ticket
    "priority": "INTEGER",  # 1 = most urgent; NULL until the Boss sets it
    "resolution": "TEXT",  # the Boss's closing summary
    "updated_at": "TEXT",  # real time of the last change
}

# The activity feed and audit log: one row per thing an agent or human did.
TICKET_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS ticket_events (
    id         INTEGER PRIMARY KEY,
    ticket_id  INTEGER,                -- NULL for shop-wide events
    agent      TEXT NOT NULL,          -- boss | inventory | accounting | facilities | customer_service | human | system
    kind       TEXT NOT NULL,          -- opened | assigned | priority | status | note | resolved | ...
    message    TEXT NOT NULL,
    data       TEXT,                   -- JSON with the details, when there are any
    created_at TEXT NOT NULL,          -- real wall-clock time, so the feed orders correctly
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
)
"""


# A request for a human decision. Money moves only after one of these is
# 'approved' (shop rule 5), and only through the pay tool.
APPROVALS_TABLE = """
CREATE TABLE IF NOT EXISTS approvals (
    id           INTEGER PRIMARY KEY,
    ticket_id    INTEGER,
    kind         TEXT NOT NULL,         -- invoice | rent | purchase_order | price_override
    ref_id       INTEGER,               -- invoice id, lease id, purchase order id, or NULL
    amount       REAL NOT NULL,         -- taken from the referenced row; 0 for a price override
    account      TEXT NOT NULL DEFAULT 'checking',
    rationale    TEXT NOT NULL,
    requested_by TEXT NOT NULL,         -- agent name
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | executed
    decided_by   TEXT,
    decided_at   TEXT,
    decision_note TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
)
"""

# Customer messages written by the agents. They stay here (shop rule 9):
# there is no tool that sends one.
DRAFTS_TABLE = """
CREATE TABLE IF NOT EXISTS drafts (
    id         INTEGER PRIMARY KEY,
    ticket_id  INTEGER NOT NULL,
    recipient  TEXT NOT NULL,
    subject    TEXT NOT NULL,
    body       TEXT NOT NULL,
    author     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
)
"""

# Restock orders. Priced from the pricing table, dated from the vendor's lead
# time (shop rule 3), and never created for a vendor with an open invoice
# (shop rule 4).
PURCHASE_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS purchase_orders (
    id            INTEGER PRIMARY KEY,
    ticket_id     INTEGER,
    vendor_id     INTEGER NOT NULL,
    sku           TEXT NOT NULL,
    size          TEXT NOT NULL,
    qty           INTEGER NOT NULL,
    unit_cost     REAL NOT NULL,
    total         REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',  -- draft | waiting_approval | ordered | received
    expected_date TEXT,                           -- shop's today + vendor lead days, set when ordered
    created_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id),
    FOREIGN KEY (vendor_id) REFERENCES vendors(id)
)
"""

ADDED_TABLES = (TICKET_EVENTS_TABLE, APPROVALS_TABLE, DRAFTS_TABLE, PURCHASE_ORDERS_TABLE)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Add the columns and tables the tools need, if they are not there yet."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(tickets)")}
    for column, column_type in TICKET_COLUMNS_ADDED.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE tickets ADD COLUMN {column} {column_type}")
    for statement in ADDED_TABLES:
        conn.execute(statement)
    conn.commit()


# --------------------------------------------------------------------------
# Connections
# --------------------------------------------------------------------------


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open the working copy for one tool call.

    Commits when the block finishes normally, rolls back if it raises, and
    always closes. Rows come back as ``sqlite3.Row`` so they can be read by
    column name and turned into dicts.
    """
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found: {path}. Unzip data.zip in the project root and copy "
            "data/campus_customs.db to data/campus_customs_new.db."
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        ensure_schema(conn)
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Small helpers shared by the tool modules
# --------------------------------------------------------------------------


def shop_today(conn: sqlite3.Connection) -> str:
    """The shop's date (shop rule 2): ``desk.date_today``, never the real calendar."""
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("The desk table is empty, so the shop has no date.")
    return row["date_today"]


def now_iso() -> str:
    """Real wall-clock time, used only to order the activity feed."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def one(cursor: sqlite3.Cursor) -> dict | None:
    row = cursor.fetchone()
    return dict(row) if row is not None else None
