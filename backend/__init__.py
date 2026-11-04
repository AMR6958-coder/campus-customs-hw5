"""Campus Customs back end: the five-agent team that runs the shop.

Modules
- config.py        settings from backend/.env (Portkey key and URL, the one model, MCP URL, limits)
- llm.py           get_model(): gpt-6-luna through the Portkey gateway, built once, used by every agent
- mcp_toolset.py   a PydanticAI toolset over the MCP server (every shop tool becomes an agent tool)
- models.py        the data types: agent names, triage plan, Boss decision, run events, shared deps
- prompts/         one instructions file per agent, plus shared.md that every agent gets first
- agents/          one file per agent (Boss, Inventory, Accounting, Facilities, Customer Service)
- team.py          the Team: builds the agents, owns the MCP connection, delegation, the run loop
- run.py           command line: triage the board, work one ticket, or run the whole board

The FastAPI app (board, feed, approvals endpoints) is the next build step.
"""
