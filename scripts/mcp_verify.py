#!/usr/bin/env python3
"""Verify a deployed RHEL MCP server.

Runs INSIDE the built image (which already ships fastmcp), so it tests the
exact artifact that was deployed and no extra dependency has to be installed
on the CI agent.

It performs a real MCP session over streamable HTTP:

    initialize -> tools/list -> tools/call get_system_information(host=...)
                -> tools/call <every extra tool>   (optional)
                -> assert the answers

and then asserts that the answer identifies the EXPECTED site. Because both
sites run the same image and the MCP inspects the host it is deployed on, the
hostname in the answer is the proof of which site is actually serving.

Extra tools
-----------
`--call` asks for further tools in the SAME session, so one connection proves
several things:

    --call get_listening_ports
    --call 'get_service_status:{"service_name":"sshd"}'

`--assert TOOL=SUBSTRING` adds a gate on one of those calls:

    --assert get_listening_ports=8095

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


def _first_text(result) -> str:
    """The plain-text rendering of a tool result.

    FastMCP reports the same payload three ways — a text block, the
    structured content and the repr of the deserialised model. All three are
    kept for the primary tool (that is the archived evidence format), but the
    extra tools only need the readable one.
    """
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            return text
    return _flatten(result)


def _parse_call(spec: str) -> tuple[str, dict]:
    """Split `--call` into a tool name and its arguments.

    'get_listening_ports'                -> ('get_listening_ports', {})
    'get_service_status:{"service_name": "sshd"}'
                                         -> ('get_service_status', {...})
    """
    name, sep, raw = spec.partition(":")
    name = name.strip()
    if not sep or not raw.strip():
        return name, {}
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"bad --call arguments for {name!r}: {exc}") from exc
    if not isinstance(args, dict):
        raise ValueError(f"--call arguments for {name!r} must be a JSON object")
    return name, args


async def verify(url: str, target: str, expect: str, tool: str,
                 calls: list[str], assertions: list[str]) -> int:
    from fastmcp import Client

    print(f"[verify] endpoint       : {url}")
    print(f"[verify] inspecting host: {target}")
    print(f"[verify] expecting       : {expect}")
    print()

    # tool -> rendered payload, for the assertions
    rendered: dict[str, str] = {}

    async with Client(url) as client:
        tools = await client.list_tools()
        names = sorted(t.name for t in tools)
        print(f"[verify] tools exposed ({len(names)}): {', '.join(names)}")
        print()

        wanted = [(tool, {"host": target})]
        for spec in calls:
            name, args = _parse_call(spec)
            # the host argument is what makes the MCP SSH to the right box
            args.setdefault("host", target)
            wanted.append((name, args))

        for name, args in wanted:
            if name not in names:
                print(f"[verify] FAIL: tool {name!r} is not exposed by {url}")
                return 1

            result = await client.call_tool(name, args)
            payload = _flatten(result)
            rendered[name] = payload

            shown = ", ".join(f"{k}={v}" for k, v in args.items())
            # the primary tool keeps the full archived rendering; the extra
            # tools only print the readable one
            body = payload if name == tool else _first_text(result)
            print(f"[verify] {name}({shown}) returned:")
            print(body)
            print()

        if expect.lower() not in rendered.get(tool, "").lower():
            print(f"[verify] FAIL: {expect!r} does not appear in the response")
            print("[verify] the endpoint is NOT serving the expected site")
            return 1

        for assertion in assertions:
            name, _, needle = assertion.partition("=")
            name = name.strip()
            needle = needle.strip()
            if name not in rendered:
                print(f"[verify] FAIL: assertion target {name!r} was never called")
                return 1
            if needle.lower() not in rendered[name].lower():
                print(f"[verify] FAIL: {name} did not report {needle!r}")
                print(f"[verify] payload was:\n{rendered[name]}")
                return 1
            print(f"[verify] PASS: {name} reports {needle!r}")

        print(f"[verify] PASS: {url} is serving {expect}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="MCP endpoint, e.g. http://192.168.147.105:8095/mcp")
    parser.add_argument("--target", required=True, help="host the MCP should inspect")
    parser.add_argument("--expect", required=True, help="hostname expected in the answer")
    parser.add_argument("--tool", default="get_system_information",
                        help="the tool that must report --expect (default: get_system_information)")
    parser.add_argument("--call", action="append", default=[], metavar="TOOL[:JSON]",
                        help="call another tool in the same session, e.g. get_listening_ports")
    parser.add_argument("--assert", action="append", default=[], dest="assertions",
                        metavar="TOOL=SUBSTRING",
                        help="extra gate: the tool's answer must contain SUBSTRING")
    args = parser.parse_args()

    try:
        return asyncio.run(verify(args.url, args.target, args.expect, args.tool,
                                   args.call, args.assertions))
    except Exception as exc:  # noqa: BLE001 - a failed check must not crash the stage silently
        print(f"[verify] FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
