#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 04 — the Aqua gate.
#
# Mirrors the Jenkins stages "Aqua Image Scan" and "Aqua Image Scan (App)".
# The Aqua console on this host decides whether an image may ship, and the
# pipeline only continues when the report says "Image Is Compliant". BOTH
# artifacts go through the gate — the inspector and the page ship together
# or not at all.
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
require_state BASE_IMAGE APP_BASE_IMAGE

step_start 04 "scanning ${BASE_IMAGE} with the Aqua console"

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"

ensure_podman_socket
load_aqua_creds

SOCK=$(podman_sock)

# Scan one image and gate on the result.
#
#   usage: aqua_gate <image> <report-file> <err-file> <label>
aqua_gate() {
    local image="$1" report="$2" err="$3" label="$4"

    note "console : ${AQUA_HOST}"
    note "image   : $(local_ref "${image}")"
    note "report  : ${report}"
    echo ""

    # Capture the scanner exit code instead of letting `set -e` kill the
    # shell — otherwise a scanner failure produces no diagnostic at all, only
    # a red step.
    local scan_rc=0
    podman run --rm --name "aqua-scan-manual-${label}" \
        --network host \
        --security-opt label=disable --user root \
        -v "${SOCK}:/var/run/docker.sock" \
        "${SCANNER_IMAGE}" \
        scan \
            --host "${AQUA_HOST}" \
            --local "$(local_ref "${image}")" \
            --no-verify \
            --user "${AQUA_USER}" \
            --password "${AQUA_PASSWORD}" \
            --html > "${report}" 2> "${err}" || scan_rc=$?

    if [ "${scan_rc}" -ne 0 ]; then
        echo "--- Aqua scanner stderr ---"
        tail -30 "${err}" || true
        echo ""
        echo "${C_RED}BLOCKED: the Aqua scanner CLI exited ${scan_rc} on ${image}${C_RESET}"
        echo "HINT: 'TLS handshake timeout' or 'Failed checking cybercenter to scanner"
        echo "      compatibility' means the aqua-web console container on this host"
        echo "      has lost its outbound path. Fix it on the host with:"
        echo "          podman network reload"
        exit 1
    fi

    echo "--- Aqua scan summary (${label}) ---"
    grep -oE "Image Is (Compliant|Non-compliant)" "${report}" || true

    # The hard gate.
    grep -q "Image Is Compliant" "${report}" \
        || { echo "${C_RED}BLOCKED: ${image} is non-compliant (or the report has no compliance marker)${C_RESET}"; exit 1; }
}

aqua_gate "${BASE_IMAGE}" \
          "${REPORT_DIR}/aqua-report.html" \
          "${REPORT_DIR}/aqua-scan.err" \
          "mcp"

echo ""

step_start 04 "scanning ${APP_BASE_IMAGE} with the Aqua console"

aqua_gate "${APP_BASE_IMAGE}" \
          "${REPORT_DIR}/aqua-report-app.html" \
          "${REPORT_DIR}/aqua-scan-app.err" \
          "app"

step_end 04
echo ""
note "next: step-05-scan-trivy.sh"
