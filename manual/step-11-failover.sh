#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 11 — the failover drill.
#
# Mirrors the Jenkins stage "Failover Drill". This is a REAL state change,
# not a routing trick:
#
#   1. the PROD MCP container is stopped  -> the PROD endpoint goes away
#   2. the DR MCP container is started   -> the DR endpoint answers
#
# The SAME image is now serving, but the answer identifies the DR host.
#
#   ./manual/step-11-failover.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 11 — failover: stand PROD down, promote DR"
step_start 11 "the PROD site goes down, the DR site takes over"

state_load
require_state FULL_IMAGE

ensure_ansible_on_path

cd "${WORKDIR}/ansible"
export ANSIBLE_PRIVATE_KEY_FILE="${HOME}/.ssh/id_rhai108_rsa"

ansible-playbook -i inventory.ini failover.yml

cd "${WORKDIR}"
echo ""
echo "===== FAILOVER: DR is now serving =====" | tee -a "${TRANSCRIPT}"

verify_mcp \
    "http://${DR_HOST}:${MCP_PORT}${MCP_PATH}" \
    "${DR_HOST}" \
    "${DR_EXPECT}" \
    "${FULL_IMAGE}" \
    || { echo "${C_RED}BLOCKED: after failover the DR endpoint did not answer as ${DR_EXPECT}${C_RESET}"; exit 1; }

echo "" | tee -a "${TRANSCRIPT}"

echo ""
note "the PROD endpoint is now down. Ask it anything — it will not answer:"
curl -s -o /dev/null -w "  http://${PROD_HOST}:${MCP_PORT}${MCP_PATH} -> HTTP %{http_code}\n" \
    --connect-timeout 5 "http://${PROD_HOST}:${MCP_PORT}${MCP_PATH}" || echo "  connection refused (expected)"

step_end 11
echo ""
note "next: step-12-failback.sh"
