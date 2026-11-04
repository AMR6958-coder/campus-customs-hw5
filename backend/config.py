"""Settings for the back end, read from backend/.env.

Shop rule 10 lives here: every agent uses gpt-6-luna through the Portkey
gateway with PORTKEY_API_KEY. The model name is a constant, not a setting;
if the .env names a different model the back end refuses to start.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"

# PydanticAI prints a banner on first use; keep the console for the run log.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# The project's .env wins over same-named variables inherited from the machine.
load_dotenv(BACKEND_DIR / ".env", override=True)

PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY", "").strip()
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").strip()

MODEL_NAME = "gpt-6-luna"
_configured_model = os.getenv("OPENAI_MODEL", MODEL_NAME).strip()
if _configured_model != MODEL_NAME:
    raise RuntimeError(f"Shop rule 10: every agent uses {MODEL_NAME}; backend/.env names '{_configured_model}'.")

# The MCP server the agents work through (the HTTP copy, shared with the dashboard).
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8100/mcp").strip()

REQUEST_TIMEOUT_SECONDS = 90

# Delegation limits, so a chain of "ask a colleague" always ends.
MAX_DELEGATION_DEPTH = 3  # boss -> a -> b -> c, then no further
MAX_DELEGATIONS_PER_TICKET = 12  # shared by everyone working one ticket
REQUEST_LIMIT_PER_TICKET = 60  # model calls across the whole chain for one ticket
TOOL_CALLS_LIMIT_PER_TICKET = 120

# Tools the agents never see. Paying and deciding are the human's; log_event is the back end's.
HUMAN_ONLY_TOOLS = frozenset({"pay", "decide_approval"})
BACKEND_ONLY_TOOLS = frozenset({"log_event"})
HIDDEN_FROM_AGENTS = HUMAN_ONLY_TOOLS | BACKEND_ONLY_TOOLS

# Who approves at the console runner. The dashboard will ask for a real name.
DEFAULT_APPROVER = "Store Manager"
