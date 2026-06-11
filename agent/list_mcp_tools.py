#!/usr/bin/env python3
"""Hello-world ADK + Fivetran MCP attachment test.

Spawns the cloned fivetran-mcp server over stdio via ADK's McpToolset and
prints every tool it exposes. Uses dummy credentials if real ones are not
set -- tool LISTING never calls the Fivetran API.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent  # noqa: F401  (proves agent construction works)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_DIR = REPO_ROOT / "fivetran-mcp"
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"


def make_toolset() -> McpToolset:
    env = {
        "FIVETRAN_API_KEY": os.getenv("FIVETRAN_API_KEY", "dummy-key-for-listing"),
        "FIVETRAN_API_SECRET": os.getenv("FIVETRAN_API_SECRET", "dummy-secret-for-listing"),
        "FIVETRAN_ALLOW_WRITES": os.getenv("FIVETRAN_ALLOW_WRITES", "true"),
    }
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=str(VENV_PY),
                args=[str(MCP_DIR / "server.py")],
                env=env,
            ),
            timeout=30,
        )
    )


async def main() -> None:
    toolset = make_toolset()
    # Hello-world agent construction with the toolset attached
    agent = Agent(
        name="sendguard_hello",
        model="gemini-3-flash-preview",
        instruction="You are a hello-world agent used to verify MCP attachment.",
        tools=[toolset],
    )
    print(f"agent '{agent.name}' constructed with MCP toolset attached")

    tools = await toolset.get_tools()
    print(f"\n{len(tools)} tools exposed by fivetran-mcp:\n")
    for t in sorted(tools, key=lambda t: t.name):
        desc = (t.description or "").split("\n")[0][:100]
        print(f"  {t.name:45s} {desc}")
    await toolset.close()


if __name__ == "__main__":
    asyncio.run(main())
