#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Shared helpers for the manual steps.
#
# Sourced by every step-NN-*.sh — it pulls in env.sh and provides the
# banner / state / podman-socket / verify helpers the steps share.
# ---------------------------------------------------------------------------

set -euo pipefail

# shellcheck source=env.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

# ------------------------------------------------------------------ output --
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_RESET=$'\033[0m'
    C_BLUE=$'\033[1;34m'
    C_GREEN=$'\033[1;32m'
    C_RED=$'\033[1;31m'
    C_YELLOW=$'\033[1;33m'
    C_DIM=$'\033[2m'
else
    C_RESET=""; C_BLUE=""; C_GREEN=""; C_RED=""; C_YELLOW=""; C_DIM=""
fi

banner() {
    echo ""
    echo "${C_BLUE}==============================================================================${C_RESET}"
    echo "${C_BLUE} $*${C_RESET}"
    echo "${C_BLUE}==============================================================================${C_RESET}"
}

step_start() {
    local n="$1"; shift
    echo ""
    echo "${C_BLUE}>>> [step ${n}] $*${C_RESET}"
}

step_end() {
    echo "${C_GREEN}<<< [step ${1}] OK${C_RESET}"
}

note() { echo "${C_DIM}    $*${C_RESET}"; }
warn() { echo "${C_YELLOW}    WARN: $*${C_RESET}"; }
die()  { echo "${C_RED}    FAIL: $*${C_RESET}" >&2; exit 1; }

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

# ansible is a pip install into the deploy user's own ~/.local/bin on this
# host, so it is often not on a non-login PATH.
ensure_ansible_on_path() {
    if command -v ansible-playbook >/dev/null 2>&1; then
        return 0
    fi
    if [ -x "${HOME}/.local/bin/ansible-playbook" ]; then
        export PATH="${HOME}/.local/bin:${PATH}"
        return 0
    fi
    die "ansible-playbook not found (looked on PATH and in ${HOME}/.local/bin)"
}

# ------------------------------------------------------------------- state --
# The state file carries the values from one step to the next (the image
# tag, the artifact name, ...), so every step can be run on its own.
state_save() {
    local tmp="${STATE_FILE}.tmp"
    if [ -f "${STATE_FILE}" ]; then cp "${STATE_FILE}" "${tmp}"; else : > "${tmp}"; fi
    while [ "$#" -ge 2 ]; do
        local key="$1" val="$2"
        grep -v "^${key}=" "${tmp}" > "${tmp}.2" || true
        printf '%s=%s\n' "${key}" "${val}" >> "${tmp}.2"
        mv "${tmp}.2" "${tmp}"
        shift 2
    done
    mv "${tmp}" "${STATE_FILE}"
    note "state -> ${STATE_FILE}"
}

state_load() {
    [ -f "${STATE_FILE}" ] || die "no state yet — run step-02-resolve-version.sh first"
    # shellcheck disable=SC1090
    set -a; . "${STATE_FILE}"; set +a
}

require_state() {
    local v
    for v in "$@"; do
        [ -n "${!v:-}" ] || die "state variable '${v}' is empty — run the earlier step first"
    done
}

# ------------------------------------------------------------ podman socket --
# The Aqua and Trivy scanners reach the local image through a container
# engine socket. Rootless podman does not expose one by default, so the API
# service is started on demand. (In the Jenkins container the root podman
# socket is bind-mounted at /var/run/docker.sock instead — same idea.)
podman_sock() {
    echo "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman/podman.sock"
}

# The name an image carries in the local store: podman normalises a short
# name into the "localhost/" registry.
local_ref() {
    echo "localhost/${1}"
}

ensure_podman_socket() {
    local sock i
    sock="$(podman_sock)"
    if [ -S "${sock}" ]; then
        return 0
    fi
    mkdir -p "$(dirname "${sock}")"
    note "starting the rootless podman API service on ${sock}"
    nohup podman system service --time=0 "unix://${sock}" \
        > "${HOME}/.mcp-demo/podman-api.log" 2>&1 &
    i=0
    while [ "${i}" -lt 20 ]; do
        [ -S "${sock}" ] && return 0
        sleep 1
        i=$((i + 1))
    done
    die "the podman API service did not start — see ${HOME}/.mcp-demo/podman-api.log"
}

# ----------------------------------------------------------------- helpers --
# Run the MCP verify client INSIDE the image, so the artifact that is being
# tested is exactly the one that was shipped. The script is piped in on
# STDIN rather than bind-mounted: podman runs on the host and cannot see a
# path inside a container.
verify_mcp() {
    # usage: verify_mcp <url> <target-host> <expected-hostname> <image>
    local url="$1" target="$2" expect="$3" image="$4" rc=0
    podman run -i --rm --pull=never --network host --security-opt label=disable \
        --entrypoint /opt/venvs/mcp/bin/python \
        "${image}" \
        - --url "${url}" --target "${target}" --expect "${expect}" \
        < "${WORKDIR}/scripts/mcp_verify.py" 2>&1 | tee -a "${TRANSCRIPT}" || rc=${PIPESTATUS[0]}
    return "${rc}"
}

# Load the Aqua console credential from the file OUTSIDE the repository.
load_aqua_creds() {
    [ -f "${AQUA_ENV_FILE}" ] || die \
"the Aqua console credential file is missing: ${AQUA_ENV_FILE}
    It holds AQUA_USER and AQUA_PASSWORD and is deliberately NOT in the
    repository. Create it on this host, e.g.:

        mkdir -p ~/.mcp-demo && umask 077
        cat > ~/.mcp-demo/aqua.env <<'EOF'
        AQUA_USER=administrator
        AQUA_PASSWORD=<the aqua console password>
        EOF
"
    set -a
    # shellcheck disable=SC1090
    . "${AQUA_ENV_FILE}"
    set +a
    [ -n "${AQUA_USER:-}" ]     || die "${AQUA_ENV_FILE} does not define AQUA_USER"
    [ -n "${AQUA_PASSWORD:-}" ] || die "${AQUA_ENV_FILE} does not define AQUA_PASSWORD"
}
