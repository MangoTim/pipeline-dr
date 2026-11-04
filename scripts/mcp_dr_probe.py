#!/usr/bin/env python3
"""DR readiness probe.

Asks a deployed MCP server what it can see about a host, and decides whether
that host is fit to take over production.

This is the gate that makes the MCP load-bearing in the failover drill. Until
now the pipeline used the MCP only as a hostname oracle — "which site is
answering?". That proves the DR promotion happened, but it says nothing about
whether DR could actually carry PROD's load.

The probe calls four tools in ONE session against the target host:

    get_system_information   -> is this the site we think it is?
    get_cpu_information      -> how many cores would we be failing over to?
    get_memory_information   -> how much RAM is actually free?
    get_disk_usage           -> how much disk is actually free?

and then gates on the numbers. A DR site that cannot hold the load is NOT
promoted, and the pipeline fails with the site still serving production.

Runs INSIDE the built image (it already ships fastmcp), so the probe tests
the exact artifact that was deployed.

Exit code 0 = the site is ready, 1 = it is not.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys

GIB = 1024 ** 3
MIB = 1024 ** 2

# Only these are real, persistent filesystems. tmpfs / devtmpfs / overlay are
# RAM-backed or synthetic and would otherwise dominate the "tightest disk"
# calculation with a 0-byte mount.
REAL_FS = {"xfs", "ext4", "ext3", "ext2", "btrfs"}

# A filesystem smaller than this is not worth failing over for.
MIN_FS_SIZE = 1 * GIB


def _as_dict(result) -> dict:
    """Best-effort extraction of the tool's structured payload.

    FastMCP may hand it back as `structured_content` (a dict), as `data` (a
    deserialised model), or only as text blocks — in which case the first
    block is the JSON encoding of the same object.
    """
    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and structured:
        return structured

    data = getattr(result, "data", None)
    if data is not None:
        if isinstance(data, dict):
            return data
        dump = getattr(data, "model_dump", None)
        if callable(dump):
            try:
                return dump(by_alias=True)
            except TypeError:
                return dump()
        try:
            return dict(data)
        except (TypeError, ValueError):
            pass

    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    return {}


def _pick(d: dict, *names, default=None):
    """Read the first key that is present."""
    for name in names:
        if name in d and d[name] not in (None, ""):
            return d[name]
    return default


def _to_int(value) -> int:
    """Turn a size into bytes.

    `findmnt --df --json` reports sizes as human strings ("85.4G", "1014M",
    "0", null) and it counts in 1024-based units, so "G" means GiB. `free`
    reports plain byte counts. Both shapes have to be accepted.
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text or text == "-":
        return 0
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]i?B?|B)?", text, re.IGNORECASE)
    if not m:
        return 0
    number = float(m.group(1))
    unit = (m.group(2) or "B").upper()
    if unit.endswith("IB"):
        unit = unit[0]
    elif unit.endswith("B") and unit != "B":
        unit = unit[0]
    factor = {"B": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3,
              "T": 1024 ** 4, "P": 1024 ** 5}.get(unit, 1)
    return int(number * factor)


