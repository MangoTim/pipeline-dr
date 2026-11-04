#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# The LAPTOP-side driver.
#
# Copy this repository to the control plane and run ONE step there, so the
# whole PROD -> DR demo can be driven by hand from the laptop, one command
# at a time:
#
#   ./manual/remote-run.sh 10          # sync, then run step 10 on .105
#   ./manual/remote-run.sh 10 --no-sync
#   ./manual/remote-run.sh all         # every step, in order
#   ./manual/remote-run.sh list        # what the steps are
#
# The step number is the NN in step-NN-*.sh.
# ---------------------------------------------------------------------------

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"

HOST="${MCP_DR_HOST:-192.168.147.105}"
USER_NAME="${MCP_DR_USER:-rhai}"
# The path ON THE CONTROL PLANE — a Linux path, not the laptop's $HOME
# (which on Windows is a C:\... path that means nothing to the remote).
REMOTE="${MCP_DR_REMOTE:-/home/${USER_NAME}/mcp-dr-pipeline}"
SYNC=1

usage() {
    cat <<'EOF'
usage: remote-run.sh <step-number|all|list> [--no-sync] [--host H] [--user U]

  <step-number>   run step-NN-*.sh on the control plane
  all             run every step in order
  list            list the steps

  --no-sync       skip the copy to the host (use the files already there)
  --host H        control plane host   (default 192.168.147.105)
  --user U        control plane account (default rhai)
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --no-sync) SYNC=0; shift ;;
        --host)    HOST="$2"; shift 2 ;;
        --user)    USER_NAME="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        all)       MODE="all"; shift ;;
        list)      MODE="list"; shift ;;
        [0-9]*)    MODE="one"; STEP="$1"; shift ;;
        *) echo "unknown argument: $1" >&2; usage; exit 1 ;;
    esac
done

TARGET="${USER_NAME}@${HOST}"
SSH=(ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=10 "${TARGET}")

step_script() {
    # step number -> the file name on the host
    local n="$1"
    local f
    f=$(cd "${HERE}" && ls step-"${n}"-*.sh 2>/dev/null | head -1 || true)
    [ -n "${f}" ] || { echo "no step ${n} — try 'list'" >&2; exit 1; }
    echo "${f}"
}

list_steps() {
    echo "the manual steps:"
    for f in "${HERE}"/step-*.sh; do
        n=$(basename "${f}" | sed -E 's/^step-([0-9]+)-.*/\1/')
        title=$(grep -m1 '^# Step ' "${f}" | sed -E 's/^# Step ([0-9]+) — //')
        printf '  %-3s %s\n' "${n}" "${title}"
    done
}

case "${MODE:-}" in
    "")     usage; exit 1 ;;
    list)   list_steps; exit 0 ;;
    all)    ;;
    one)    ;;
esac

# ------------------------------------------------------------------- sync ---
if [ "${SYNC}" -eq 1 ]; then
    echo ">> copying the repository to ${TARGET}:${REMOTE}"
    tar -cf - \
        --exclude=.git \
        --exclude=manual-reports \
        --exclude='.manual-state.env' \
        --exclude=upstream \
        --exclude='*.tar.gz' \
        -C "${ROOT}" . \
        | "${SSH[@]}" "mkdir -p '${REMOTE}' && tar -xf - -C '${REMOTE}'"
    echo ">> synced"
    echo ""
fi

# -------------------------------------------------------------------- run ---
if [ "${MODE}" = "all" ]; then
    "${SSH[@]}" "bash '${REMOTE}/manual/run-all.sh'"
else
    SCRIPT=$(step_script "${STEP}")
    echo ">> running ${SCRIPT} on ${TARGET}"
    echo ""
    "${SSH[@]}" "bash '${REMOTE}/manual/${SCRIPT}'"
fi
