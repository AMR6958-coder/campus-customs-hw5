"""Check every tool output recorded in mcp_smoke.json against the working copy.

For each entry, runs ``db_check.sql`` read-only against data/campus_customs_new.db,
compares the rows with ``db_check.expect`` (the value taken from the tool's
output), and writes ``db_value`` and ``match`` back into the JSON, plus a
summary at the top. Exit code 1 if anything does not match.

    .venv\\Scripts\\python output\\check_mcp_smoke.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parent / "data" / "campus_customs_new.db"
JSON_PATH = HERE / "mcp_smoke.json"


def normalise(rows: list[tuple]) -> object:
    """Rows as lists; a single one-column row collapses to that value."""
    out = [list(row) for row in rows]
    if len(out) == 1 and len(out[0]) == 1:
        return out[0][0]
    return out


def main() -> int:
    doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    matched, mismatched, tools = 0, 0, set()
    for entry in doc["entries"]:
        check = entry["db_check"]
        value = normalise(conn.execute(check["sql"]).fetchall())
        check["db_value"] = value
        check["match"] = value == check["expect"]
        tools.add(entry["tool"])
        if check["match"]:
            matched += 1
        else:
            mismatched += 1
            print(f"MISMATCH step {entry['step']} {entry['tool']}:\n  expected {check['expect']!r}\n  database {value!r}")
    conn.close()
    doc["summary"] = {
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "entries": len(doc["entries"]),
        "distinct_tools": len(tools),
        "matched": matched,
        "mismatched": mismatched,
    }
    JSON_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(doc['entries'])} entries, {len(tools)} distinct tools, {matched} matched, {mismatched} mismatched")
    return 0 if mismatched == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
