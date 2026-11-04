#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 07 — the FINAL Trivy gate.
#
# Mirrors the Jenkins stage "Trivy Final Scan". This is the hard gate, and
# it runs on the image that is about to be exported and deployed to BOTH
# sites. It has to be clean:
#
#   * no HIGH/CRITICAL library CVEs
#   * no CRITICAL OS CVEs
#
#   ./manual/step-07-scan-trivy-final.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 07 — the final Trivy gate"
step_start 07 "re-scanning the remediated image"

state_load
require_state REMEDIATED_IMAGE

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"

ensure_podman_socket
SOCK=$(podman_sock)
TRIVY_RC=0
TRIVY_OS_RC=0

echo "--- 1/2 library CVEs ---"
podman run --rm --name mcp-trivy-final-manual \
    --network host --security-opt label=disable \
    -v "${SOCK}:/var/run/docker.sock" \
    -v trivy-cache:/root/.cache/trivy \
    -e TRIVY_DB_REPOSITORY=docker.io/aquasec/trivy-db:2 \
    "${TRIVY_IMAGE}" \
    image --scanners vuln \
        --pkg-types library \
        --severity HIGH,CRITICAL \
        --exit-code 1 \
        --format table \
        "$(local_ref "${REMEDIATED_IMAGE}")" \
        > "${REPORT_DIR}/trivy-final-report.txt" 2>&1 || TRIVY_RC=$?

cat "${REPORT_DIR}/trivy-final-report.txt"
note "trivy (final, library) exit code: ${TRIVY_RC}"
echo ""

echo "--- 2/2 OS packages ---"
podman run --rm --name mcp-trivy-final-os-manual \
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
        "$(local_ref "${REMEDIATED_IMAGE}")" \
        > "${REPORT_DIR}/trivy-final-os-report.txt" 2>&1 || TRIVY_OS_RC=$?

cat "${REPORT_DIR}/trivy-final-os-report.txt"
note "trivy (final, OS) exit code: ${TRIVY_OS_RC}"
echo ""

if [ "${TRIVY_RC}" -ne 0 ]; then
    echo "${C_RED}BLOCKED: the remediated image still has a HIGH/CRITICAL library CVE${C_RESET}"
    echo "        see ${REPORT_DIR}/trivy-final-report.txt"
    exit 1
fi

if [ "${TRIVY_OS_RC}" -ne 0 ]; then
    echo "${C_RED}BLOCKED: the remediated image has a CRITICAL OS vulnerability${C_RESET}"
    echo "        see ${REPORT_DIR}/trivy-final-os-report.txt"
    exit 1
fi

echo "${C_GREEN}Trivy OK on the shipped image: no HIGH/CRITICAL library CVEs, no CRITICAL OS CVEs.${C_RESET}"

step_end 07
echo ""
note "next: step-08-export-artifact.sh"
