#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Shared helpers for the DRILL pipelines: mcp-failover and mcp-failback.
#
# A drill pipeline does NOT build and does NOT scan. It acts on whatever is
# deployed right now. That is what makes it an operator action rather than a
# side effect of a CI build: you run it when you want to move the service.
#
# Two things here differ from the main pipeline, and both are deliberate:
#
# 1. THE VERIFICATION CLIENT RUNS ON THE CONTROL PLANE, not inside the
#    Jenkins container. The client needs fastmcp, which only exists inside
#    the MCP image, and the deployed image lives in the DEPLOY USER's
#    rootless podman store on .105. The Jenkins container has its own store
#    and never had the artifact -- the main pipeline can run the client
#    inside it only because it built the image there a moment ago.
#
# 2. THE IMAGE IS READ FROM THE SYSTEMD UNIT of the deployed site, not from
#    a variable. The drill has to act on what is actually deployed, not on
#    what an earlier build intended to deploy.
#
# Sourced from the `sh` blocks of Jenkinsfile.failover / Jenkinsfile.failback.
# ---------------------------------------------------------------------------

# The transcript every drill writes; the job archives it as the evidence.
DRILL_TRANSCRIPT="drill-transcript.txt"

# The state file carries the resolved image from the first stage into the
# later ones, so every stage acts on the SAME artifact.
DRILL_STATE_FILE="${WORKSPACE}/.drill-state.env"

# The control plane: the PROD site, and the deploy user that owns the
# rootless podman store the deployed image lives in.
DRILL_CTRL_HOST="${DRILL_CTRL_HOST:-192.168.147.105}"
DRILL_CTRL_USER="${DRILL_CTRL_USER:-rhai}"

drill_log() {
    echo "$@" | tee -a "${DRILL_TRANSCRIPT}"
}

# SSH to the control plane and run a remote command. stdin is passed
# through, so a script can be piped into the remote command.
drill_ssh() {
    ssh -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -o BatchMode=yes \
        -i "${ANSIBLE_PRIVATE_KEY_FILE}" \
        "${DRILL_CTRL_USER}@${DRILL_CTRL_HOST}" "$@"
}

# The same, for a remote command that must NOT read stdin.
drill_ssh_n() {
    ssh -n -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -o BatchMode=yes \
        -i "${ANSIBLE_PRIVATE_KEY_FILE}" \
        "${DRILL_CTRL_USER}@${DRILL_CTRL_HOST}" "$@"
}

# The MCP image the control plane is running right now, taken from its
# systemd user unit. Returns e.g. rhel-mcp-remediated:v1.0.08112615
drill_deployed_image() {
    drill_ssh_n "grep '^ExecStart=' ~/.config/systemd/user/rhel-mcp.service" \
        | awk '{print $NF}'
}

# The app image, same way. Empty when the page is not deployed.
drill_app_image() {
    drill_ssh_n "grep '^ExecStart=' ~/.config/systemd/user/lunch-rolltable.service 2>/dev/null" \
        | awk '{print $NF}'
}

# Is the page deployed on this pair at all? Both sites get the same
# artifact, so the control plane answers for the pair.
drill_app_deployed() {
    [ -n "$(drill_app_image)" ]
}

# ------------------------------------------------------------------- state --
drill_state_save() {
    # usage: drill_state_save KEY=VALUE [KEY=VALUE ...]
    local tmp="${DRILL_STATE_FILE}.tmp" entry
    : > "${tmp}"
    for entry in "$@"; do
        printf '%s\n' "${entry}" >> "${tmp}"
    done
    mv "${tmp}" "${DRILL_STATE_FILE}"
}

drill_state_load() {
    [ -f "${DRILL_STATE_FILE}" ] || {
        echo "no drill state — the run never resolved the deployed image" >&2
        return 1
    }
    # shellcheck disable=SC1090
    . "${DRILL_STATE_FILE}"
}

# ------------------------------------------------------------------ verify --
# Run the MCP verification client ON THE CONTROL PLANE. It is the same
# container, the same script and the same assertions the main pipeline
# runs -- only the host it runs on is different.
#
# usage: drill_verify_mcp <url> <target-host> <expected-hostname> <image> [extra args...]
drill_verify_mcp() {
    local url="$1" target="$2" expect="$3" image="$4"; shift 4
    local rc=0
    drill_ssh "podman run -i --rm --pull=never --network host --security-opt label=disable \
        --entrypoint /opt/venvs/mcp/bin/python ${image} - \
        --url ${url} --target ${target} --expect ${expect} $*" \
        < "${WORKSPACE}/scripts/mcp_verify.py" 2>&1 | tee -a "${DRILL_TRANSCRIPT}" || rc=${PIPESTATUS[0]}
    return "${rc}"
}

# Ask the standby what it can see of ITSELF and gate on the numbers. This is
# the check that makes the MCP load-bearing: a standby that cannot hold the
# load is never promoted.
#
# usage: drill_probe_dr <url> <target-host> <expected-hostname> <image>
drill_probe_dr() {
    local url="$1" target="$2" expect="$3" image="$4" rc=0
    drill_ssh "podman run -i --rm --pull=never --network host --security-opt label=disable \
        --entrypoint /opt/venvs/mcp/bin/python ${image} - \
        --url ${url} --target ${target} --expect ${expect} \
        --min-cpu-cores ${DR_MIN_CPU_CORES} \
        --min-free-mem-percent ${DR_MIN_FREE_MEM_PERCENT} \
        --min-free-disk-percent ${DR_MIN_FREE_DISK_PERCENT}" \
        < "${WORKSPACE}/scripts/mcp_dr_probe.py" 2>&1 | tee -a "${DRILL_TRANSCRIPT}" || rc=${PIPESTATUS[0]}
    return "${rc}"
}

# Verify the page. The page's panel asks the MCP which site it is talking
# to, so this checks the whole chain: page -> MCP -> host.
#
# usage: drill_verify_app <url> <expected-hostname> <role> <peer-role> <image>
drill_verify_app() {
    local url="$1" expect="$2" role="$3" peer="$4" image="$5" rc=0
    drill_ssh "podman run -i --rm --pull=never --network host --security-opt label=disable \
        --entrypoint python ${image} - \
        --url ${url} --expect ${expect} --role ${role} --peer ${peer}" \
        < "${WORKSPACE}/scripts/app_verify.py" 2>&1 | tee -a "${DRILL_TRANSCRIPT}" || rc=${PIPESTATUS[0]}
    return "${rc}"
}

# ----------------------------------------------------------------- ansible --
# Run one of the drill playbooks from the checkout, with the controller key.
#
# usage: drill_ansible <playbook>
drill_ansible() {
    cd "${WORKSPACE}/ansible"
    ansible-playbook -i inventory.ini "$1"
}
