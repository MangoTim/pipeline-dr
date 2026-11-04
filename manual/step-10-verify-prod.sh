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
# TWO facts are proven here, in one MCP session:
#
#   1. get_system_information -> the endpoint answers as server-gateway
#      .example.com, so the PROD site is the one serving.
#   2. get_listening_ports    -> port 8095 on THAT host is held by the
#      linux-mcp-server process. This is what makes fact 1 believable: the
#      MCP did not return a canned string, it really reached the host's
#      kernel over SSH and read its socket table.
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
    --call get_listening_ports \
    --assert "get_listening_ports=${MCP_PORT}" \
    || { echo "${C_RED}BLOCKED: the PROD endpoint did not answer as ${PROD_EXPECT}${C_RESET}"; exit 1; }

echo "" | tee -a "${TRANSCRIPT}"

step_end 10
echo ""
note "next: step-11-failover.sh"
