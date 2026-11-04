#!/usr/bin/env python3
"""Verify a deployed RHEL MCP server.

Runs INSIDE the built image (which already ships fastmcp), so it tests the
exact artifact that was deployed and no extra dependency has to be installed
on the CI agent.

It performs a real MCP session over streamable HTTP:

    initialize -> tools/list -> tools/call get_system_information(host=...)

and then asserts that the answer identifies the EXPECTED site. Because both
sites run the same image and the MCP inspects the host it is deployed on, the
hostname in the answer is the proof of which site is actually serving.

Exit code 0 = pass, 1 = fail.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _flatten(result) -> str:
    """Best-effort rendering of a tool result as text.

    The MCP tool returns a structured object (SystemInfo), so the payload can
    arrive as structured content, as parsed data, or as plain text blocks
    depending on the client and the server version. Look at all of them.

    The same payload usually shows up in more than one of those places, so
    identical renderings are collapsed to keep the transcript readable.
    """
    chunks: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        key = text.strip()
        if key and key not in seen:
            seen.add(key)
            chunks.append(text)

    content = getattr(result, "content", None)
    if content:
        for block in content:
            text = getattr(block, "text", None)
            if text:
                add(text)

    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if structured is not None:
        add(json.dumps(structured, indent=2, default=str))

    data = getattr(result, "data", None)
    if data is not None:
        add(json.dumps(data, indent=2, default=str))

    if not chunks:
        chunks.append(repr(result))

    return "\n".join(chunks)


async def verify(url: str, target: str, expect: str, tool: str) -> int:
    from fastmcp import Client

    print(f"[verify] endpoint       : {url}")
    print(f"[verify] inspecting host: {target}")
    print(f"[verify] expecting       : {expect}")
    print()

    async with Client(url) as client:
        tools = await client.list_tools()
        names = sorted(t.name for t in tools)
        print(f"[verify] tools exposed ({len(names)}): {', '.join(names)}")
        print()

        if tool not in names:
            print(f"[verify] FAIL: tool {tool!r} is not exposed by {url}")
            return 1

        result = await client.call_tool(tool, {"host": target})
        payload = _flatten(result)

        print(f"[verify] {tool}(host={target}) returned:")
        print(payload)
        print()

        if expect.lower() not in payload.lower():
            print(f"[verify] FAIL: {expect!r} does not appear in the response")
            print("[verify] the endpoint is NOT serving the expected site")
            return 1

        print(f"[verify] PASS: {url} is serving {expect}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="MCP endpoint, e.g. http://192.168.147.105:8095/mcp")
    parser.add_argument("--target", required=True, help="host the MCP should inspect")
    parser.add_argument("--expect", required=True, help="hostname expected in the answer")
    parser.add_argument("--tool", default="get_system_information")
    args = parser.parse_args()

    try:
        return asyncio.run(verify(args.url, args.target, args.expect, args.tool))
    except Exception as exc:  # noqa: BLE001 - a failed check must not crash the stage silently
        print(f"[verify] FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
