"""Attach the (forked) Fivetran MCP server as an ADK toolset.

Only the tools SendGuard needs are exposed via tool_filter -- the full server
has 80 tools, which would bloat the model's context and invite misuse.
"""

import os
from pathlib import Path

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_SERVER = REPO_ROOT / "fivetran-mcp" / "server.py"

SENDGUARD_TOOLS = [
    "list_connections",
    "get_connection_details",
    "sync_connection",
    "resync_connection",
    "get_connection_schema_config",
    "list_activation_syncs",
    "trigger_activation_sync",
    "get_activation_sync_run",
]


def make_fivetran_toolset() -> McpToolset:
    import sys
    env = {
        "FIVETRAN_API_KEY": os.getenv("FIVETRAN_API_KEY", ""),
        "FIVETRAN_API_SECRET": os.getenv("FIVETRAN_API_SECRET", ""),
        "FIVETRAN_ALLOW_WRITES": os.getenv("FIVETRAN_ALLOW_WRITES", "true"),
        "FIVETRAN_ACTIVATIONS_TOKEN": os.getenv("FIVETRAN_ACTIVATIONS_TOKEN", ""),
    }
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[str(MCP_SERVER)],
                env=env,
            ),
            timeout=60,
        ),
        tool_filter=SENDGUARD_TOOLS,
    )
