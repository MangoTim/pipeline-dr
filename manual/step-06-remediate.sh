#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 06 — security remediation.
#
# Mirrors the Jenkins stage "Security Remediation". The upstream image is
# built from a pinned commit, so its Python dependency tree is fixed — and
# that tree carries published CVEs. They are fixed HERE, inside the image,
# and the result is re-scanned with a hard gate in step 07. What ships is
# the remediated image.
#
# Two kinds of finding are handled:
#
#   1. the MCP's OWN dependencies — authlib, pyjwt, certifi, dnspython,
#      joserfc. These are upgraded in place to the version Trivy names as
#      the fix.
#
#   2. the copies that pip bundles inside its own _vendor directory —
#      urllib3, msgpack, setuptools. They are real files in the image, but
#      the MCP never imports them and there is no upstream fix to install.
#      pip has no business in a runtime virtualenv, so it is removed, and
#      its vendored copies go with it.
#
# The remediated image is a DERIVED build: FROM the upstream image, so
# every upstream layer, label, env var, user and entrypoint is preserved
# exactly. (`podman commit` would clobber the entrypoint.)
#
#   ./manual/step-06-remediate.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 06 — security remediation"
step_start 06 "fixing the HIGH/CRITICAL library CVEs inside the image"

state_load
require_state BASE_IMAGE REMEDIATED_IMAGE

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"

# --------------------------------------------- what is actually installed ---
note "the packages that are really installed and importable in the image:"
podman run --rm --pull=never --network host --security-opt label=disable \
    --entrypoint /opt/venvs/mcp/bin/python \
    "$(local_ref "${BASE_IMAGE}")" \
    -m pip list --format=freeze > "${REPORT_DIR}/pip-list.txt" 2>/dev/null

# Trivy also reports the packages pip keeps in its own _vendor directory;
# those are not in this list, so they are correctly left out of the
# upgrade list.
FIX_RC=0
python3 scripts/trivy_cve_packages.py \
    "${REPORT_DIR}/trivy-report.json" \
    --installed "${REPORT_DIR}/pip-list.txt" \
    > "${REPORT_DIR}/cve-fixes.txt" || FIX_RC=$?

echo ""
echo "--- packages to upgrade ---"
cat "${REPORT_DIR}/cve-fixes.txt"
echo ""

if [ "${FIX_RC}" -ne 0 ]; then
    if [ "${FIX_RC}" -eq 3 ]; then
        echo "${C_RED}BLOCKED: Trivy found a HIGH/CRITICAL library CVE with no published fix.${C_RESET}"
        echo "        It cannot be remediated automatically — the image must be"
        echo "        rebuilt from a newer upstream commit."
    else
        echo "${C_RED}BLOCKED: could not build the remediation list (exit ${FIX_RC}).${C_RESET}"
        echo "        see ${REPORT_DIR}/trivy-report.json"
    fi
    exit 1
fi

# ----------------------------------------------------------- derived image ---
FIXES=$(tr '\n' ' ' < "${REPORT_DIR}/cve-fixes.txt")
if [ -n "${FIXES}" ]; then
    UPGRADE="/opt/venvs/mcp/bin/python -m pip install --no-cache-dir --no-deps --upgrade ${FIXES} ;"
else
    UPGRADE="true ;"
fi

# The derived Containerfile: FROM the upstream image, so every upstream
# layer, label, env var, user and entrypoint is preserved exactly.
# One line per echo — the Jenkinsfile writes the same file the same way.
{
    echo "FROM $(local_ref "${BASE_IMAGE}")"
    echo "USER root"
    echo "RUN set -eux; ${UPGRADE} rm -rf /opt/venvs/mcp/lib/python3.12/site-packages/pip /opt/venvs/mcp/lib/python3.12/site-packages/pip-*.dist-info /opt/venvs/mcp/bin/pip* ; /opt/venvs/mcp/bin/python -c 'import fastmcp, linux_mcp_server, asyncssh'"
    echo "USER mcp"
} > Containerfile.remediated

echo "--- derived Containerfile ---"
cat Containerfile.remediated
echo ""

podman build --network host --pull=never --format docker \
    --file Containerfile.remediated \
    --tag "${REMEDIATED_IMAGE}" \
    .

echo ""
note "the remediated image:"
podman image inspect "${REMEDIATED_IMAGE}" --format 'id={{.Id}} size={{.Size}}'

# From here on the remediated image IS the artifact: the export, the deploy,
# the verify and the drill all use it, so what ships is the image that
# passed the final scan in step 07.
state_save "FULL_IMAGE=${REMEDIATED_IMAGE}"

step_end 06
echo ""
note "next: step-07-scan-trivy-final.sh"
