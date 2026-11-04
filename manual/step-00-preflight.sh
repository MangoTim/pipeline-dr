#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 00 — preflight.
#
# Checks everything the later steps depend on, BEFORE anything is built:
# the tools, the two sites, the deploy key, the port and the credential.
# Nothing is changed here — this step only reports.
#
#   ./manual/step-00-preflight.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 00 — preflight checks"
step_start 00 "checking the tools, the two sites and the credential"

mkdir -p "${REPORT_DIR}"

note "working directory : ${WORKDIR}"
note "report directory  : ${REPORT_DIR}"
note "running as        : $(id -un) (uid $(id -u))"
echo ""

echo "--- tools ---"
for c in podman curl python3 gzip sha256sum tar ssh; do
    need_cmd "${c}"
    note "OK   ${c} -> $(command -v "${c}")"
done
ensure_ansible_on_path
note "OK   ansible-playbook -> $(command -v ansible-playbook)"
note "     $(ansible-playbook --version 2>/dev/null | head -1)"
echo ""

echo "--- the repository checkout ---"
[ -d "${WORKDIR}" ] || die "the checkout ${WORKDIR} does not exist"
[ -f "${WORKDIR}/Jenkinsfile" ] || die "${WORKDIR}/Jenkinsfile is missing"
[ -f "${WORKDIR}/scripts/mcp_verify.py" ] || die "${WORKDIR}/scripts/mcp_verify.py is missing"
[ -f "${WORKDIR}/scripts/trivy_cve_packages.py" ] || die "${WORKDIR}/scripts/trivy_cve_packages.py is missing"
[ -f "${WORKDIR}/ansible/inventory.ini" ] || die "${WORKDIR}/ansible/inventory.ini is missing"
note "OK   the checkout looks complete"
echo ""

echo "--- the deploy key ---"
KEY="${HOME}/.ssh/id_rhai108_rsa"
[ -r "${KEY}" ] || die "the pipeline SSH key ${KEY} is missing or unreadable"
note "OK   ${KEY}"
echo ""

echo "--- both sites, over the pipeline key ---"
( cd "${WORKDIR}/ansible" && ansible -i inventory.ini mcp_sites -m ping ) \
    || die "ansible could not reach one of the sites"
echo ""

echo "--- the MCP port on both sites ---"
for host in "${PROD_HOST}" "${DR_HOST}"; do
    if curl -s -o /dev/null --connect-timeout 5 "http://${host}:${MCP_PORT}${MCP_PATH}"; then
        note "OK   ${host}:${MCP_PORT} answers"
    else
        warn "${host}:${MCP_PORT} does not answer right now."
        warn "     That is expected before the first deploy — the sites come up in step 09."
    fi
done
echo ""

echo "--- the Aqua console credential ---"
if [ -f "${AQUA_ENV_FILE}" ]; then
    note "OK   ${AQUA_ENV_FILE} (not printed)"
else
    warn "${AQUA_ENV_FILE} is missing — step 04 (the Aqua gate) cannot run until it exists."
    warn "See manual/README.md for the one-liner that creates it."
fi
echo ""

echo "--- the podman API socket the scanners need ---"
ensure_podman_socket
note "OK   $(podman_sock)"
echo ""

step_end 00
echo ""
note "preflight done — next: step-01-fetch-source.sh"