def _pct(free: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return free * 100.0 / total


def _fmt_bytes(value: int) -> str:
    for unit, size in (("GiB", GIB), ("MiB", MIB)):
        if value >= size:
            return f"{value / size:.1f} {unit}"
    return f"{value} B"


async def probe(url: str, target: str, expect: str,
                min_cores: int, min_mem_pct: float, min_disk_pct: float) -> int:
    from fastmcp import Client

    print(f"[probe] endpoint        : {url}")
    print(f"[probe] inspecting host : {target}")
    print(f"[probe] expecting        : {expect}")
    print()

    failures: list[str] = []

    async with Client(url) as client:
        async def call(name: str) -> dict:
            result = await client.call_tool(name, {"host": target})
            return _as_dict(result)

        sysinfo = await call("get_system_information")
        cpu = await call("get_cpu_information")
        memory = await call("get_memory_information")
        disk = await call("get_disk_usage")

    # --- identity ----------------------------------------------------------
    hostname = str(_pick(sysinfo, "hostname", default=""))
    print(f"[probe] hostname        : {hostname}")
    print(f"[probe] os              : {_pick(sysinfo, 'os_name', default='?')} "
          f"{_pick(sysinfo, 'os_version', default='')}".rstrip())
    print(f"[probe] kernel          : {_pick(sysinfo, 'kernel', default='?')}")
    print(f"[probe] uptime          : {_pick(sysinfo, 'uptime', default='?')}")
    print()

    if expect and hostname.lower() != expect.lower():
        failures.append(f"the endpoint reports {hostname!r}, expected {expect!r}")

    # --- cpu ---------------------------------------------------------------
    cores = int(_pick(cpu, "logical_cores", "logicalCores", default=0) or 0)
    phys = int(_pick(cpu, "physical_cores", "physicalCores", default=0) or 0)
    load1 = _pick(cpu, "load_avg_1m", "loadAvg1m", default=0) or 0
    print("[probe] CPU")
    print(f"[probe]   logical cores : {cores}")
    print(f"[probe]   physical cores: {phys}")
    print(f"[probe]   model         : {_pick(cpu, 'model', default='?')}")
    print(f"[probe]   load (1m)     : {load1}")
    print()
    if cores < min_cores:
        failures.append(f"only {cores} logical cores, need at least {min_cores}")

    # --- memory ------------------------------------------------------------
    ram = _pick(memory, "ram", default={}) or {}
    ram_total = _to_int(_pick(ram, "total", default=0))
    ram_avail = _to_int(_pick(ram, "available", "free", default=0))
    mem_pct = _pct(ram_avail, ram_total)
    swap = _pick(memory, "swap", default=None) or {}
    swap_total = _to_int(_pick(swap, "total", default=0))
    swap_free = _to_int(_pick(swap, "free", default=0))
    print("[probe] memory")
    print(f"[probe]   RAM total     : {_fmt_bytes(ram_total)}")
    print(f"[probe]   RAM available : {_fmt_bytes(ram_avail)}  ({mem_pct:.1f} % free)")
    print(f"[probe]   swap          : {_fmt_bytes(swap_free)} free of {_fmt_bytes(swap_total)}")
    print()
    if mem_pct < min_mem_pct:
        failures.append(f"only {mem_pct:.1f} % memory free, need at least {min_mem_pct:.1f} %")

    # --- disk --------------------------------------------------------------
    filesystems = _pick(disk, "filesystems", default=[]) or []
    real: list[tuple[str, str, int, int, int]] = []
    pseudo = 0
    for fs in filesystems:
        fstype = str(_pick(fs, "fstype", default="") or "")
        target_mnt = str(_pick(fs, "target", default="") or "")
        size = _to_int(_pick(fs, "size", default=0))
        used = _to_int(_pick(fs, "used", default=0))
        avail = _to_int(_pick(fs, "avail", default=0))
        if fstype in REAL_FS and size >= MIN_FS_SIZE:
            real.append((target_mnt, fstype, size, used, avail))
        else:
            pseudo += 1

    print("[probe] disk")
    tightest_pct = 100.0
    tightest = ""
    for target_mnt, fstype, size, used, avail in real:
        pct = _pct(avail, size)
        print(f"[probe]   {target_mnt:<12} {fstype:<6} {_fmt_bytes(size):>10} total  "
              f"{_fmt_bytes(used):>10} used  {_fmt_bytes(avail):>10} free  ({pct:5.1f} % free)")
        if pct < tightest_pct:
            tightest_pct = pct
            tightest = f"{target_mnt} ({fstype})"
    if pseudo:
        print(f"[probe]   ({pseudo} pseudo filesystems skipped — tmpfs, overlay, ... — "
              f"only real ones are gated)")
    print()
    if not real:
        failures.append("no real filesystem was found to measure")
    elif tightest_pct < min_disk_pct:
        failures.append(
            f"the tightest filesystem {tightest} has only {tightest_pct:.1f} % free, "
            f"need at least {min_disk_pct:.1f} %")

    # --- verdict -----------------------------------------------------------
    print()
    if failures:
        print("[probe] NOT READY for failover:")
        for f in failures:
            print(f"[probe]   - {f}")
        return 1

    print(f"[probe] READY: {hostname} has {cores} cores, "
          f"{mem_pct:.1f} % memory free, {tightest_pct:.1f} % disk free "
          f"(tightest: {tightest})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="MCP endpoint, e.g. http://192.168.147.104:8095/mcp")
    parser.add_argument("--target", required=True, help="host the MCP should inspect")
    parser.add_argument("--expect", default="", help="hostname the site must report")
    parser.add_argument("--min-cpu-cores", type=int, default=1)
    parser.add_argument("--min-free-mem-percent", type=float, default=0.0)
    parser.add_argument("--min-free-disk-percent", type=float, default=0.0)
    args = parser.parse_args()

    try:
        return asyncio.run(probe(args.url, args.target, args.expect,
                                 args.min_cpu_cores, args.min_free_mem_percent,
                                 args.min_free_disk_percent))
    except Exception as exc:  # noqa: BLE001 - a failed probe must not crash the stage silently
        print(f"[probe] FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
