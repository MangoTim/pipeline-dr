#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 12 — fail back to PROD.
#
# Mirrors the Jenkins stage "Failback". The exact inverse of step 11:
#
#   1. the DR MCP container is stopped
#   2. the PROD MCP container is started again
#
# After this the PROD endpoint answers again.
#
#   ./manual/step-12-failback.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 12 — failback: return to PROD"
step_start 12 "the DR site goes down, PROD comes back"

state_load
require_state FULL_IMAGE

ensure_ansible_on_path

cd "${WORKDIR}/ansible"
export ANSIBLE_PRIVATE_KEY_FILE="${HOME}/.ssh/id_rhai108_rsa"

ansible-playbook -i inventory.ini failback.yml

cd "${WORKDIR}"
echo ""
echo "===== FAILBACK: PROD is serving again =====" | tee -a "${TRANSCRIPT}"

verify_mcp \
    "http://${PROD_HOST}:${MCP_PORT}${MCP_PATH}" \
    "${PROD_HOST}" \
    "${PROD_EXPECT}" \
    "${FULL_IMAGE}" \
    || { echo "${C_RED}BLOCKED: after failback the PROD endpoint did not answer as ${PROD_EXPECT}${C_RESET}"; exit 1; }

echo "" | tee -a "${TRANSCRIPT}"

step_end 12
echo ""
note "next: step-13-show-same-artifact.sh"
