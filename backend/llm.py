"""The one model every agent uses: gpt-6-luna through the Portkey gateway.

Same construction as Homework 4: an OpenAI-compatible client pointed at
PORTKEY_BASE_URL with PORTKEY_API_KEY, wrapped in PydanticAI's OpenAI chat
model. Built once and shared.
"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from backend import config


class ModelNotConfigured(RuntimeError):
    """Raised when PORTKEY_API_KEY is missing."""


# The gateway's chat-completions endpoint accepts function tools for gpt-6-luna
# only with reasoning effort "none" (its 400 says so); without tools it does not
# care. Every agent uses tools, so the setting is part of the model.
MODEL_SETTINGS = OpenAIChatModelSettings(openai_reasoning_effort="none")


@lru_cache(maxsize=1)
def get_model() -> OpenAIChatModel:
    if not config.PORTKEY_API_KEY:
        raise ModelNotConfigured("PORTKEY_API_KEY is not set. Add it to backend/.env (see backend/.env.example).")
    client = AsyncOpenAI(
        base_url=config.PORTKEY_BASE_URL,
        api_key=config.PORTKEY_API_KEY,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        max_retries=2,
    )
    return OpenAIChatModel(config.MODEL_NAME, provider=OpenAIProvider(openai_client=client), settings=MODEL_SETTINGS)
