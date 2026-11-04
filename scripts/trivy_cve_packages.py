#!/usr/bin/env python3
"""Turn a Trivy JSON report into a pip upgrade instruction list.

The pipeline scans the built image with Trivy, then remediates the HIGH and
CRITICAL library CVEs it finds by upgrading the affected Python packages
inside the image. This script is the bridge between the two: it reads the
Trivy JSON report and prints one `name==version` pair per line, which is
exactly the argument list `pip install --upgrade` expects.

    trivy_cve_packages.py trivy-report.json
    -> authlib==1.9.1
       pyjwt==2.14.0

Only packages that are actually INSTALLED in the image are listed. Trivy also
reports the packages that pip bundles inside its own `_vendor` directory
(urllib3, msgpack, requests, ...) — those are not importable by the
application, they disappear when pip is removed from the runtime venv, and
there is nothing to upgrade. Passing the image's own `pip list` output with
--installed keeps them out of the upgrade list.

Findings with no published fix are reported on stderr and make the script
exit 3, so the pipeline fails loudly instead of shipping an image it could
not clean.
"""

import argparse
import json
import sys

EXIT_UNREMEDIABLE = 3


def normalise(name):
    """PEP 503 normalisation, so `Authlib` and `auth-lib` both become auth-lib."""
    return name.strip().lower().replace("_", "-").replace(".", "-")


def read_installed(path):
    """Read `pip list --format=freeze` output into a set of normalised names."""
    installed = set()
    if not path:
        return installed
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or "==" not in line:
                continue
            name, _version = line.split("==", 1)
            installed.add(normalise(name))
    return installed


def collect(report, severities, want_class):
    """Return an ordered list of dicts for actionable findings.

    Ordered by name so the pip command line is stable between builds.
    """
    found = {}

    for result in report.get("Results") or []:
        if result.get("Class") != want_class:
            continue

        for vuln in result.get("Vulnerabilities") or []:
            severity = (vuln.get("Severity") or "").upper()
            if severity not in severities:
                continue

            name = vuln.get("PkgName") or ""
            if not name:
                continue

            key = normalise(name)
            entry = found.get(key)
            if entry is None:
                found[key] = {
                    "name": key,
                    "installed": vuln.get("InstalledVersion", ""),
                    "fixed": vuln.get("FixedVersion") or "",
                }
            elif (vuln.get("FixedVersion") or "") > entry["fixed"]:
                # A package can carry several CVEs with different fix versions.
                # The highest fix is the one that clears all of them.
                entry["fixed"] = vuln.get("FixedVersion") or ""

    return [found[k] for k in sorted(found)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="Trivy JSON report file")
    parser.add_argument(
        "--installed",
        help="file with `pip list --format=freeze` output of the image",
    )
    parser.add_argument(
        "--severity",
        default="HIGH,CRITICAL",
        help="comma separated severities to remediate (default: HIGH,CRITICAL)",
    )
    parser.add_argument(
        "--class",
        dest="cls",
        default="lang-pkgs",
        help="Trivy result class: lang-pkgs (library) or os-pkgs (OS)",
    )
    args = parser.parse_args()

    severities = {s.strip().upper() for s in args.severity.split(",") if s.strip()}
    installed = read_installed(args.installed)

    with open(args.report, encoding="utf-8") as fh:
        report = json.load(fh)

    entries = collect(report, severities, args.cls)

    actionable = []
    unremediable = []
    skipped = []

    for entry in entries:
        name = entry["name"]
        fixed = entry["fixed"].strip()

        if installed and name not in installed:
            # Not importable by the application — pip's own vendored copies,
            # or a package Trivy saw in a layer that is not in the final
            # filesystem. Removing pip from the runtime venv removes the
            # vendored ones; the re-scan is what confirms it.
            skipped.append(name)
            continue

        if not fixed:
            unremediable.append(f"{name} {entry['installed']} (no fix published)")
            continue

        # Some ecosystems publish a list of fixed versions; the first is the
        # lowest acceptable one.
        fixed = fixed.split(",")[0].strip()
        actionable.append((name, fixed))

    for name, fixed in actionable:
        print(f"{name}=={fixed}")

    if skipped:
        print(
            "not installed in the image (pip's vendored copies or a removed "
            f"package), not upgraded: {', '.join(skipped)}",
            file=sys.stderr,
        )

    if unremediable:
        for item in unremediable:
            print(f"NO FIX AVAILABLE: {item}", file=sys.stderr)
        return EXIT_UNREMEDIABLE

    if not actionable:
        print(
            f"no actionable {args.cls} findings at severity {args.severity}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
