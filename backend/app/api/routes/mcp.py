from __future__ import annotations

from fastmcp import FastMCP
from mcp.types import ToolAnnotations


mcp = FastMCP(
    'AlphaPredator',
    instructions=(
        'A-share intelligent stock analysis workstation. '
        'Current MCP stage only provides basic connectivity and does not expose business tools.'
    ),
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_alpha_predator_info() -> dict[str, str]:
    """Return basic MCP service information for connectivity verification."""
    return {
        'name': 'AlphaPredator',
        'mcp_status': 'ok',
        'capabilities_stage': 'F05a-basic-mcp',
    }
