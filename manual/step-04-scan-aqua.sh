#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 04 — the Aqua gate.
#
# Mirrors the Jenkins stage "Aqua Image Scan". The Aqua console on this
# host decides whether the image may ship, and the pipeline only continues
# when the report says "Image Is Compliant".
#
#   --local <image> : the syntax Aqua scanner 2022.4 accepts. The plugin
#                      generates "--registry '' <positional>", which the
#                      scanner rejects.
#   --html          : the report goes to STDOUT and is redirected to a
#                      file. DO NOT use --htmlfile <path> — that writes
#                      inside the scanner container and is lost when
#                      --rm deletes it.
#   --no-verify     : the console certificate is self-signed.
#
#   ./manual/step-04-scan-aqua.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 04 — the Aqua gate"

state_load
require_state BASE_IMAGE

step_start 04 "scanning ${BASE_IMAGE} with the Aqua console"

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"

ensure_podman_socket
load_aqua_creds

SOCK=$(podman_sock)
REPORT="${REPORT_DIR}/aqua-report.html"
ERR="${REPORT_DIR}/aqua-scan.err"

note "console : ${AQUA_HOST}"
note "image   : $(local_ref "${BASE_IMAGE}")"
note "report  : ${REPORT}"
echo ""

# Capture the scanner exit code instead of letting `set -e` kill the shell —
# otherwise a scanner failure produces no diagnostic at all, only a red step.
SCAN_RC=0
podman run --rm --name aqua-scan-manual \
    --network host \
    --security-opt label=disable --user root \
    -v "${SOCK}:/var/run/docker.sock" \
    "${SCANNER_IMAGE}" \
    scan \
        --host "${AQUA_HOST}" \
        --local "$(local_ref "${BASE_IMAGE}")" \
        --no-verify \
        --user "${AQUA_USER}" \
        --password "${AQUA_PASSWORD}" \
        --html > "${REPORT}" 2> "${ERR}" || SCAN_RC=$?

if [ "${SCAN_RC}" -ne 0 ]; then
    echo "--- Aqua scanner stderr ---"
    tail -30 "${ERR}" || true
    echo ""
    echo "${C_RED}BLOCKED: the Aqua scanner CLI exited ${SCAN_RC}${C_RESET}"
    echo "HINT: 'TLS handshake timeout' or 'Failed checking cybercenter to scanner"
    echo "      compatibility' means the aqua-web console container on this host"
    echo "      has lost its outbound path. Fix it on the host with:"
    echo "          podman network reload"
    exit 1
fi

echo "--- Aqua scan summary ---"
grep -oE "Image Is (Compliant|Non-compliant)" "${REPORT}" || true

# The hard gate.
grep -q "Image Is Compliant" "${REPORT}" \
    || { echo "${C_RED}BLOCKED: the image is non-compliant (or the report has no compliance marker)${C_RESET}"; exit 1; }

step_end 04
echo ""
note "next: step-05-scan-trivy.sh"
