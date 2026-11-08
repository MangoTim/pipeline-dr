#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 13 — prove both sites run the SAME artifacts.
#
# Not a Jenkins stage — this is the evidence that ties the demo together.
# The PROD site and the DR site are different machines, but they load the
# same tarballs, so the images they run MUST be identical.
#
# What is compared, and what it means:
#
#   image ID   the sha256 of the image CONFIG — the authoritative identity
#              of the image. It must match.
#   layers     the sha256 of every layer, in order. They must all match:
#              this is the content itself.
#   digest     the sha256 of the image MANIFEST. It is reported, but it is
#              NOT a gate: the manifest is rebuilt by each site's own
#              podman, and the two hosts do not run the same podman build
#              (.105 has 4.9.4-rhel, .104 has 4.9.4-dev), so the manifest
#              bytes — and therefore their hash — can differ while every
#              layer is byte-identical.
#
#   ./manual/step-13-show-same-artifact.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 13 — the same artifacts on both sites"
step_start 13 "comparing the image ID and the layers on PROD and DR"

state_load
require_state FULL_IMAGE APP_FULL_IMAGE

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"

KEY="${HOME}/.ssh/id_rhai108_rsa"
[ -r "${KEY}" ] || die "the pipeline SSH key ${KEY} is missing or unreadable"

# Compare ONE image across the two sites and gate on the result.
#
#   usage: compare_image <image-ref> <label>
compare_image() {
    local image="$1" label="$2"

    # The deploy user on each site — the same accounts Ansible drives.
    local inspect_site
    inspect_site() {
        local target="$1"
        ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
            -i "${KEY}" "${target}" \
            "podman image inspect $(local_ref "${image}") --format 'Id={{.Id}} Digest={{.Digest}} Layers={{.RootFS.Layers}}'"
    }

    local prod_out dr_out
    prod_out=$(inspect_site "${PROD_USER}@${PROD_HOST}") || die "could not inspect the PROD site"
    dr_out=$(inspect_site "${DR_USER}@${DR_HOST}")     || die "could not inspect the DR site"

    {
        echo "--- ${label} (${image}) ---"
        echo "PROD ${PROD_USER}@${PROD_HOST}: ${prod_out}"
        echo "DR   ${DR_USER}@${DR_HOST}: ${dr_out}"
    } | tee -a "${REPORT_DIR}/image-inspect.txt"

    local prod_id dr_id prod_digest dr_digest prod_layers dr_layers
    prod_id=$(echo "${prod_out}"     | sed -n 's/^Id=\([^ ]*\).*/\1/p')
    dr_id=$(echo "${dr_out}"         | sed -n 's/^Id=\([^ ]*\).*/\1/p')
    prod_digest=$(echo "${prod_out}" | sed -n 's/^.*Digest=\([^ ]*\).*/\1/p')
    dr_digest=$(echo "${dr_out}"     | sed -n 's/^.*Digest=\([^ ]*\).*/\1/p')
    prod_layers=$(echo "${prod_out}" | sed -n 's/^.*Layers=//p')
    dr_layers=$(echo "${dr_out}"     | sed -n 's/^.*Layers=//p')

    echo ""
    printf '  %-18s image id  %s\n' "${PROD_HOST}" "${prod_id}"
    printf '  %-18s image id  %s\n' "${DR_HOST}"   "${dr_id}"
    echo ""
    echo "  layers (identical content, in order):"
    echo "${prod_layers}" | tr -d '[]' | tr ' ' '\n' | grep -v '^$' | nl -w4 -s'  ' | sed 's/^/    /'
    echo ""
    printf '  manifest digest  PROD %s\n' "${prod_digest}"
    printf '  manifest digest  DR   %s\n' "${dr_digest}"
    if [ "${prod_digest}" != "${dr_digest}" ]; then
        note "(the manifest digests differ because each site rebuilds the manifest with"
        note " its own podman build — the image ID and every layer are identical)"
    fi
    echo ""

    [ -n "${prod_id}" ] && [ "${prod_id}" = "${dr_id}" ] \
        || { echo "${C_RED}FAIL: the sites run DIFFERENT ${label} images${C_RESET}"; exit 1; }

    [ "${prod_layers}" = "${dr_layers}" ] \
        || { echo "${C_RED}FAIL: the ${label} layer digests differ${C_RESET}"; exit 1; }

    echo "${C_GREEN}PASS: both sites run the SAME ${label} image (${prod_id:0:12})${C_RESET}"
    echo "${C_GREEN}      and every one of its layers is byte-identical${C_RESET}"
    echo ""
}

: > "${REPORT_DIR}/image-inspect.txt"

compare_image "${FULL_IMAGE}" "MCP"
compare_image "${APP_FULL_IMAGE}" "app"

step_end 13
echo ""
note "the drill is over. PROD is live, DR is stopped — the intended DR posture."
note "the transcript of the whole drill is in ${TRANSCRIPT}"
