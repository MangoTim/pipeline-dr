#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 05 — the BASELINE Trivy scan.
#
# Mirrors the Jenkins stages "Trivy Scan" and "Trivy Scan (App)".
#
# For the MCP server this scan is deliberately NOT the gate on the library
# findings — it is the INPUT to the remediation step. The gate on what
# actually ships is step 07.
#
# Three scans run here:
#   1. the Python dependency tree of the MCP server, as JSON, because the
#      remediation step parses it;
#   2. the OS packages of the MCP base image (UBI 10 minimal) — CRITICAL is
#      the gate, and it is checked right now;
#   3. the OS packages of the APP image (Debian trixie) — CRITICAL is the
#      gate. The app has NO pip dependencies (it is the Python standard
#      library and three source files), so there is no library tree to
#      report and, more importantly, NO remediation step: there is nothing
#      to upgrade. Its Dockerfile carries an `apt-get upgrade`, so the gate
#      simply proves the Debian package set was patched at build time.
#
#   ./manual/step-05-scan-trivy.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 05 — the baseline Trivy scan"

state_load
require_state BASE_IMAGE APP_BASE_IMAGE

step_start 05 "scanning ${BASE_IMAGE}"

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"

ensure_podman_socket
SOCK=$(podman_sock)
TRIVY_RC=0
TRIVY_OS_RC=0

# ------------------------------------------------------------- libraries ----
echo "--- 1/3 library CVEs (the Python dependency tree) ---"
podman run --rm --name mcp-trivy-manual \
    --network host --security-opt label=disable \
    -v "${SOCK}:/var/run/docker.sock" \
    -v trivy-cache:/root/.cache/trivy \
    -e TRIVY_DB_REPOSITORY=docker.io/aquasec/trivy-db:2 \
    "${TRIVY_IMAGE}" \
    image --scanners vuln \
        --pkg-types library \
        --severity HIGH,CRITICAL \
        --exit-code 1 \
        --format json \
        "$(local_ref "${BASE_IMAGE}")" \
        > "${REPORT_DIR}/trivy-report.json" 2> "${REPORT_DIR}/trivy-scan.err" || TRIVY_RC=$?

python3 - "${REPORT_DIR}/trivy-report.json" > "${REPORT_DIR}/trivy-report.txt" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    report = json.load(fh)

for result in report.get("Results") or []:
    findings = result.get("Vulnerabilities") or []
    print("Target: %s (%s)" % (result.get("Target"), result.get("Class")))
    if not findings:
        print("    no HIGH/CRITICAL findings")
    for vuln in findings:
        print("    %-24s %-14s %-9s -> %s" % (
            vuln.get("PkgName"),
            vuln.get("InstalledVersion"),
            vuln.get("Severity"),
            vuln.get("FixedVersion") or "NO FIX PUBLISHED",
        ))
    print("")
PY

cat "${REPORT_DIR}/trivy-report.txt"
note "trivy (library) exit code: ${TRIVY_RC}"
echo ""

# ----------------------------------------------------------- OS packages ----
echo "--- 2/3 OS packages of the base image (CRITICAL is the gate) ---"
podman run --rm --name mcp-trivy-os-manual \
    --network host --security-opt label=disable \
    -v "${SOCK}:/var/run/docker.sock" \
    -v trivy-cache:/root/.cache/trivy \
    -e TRIVY_DB_REPOSITORY=docker.io/aquasec/trivy-db:2 \
    "${TRIVY_IMAGE}" \
    image --scanners vuln \
        --pkg-types os \
        --severity CRITICAL \
        --exit-code 1 \
        --format table \
        "$(local_ref "${BASE_IMAGE}")" \
        > "${REPORT_DIR}/trivy-os-report.txt" 2>&1 || TRIVY_OS_RC=$?

cat "${REPORT_DIR}/trivy-os-report.txt"
note "trivy (OS packages) exit code: ${TRIVY_OS_RC}"
echo ""

if [ "${TRIVY_OS_RC}" -ne 0 ]; then
    echo "${C_RED}BLOCKED: Trivy reported a CRITICAL OS vulnerability in the MCP image${C_RESET}"
    echo "        see ${REPORT_DIR}/trivy-os-report.txt"
    exit 1
fi

# ------------------------------------------------ the app's OS packages ------
# The app has no library tree and no remediation step, so this single scan
# IS the gate on the app image.
TRIVY_APP_OS_RC=0
echo "--- 3/3 OS packages of the app image (CRITICAL is the gate) ---"
podman run --rm --name app-trivy-os-manual \
    --network host --security-opt label=disable \
    -v "${SOCK}:/var/run/docker.sock" \
    -v trivy-cache:/root/.cache/trivy \
    -e TRIVY_DB_REPOSITORY=docker.io/aquasec/trivy-db:2 \
    "${TRIVY_IMAGE}" \
    image --scanners vuln \
        --pkg-types os \
        --severity CRITICAL \
        --exit-code 1 \
        --format table \
        "$(local_ref "${APP_BASE_IMAGE}")" \
        > "${REPORT_DIR}/trivy-app-os-report.txt" 2>&1 || TRIVY_APP_OS_RC=$?

cat "${REPORT_DIR}/trivy-app-os-report.txt"
note "trivy (app, OS packages) exit code: ${TRIVY_APP_OS_RC}"
echo ""

if [ "${TRIVY_APP_OS_RC}" -ne 0 ]; then
    echo "${C_RED}BLOCKED: Trivy reported a CRITICAL OS vulnerability in the app image${C_RESET}"
    echo "        see ${REPORT_DIR}/trivy-app-os-report.txt"
    exit 1
fi

note "the library findings are NOT a gate here — step 06 remediates them"
note "and step 07 re-scans the remediated image."
note "the app image is clean already: it has no library dependencies, so"
note "there is nothing to remediate and no final re-scan to do."

step_end 05
echo ""
note "next: step-06-remediate.sh"
