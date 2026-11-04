#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 11 — the failover drill.
#
# Mirrors the Jenkins stage "Failover Drill". This is a REAL state change,
# not a routing trick:
#
#   1. the DR standby is warmed up (its MCP is started) — PROD keeps serving
#   2. the MCP READINESS PROBE asks the DR site what it can see of itself
#      and gates on the answer
#   3. the PROD MCP container is stopped  -> the PROD endpoint goes away
#   4. the DR MCP container is started   -> the DR endpoint answers
#
# The SAME image is now serving, but the answer identifies the DR host.
#
# Step 2 is the point of the whole exercise: a standby that cannot hold the
# load is NEVER promoted. If the probe fails, the drill rolls back to the
# PROD-only posture and the step fails — production was never at risk.
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

# ---------------------------------------------------------------- 1. warm up --
# Bring the standby up WITHOUT touching PROD, so it can be health-checked
# while production is still serving.
ansible-playbook -i inventory.ini dr-warmup.yml

cd "${WORKDIR}"
echo ""
echo "===== DR READINESS PROBE (before any cutover) =====" | tee -a "${TRANSCRIPT}"

# ------------------------------------------------------- 2. the readiness gate --
if ! probe_dr_readiness \
        "http://${DR_HOST}:${MCP_PORT}${MCP_PATH}" \
        "${DR_HOST}" \
        "${DR_EXPECT}" \
        "${FULL_IMAGE}"; then

    echo ""
    echo "${C_RED}BLOCKED: the DR site is not fit to take over. Rolling back.${C_RESET}" | tee -a "${TRANSCRIPT}"
    echo ""

    # Roll back to the PROD-only posture: DR goes down, PROD stays up.
    cd "${WORKDIR}/ansible"
    ansible-playbook -i inventory.ini failback.yml || true
    cd "${WORKDIR}"

    note "PROD is still serving — production was never at risk."
    exit 1
fi

echo "" | tee -a "${TRANSCRIPT}"

# ---------------------------------------------------------------- 3. fail over --
cd "${WORKDIR}/ansible"
ansible-playbook -i inventory.ini failover.yml

cd "${WORKDIR}"
echo ""
echo "===== FAILOVER: DR is now serving =====" | tee -a "${TRANSCRIPT}"

# --------------------------------------------------------------- 4. prove it --
verify_mcp \
    "http://${DR_HOST}:${MCP_PORT}${MCP_PATH}" \
    "${DR_HOST}" \
    "${DR_EXPECT}" \
    "${FULL_IMAGE}" \
    --call get_listening_ports \
    --assert "get_listening_ports=${MCP_PORT}" \
    || { echo "${C_RED}BLOCKED: after failover the DR endpoint did not answer as ${DR_EXPECT}${C_RESET}"; exit 1; }

echo "" | tee -a "${TRANSCRIPT}"

echo ""
note "the PROD endpoint is now down. Ask it anything — it will not answer:"
curl -s -o /dev/null -w "  http://${PROD_HOST}:${MCP_PORT}${MCP_PATH} -> HTTP %{http_code}\n" \
    --connect-timeout 5 "http://${PROD_HOST}:${MCP_PORT}${MCP_PATH}" || echo "  connection refused (expected)"

step_end 11
echo ""
note "next: step-12-failback.sh"
