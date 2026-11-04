#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 10 — verify the PROD site.
#
# Mirrors the Jenkins stage "Verify PROD". The verify client runs INSIDE the
# image that was just built, so it tests the exact artifact that was
# shipped — and it needs no extra dependency on the controller, because the
# image already contains fastmcp.
#
# The script is piped into the container on STDIN and read by `python -`.
# It is NOT bind-mounted: podman runs on the host and cannot see a path
# inside a container.
#
#   ./manual/step-10-verify-prod.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 10 — verify PROD"
step_start 10 "asking the PROD endpoint who it is"

state_load
require_state FULL_IMAGE

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"
: > "${TRANSCRIPT}"

echo "===== PROD verification =====" | tee -a "${TRANSCRIPT}"

verify_mcp \
    "http://${PROD_HOST}:${MCP_PORT}${MCP_PATH}" \
    "${PROD_HOST}" \
    "${PROD_EXPECT}" \
    "${FULL_IMAGE}" \
    || { echo "${C_RED}BLOCKED: the PROD endpoint did not answer as ${PROD_EXPECT}${C_RESET}"; exit 1; }

echo "" | tee -a "${TRANSCRIPT}"

step_end 10
echo ""
note "next: step-11-failover.sh"
