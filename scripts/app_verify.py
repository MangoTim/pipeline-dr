#!/usr/bin/env python3
"""Verify the deployed Lunch Rolltable app.

Runs INSIDE the app image, so it tests the exact artifact that was shipped.
The image carries nothing but the Python standard library, which is enough:
the app's own status endpoint already returns everything as JSON.

    GET <url>/api/mcp/status
      -> {site: {...}, prod: {...}, dr: {...}, tools: [...], appVersion: ...}

The chain this checks is  page -> MCP -> host :

  * the page answers
  * the page reports the site role we expect
  * the page reports the hostname we expect — and that hostname came from
    the MCP, which got it over SSH from the host that is serving the page,
    so it identifies the site that is ACTUALLY serving
  * both cluster tiles are present

Exit code 0 = pass, 1 = fail.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def fetch(url: str, timeout: float):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"cannot reach {url}: {exc.reason}") from exc
    except OSError as exc:
        raise RuntimeError(f"cannot reach {url}: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{url} did not return JSON: {exc}") from exc


def describe(tile: dict) -> str:
    if tile.get("ok"):
        return f"{tile.get('hostname', '?')} (online)"
    return f"{tile.get('error', 'unreachable')}"


def verify(url: str, expect: str, role: str, peer_role: str, timeout: float) -> int:
    print(f"[app] endpoint       : {url}")
    print(f"[app] expecting site : {role} / {expect}")
    print()

    try:
        status = fetch(url, timeout=timeout)
    except RuntimeError as exc:
        print(f"[app] FAIL: {exc}")
        return 1

    site = status.get("site") or {}
    prod = status.get("prod") or {}
    dr = status.get("dr") or {}

    print(f"[app] page reports role     : {site.get('role')}")
    print(f"[app] page reports hostname : {site.get('hostname')}")
    print(f"[app] page talks to         : {site.get('mcpUrl')}")
    print(f"[app] MCP tools exposed     : {len(status.get('tools') or [])}")
    print(f"[app] app image version     : {status.get('appVersion')}")
    print(f"[app] cluster tiles         : PROD={describe(prod)} | DR={describe(dr)}")
    print()

    failures = []

    if not site.get("ok"):
        failures.append(f"the page cannot reach its own MCP: {site.get('error')}")

    if role and site.get("role") != role:
        failures.append(f"the page reports role {site.get('role')!r}, expected {role!r}")

    hostname = site.get("hostname") or ""
    if expect.lower() not in hostname.lower():
        failures.append(
            f"the page reports hostname {hostname!r}, expected it to contain {expect!r}")

    for name in ("prod", "dr"):
        if name not in status:
            failures.append(f"the page did not return the {name.upper()} cluster tile")

    if peer_role:
        peer = status.get(peer_role.lower()) or {}
        if not peer:
            failures.append(f"the page did not return the {peer_role} cluster tile")

    if failures:
        for failure in failures:
            print(f"[app] FAIL: {failure}")
        print("[app] the page is NOT serving the expected site")
        return 1

    print(f"[app] PASS: {url} is serving {role} ({expect})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True,
                        help="the app's status endpoint, e.g. http://192.168.147.105:8084/api/mcp/status")
    parser.add_argument("--expect", required=True,
                        help="hostname the page must report")
    parser.add_argument("--role", default="",
                        help="site role the page must report, PROD or DR")
    parser.add_argument("--peer", default="",
                        help="the peer site's role, so the peer tile is checked too")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="seconds to wait for the status endpoint")
    args = parser.parse_args()

    try:
        return verify(args.url, args.expect, args.role, args.peer, args.timeout)
    except Exception as exc:  # noqa: BLE001 - a failed check must not crash the stage silently
        print(f"[app] FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
