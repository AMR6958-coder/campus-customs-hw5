"""Append-only audit trail of the agent team's work: ``output/audit_trail.json``.

Same shape as Homework 4: JSON Lines, one complete JSON object per line, the
only JSON layout that can be appended to safely. Nothing in the code base
rewrites, edits, or deletes the file; every run adds to it.

What gets written, as it happens:

- ``run_started``: an agent run begins (the Boss on a ticket or the board, or
  a colleague answering a delegation), with the agent, the ticket, the chain,
  the parent run, the prompt given, and the prompt files in force.
- ``step``: one loop step of that run, written the moment the model's response
  arrives: the request that went in (the user prompt, or the tool results and
  retries from the previous step), and the response (text, tool calls with
  their arguments, token usage, the model name the gateway reported).
- ``run_finished``: the run's outcome and output (or the error), total usage,
  and duration.
- ``human``: a human decision or payment made through the back end, and a
  reset of the working copy.

Tool results are previewed up to PREVIEW_CHARS; the database is the record of
what the tools did. The trail contains customer names from the tickets, so
treat it like the database.

Read it from the command line::

    .venv\\Scripts\\python -m backend.audit_trail --tail 5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from backend import config

TRAIL_PATH = Path(os.getenv("AUDIT_TRAIL_PATH") or config.PROJECT_ROOT / "output" / "audit_trail.json")
PREVIEW_CHARS = 2000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def preview(value: Any, limit: int = PREVIEW_CHARS) -> Any:
    """JSON-friendly copy of a value, cut to `limit` characters when long."""
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    if len(text) <= limit:
        return value if isinstance(value, (str, dict, list)) else text
    return text[:limit] + f"... [{len(text) - limit} more chars]"


# --------------------------------------------------------------------------
# Serialising PydanticAI messages
# --------------------------------------------------------------------------


def serialize_request(request: ModelRequest | None) -> dict[str, Any] | None:
    if request is None:
        return None
    parts: list[dict[str, Any]] = []
    for part in request.parts:
        if isinstance(part, UserPromptPart):
            parts.append({"part": "user_prompt", "content": preview(part.content)})
        elif isinstance(part, ToolReturnPart):
            parts.append({"part": "tool_return", "tool": part.tool_name, "tool_call_id": part.tool_call_id, "content": preview(part.content)})
        elif isinstance(part, RetryPromptPart):
            parts.append({"part": "retry", "tool": part.tool_name, "content": preview(part.content)})
        elif isinstance(part, SystemPromptPart):
            parts.append({"part": "system_prompt", "content": preview(part.content, 300)})
        else:
            parts.append({"part": type(part).__name__})
    record: dict[str, Any] = {"timestamp": request.timestamp.isoformat() if request.timestamp else None, "parts": parts}
    if request.instructions:
        record["instructions_sha256"] = hashlib.sha256(request.instructions.encode("utf-8")).hexdigest()[:16]
        record["instructions_chars"] = len(request.instructions)
    return record


def serialize_response(response: ModelResponse) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    for part in response.parts:
        if isinstance(part, TextPart):
            parts.append({"part": "text", "content": preview(part.content)})
        elif isinstance(part, ToolCallPart):
            parts.append({"part": "tool_call", "tool": part.tool_name, "tool_call_id": part.tool_call_id, "args": preview(part.args_as_dict() if hasattr(part, "args_as_dict") else part.args)})
        elif isinstance(part, ThinkingPart):
            parts.append({"part": "thinking", "chars": len(part.content or "")})
        else:
            parts.append({"part": type(part).__name__})
    usage = response.usage
    return {
        "timestamp": response.timestamp.isoformat() if response.timestamp else None,
        "model": response.model_name,
        "finish_reason": response.finish_reason,
        "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
        "parts": parts,
    }


# --------------------------------------------------------------------------
# The trail
# --------------------------------------------------------------------------


class AuditTrail:
    def __init__(self, path: Path = TRAIL_PATH) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> None:
        """Add one line. The file is opened in append mode and never truncated."""
        line = json.dumps({"ts": now_iso(), **record}, default=str, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def run_started(self, *, run_id: str, agent: str, mode: str, ticket_id: int | None, depth: int, chain: list[str], parent_run_id: str | None, prompt: str) -> None:
        self.append(
            {
                "record": "run_started",
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "agent": agent,
                "mode": mode,
                "ticket_id": ticket_id,
                "depth": depth,
                "chain": chain,
                "model": config.MODEL_NAME,
                "prompt_files": prompt_files(agent),
                "prompt": preview(prompt),
            }
        )

    def step(self, *, run_id: str, agent: str, ticket_id: int | None, step: int, request: ModelRequest | None, response: ModelResponse) -> None:
        self.append(
            {
                "record": "step",
                "run_id": run_id,
                "agent": agent,
                "ticket_id": ticket_id,
                "step": step,
                "request": serialize_request(request),
                "response": serialize_response(response),
            }
        )

    def run_finished(self, *, run_id: str, agent: str, ticket_id: int | None, outcome: str, output: Any, steps: int, usage: Any, duration_ms: int, error: str | None = None) -> None:
        self.append(
            {
                "record": "run_finished",
                "run_id": run_id,
                "agent": agent,
                "ticket_id": ticket_id,
                "outcome": outcome,
                "steps": steps,
                "usage": usage_dict(usage),
                "duration_ms": duration_ms,
                "output": preview(output),
                "error": error,
            }
        )

    def human(self, action: str, **details: Any) -> None:
        self.append({"record": "human", "action": action, **{k: preview(v) for k, v in details.items()}})


def usage_dict(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "requests": getattr(usage, "requests", None),
        "tool_calls": getattr(usage, "tool_calls", None),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }


def prompt_files(agent: str) -> list[dict[str, Any]]:
    files = []
    for name in (f"{agent}.md", "shared.md"):
        path = config.PROMPTS_DIR / name
        if path.exists():
            files.append({"file": name, "modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")})
    return files


def read_trail(path: Path = TRAIL_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read the audit trail.")
    parser.add_argument("--tail", type=int, default=10, help="how many of the last records to print")
    args = parser.parse_args(argv)
    records = read_trail()
    for record in records[-args.tail :]:
        print(json.dumps(record, ensure_ascii=False)[:400])
    print(f"{len(records)} records in {TRAIL_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
