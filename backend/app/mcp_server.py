from __future__ import annotations

from fastmcp import FastMCP


mcp = FastMCP("AlphaPredator")
mcp_app = mcp.http_app(
    path="/",
    host_origin_protection=True,
    allowed_hosts=["127.0.0.1", "localhost", "::1"],
    allowed_origins=[
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ],
)
