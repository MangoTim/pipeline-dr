#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 09 — deploy to both sites with Ansible.
#
# Mirrors the Jenkins stage "Ansible Deploy". The SAME tarball is copied to
# .105 (PROD) and .104 (DR). Each site loads it into its own rootless podman
# store and runs it as a systemd USER unit — no root, no sudo password, no
# shared filesystem, no dependency on the PROD registry.
#
#   ./manual/step-09-deploy.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 09 — deploy to both sites"
step_start 09 "ansible-playbook site.yml"

state_load
require_state FULL_IMAGE ARTIFACT

ensure_ansible_on_path

cd "${WORKDIR}/ansible"

note "image    : ${FULL_IMAGE}"
note "artifact : ${WORKDIR}/${ARTIFACT}"
note "sites    : ${PROD_HOST} (PROD) and ${DR_HOST} (DR)"
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
    -e "mcp_artifact=${WORKDIR}/${ARTIFACT}"

step_end 09
echo ""
note "next: step-10-verify-prod.sh"
