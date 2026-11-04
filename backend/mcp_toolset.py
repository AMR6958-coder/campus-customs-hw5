"""A PydanticAI toolset backed by the Campus Customs MCP server.

Every tool the server lists becomes a tool the agents can call, with the
server's own name, description, and argument schema, so the agents and the
server never disagree about what a tool is. Calls go through the official
``mcp`` SDK client (streamable HTTP for the running server, stdio for the
tests), which is the client that works on this machine.

A refusal from a tool (a ValueError on the server) comes back to the model as
``{"error": "<the sentence>"}`` rather than an exception, because refusals
such as "the vendor will not ship while invoice 501 is unpaid" are facts the
agent should read and act on, not failures to retry.

One instance is shared by all agents; it connects once (reference-counted
enter/exit) and stays connected for the whole run.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_core import SchemaValidator, core_schema

# The MCP server validates arguments itself; here anything JSON-shaped passes.
_ANY_ARGS = SchemaValidator(schema=core_schema.any_schema())


class _DropSessionTerminationNoise(logging.Filter):
    """On this machine the server's reply to the closing DELETE is cut short by a
    local proxy; the session is gone either way, so the SDK's warning is noise."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Session termination failed")


logging.getLogger("mcp.client.streamable_http").addFilter(_DropSessionTerminationNoise())

# Called after every tool call an agent makes: (deps, tool name, arguments, result).
CallHook = Callable[[Any, str, dict[str, Any], Any], Awaitable[None]]


class MCPToolset(AbstractToolset[Any]):
    def __init__(
        self,
        url: str | None = None,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        toolset_id: str = "campus-customs",
    ) -> None:
        if not url and not command:
            raise ValueError("Give a url (streamable HTTP) or a command (stdio).")
        self.url = url
        self.command, self.args, self.env, self.cwd = command, args or [], env, cwd
        self._id = toolset_id
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tool_defs: list[ToolDefinition] = []
        self._entered = 0
        self.on_call: CallHook | None = None

    # ---- lifecycle ---------------------------------------------------------

    async def __aenter__(self) -> MCPToolset:
        if self._entered == 0:
            stack = AsyncExitStack()
            await stack.__aenter__()
            try:
                if self.url:
                    read, write = await stack.enter_async_context(streamable_http_client(self.url))
                else:
                    params = StdioServerParameters(
                        command=self.command or "",
                        args=self.args,
                        env={**os.environ, **(self.env or {})},
                        cwd=self.cwd,
                    )
                    read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                listed = await session.list_tools()
            except BaseException:
                await stack.aclose()
                raise
            self._stack, self._session = stack, session
            self._tool_defs = [
                ToolDefinition(
                    name=tool.name,
                    description=tool.description or "",
                    parameters_json_schema=_input_schema(tool),
                    sequential=True,  # one shop action at a time keeps the event log readable
                )
                for tool in listed.tools
            ]
        self._entered += 1
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self._entered -= 1
        if self._entered == 0 and self._stack is not None:
            stack, self._stack, self._session = self._stack, None, None
            await stack.aclose()

    @property
    def id(self) -> str | None:
        return self._id

    @property
    def tool_names(self) -> list[str]:
        return [tool.name for tool in self._tool_defs]

    # ---- the toolset interface ---------------------------------------------

    async def get_tools(self, ctx: RunContext[Any]) -> dict[str, ToolsetTool[Any]]:
        return {
            tool_def.name: ToolsetTool(toolset=self, tool_def=tool_def, max_retries=1, args_validator=_ANY_ARGS)
            for tool_def in self._tool_defs
        }

    async def call_tool(self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any], tool: ToolsetTool[Any]) -> Any:
        result = await self.call(name, tool_args)
        if self.on_call is not None:
            await self.on_call(ctx.deps, name, tool_args, result)
        return result

    # ---- raw calls (also used by the Team for log_event, pay, decide_approval) ----

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        if self._session is None:
            raise RuntimeError("MCPToolset is not connected; use `async with`.")
        result = await self._session.call_tool(name, arguments or {})
        text = "".join(getattr(part, "text", "") or "" for part in result.content)
        if result.is_error:
            return {"error": text.strip() or f"{name} failed"}
        # FastMCP puts the real value in structured_content: a dict for a
        # record, {"result": [...]} for a list (even an empty one, whose text
        # content is empty). The text is only a fallback.
        if result.structured_content is not None:
            return result.structured_content
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return text


def _input_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
    return dict(schema) if schema else {"type": "object", "properties": {}}
