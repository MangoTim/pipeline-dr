#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 09 — deploy to both sites with Ansible.
#
# Mirrors the Jenkins stage "Ansible Deploy". The SAME tarballs are copied to
# .105 (PROD) and .104 (DR). Each site loads them into its own rootless
# podman store and runs them as systemd USER units — no root, no sudo
# password, no shared filesystem, no dependency on the PROD registry.
#
# Two artifacts, two roles: `mcp` and `rolltable`. site.yml plays both roles
# on both sites, so the MCP and the page it serves are deployed from the
# same release.
#
#   ./manual/step-09-deploy.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 09 — deploy to both sites"
step_start 09 "ansible-playbook site.yml"

state_load
require_state FULL_IMAGE ARTIFACT APP_FULL_IMAGE APP_ARTIFACT

ensure_ansible_on_path

cd "${WORKDIR}/ansible"

note "MCP image    : ${FULL_IMAGE}"
note "MCP artifact : ${WORKDIR}/${ARTIFACT}"
note "app image    : ${APP_FULL_IMAGE}"
note "app artifact : ${WORKDIR}/${APP_ARTIFACT}"
note "sites        : ${PROD_HOST} (PROD) and ${DR_HOST} (DR)"
echo ""

# The controller's SSH key. The ini key is `private_key_file` and the path
# is relative to the CONTROLLER's home, so the same inventory works from a
# developer machine and from this host.
export ANSIBLE_PRIVATE_KEY_FILE="${HOME}/.ssh/id_rhai108_rsa"
[ -r "${ANSIBLE_PRIVATE_KEY_FILE}" ] || die "the SSH key ${ANSIBLE_PRIVATE_KEY_FILE} is not readable"

ansible-playbook \
    -i inventory.ini \
    site.yml \
    -e "mcp_image=${FULL_IMAGE}" \
    -e "mcp_artifact=${WORKDIR}/${ARTIFACT}" \
    -e "rolltable_image=${APP_FULL_IMAGE}" \
    -e "rolltable_artifact=${WORKDIR}/${APP_ARTIFACT}"

step_end 09
echo ""
note "next: step-10-verify-prod.sh"
