"""Authenticated FastMCP CLI: discovery or one explicit tool call."""

import argparse
import asyncio
import json
import os
import sys

import httpx
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp import McpError

from mcps.trackflow.config import validate_url


async def run_client(tool: str | None, arguments: dict[str, object]) -> None:
    url = os.environ.get("TRACKFLOW_MCP_URL")
    token = os.environ.get("TRACKFLOW_MCP_TOKEN")
    if not url or not token:
        raise ValueError("Set TRACKFLOW_MCP_URL and TRACKFLOW_MCP_TOKEN; tokens are never CLI arguments.")
    validate_url(url)
    async with Client(url, auth=token, name="trackflow-fastmcp-client", timeout=10) as client:
        if tool is None:
            tools = await client.list_tools()
            print(json.dumps([item.model_dump(mode="json", by_alias=True) for item in tools], indent=2))
        else:
            result = await client.call_tool(tool, arguments, raise_on_error=False)
            print(json.dumps({
                "isError": result.is_error,
                "structuredContent": result.structured_content,
                "content": [item.model_dump(mode="json") for item in result.content],
            }, indent=2))
            if result.is_error:
                raise ToolError("MCP tool call failed; see the error code above.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", help="Omit to list tools and schemas.")
    parser.add_argument("--arguments", default="{}", help="JSON object. Do not include secrets.")
    args = parser.parse_args()
    try:
        arguments = json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("--arguments must be a JSON object.")
        asyncio.run(run_client(args.tool, arguments))
    except (ValueError, RuntimeError, httpx.HTTPError, McpError, ToolError) as exc:
        print(f"MCP client failed ({type(exc).__name__}); check configuration, authentication and server logs.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
