#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 13 — prove both sites run the SAME artifact.
#
# Not a Jenkins stage — this is the evidence that ties the demo together.
# The PROD site and the DR site are different machines, but they load the
# same tarball, so the image they run MUST be identical.
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

banner "Step 13 — the same artifact on both sites"
step_start 13 "comparing the image ID and the layers on PROD and DR"

state_load
require_state FULL_IMAGE

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"

KEY="${HOME}/.ssh/id_rhai108_rsa"
[ -r "${KEY}" ] || die "the pipeline SSH key ${KEY} is missing or unreadable"

# The deploy user on each site — the same accounts Ansible drives.
inspect_site() {
    local target="$1"
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        -i "${KEY}" "${target}" \
        "podman image inspect $(local_ref "${FULL_IMAGE}") --format 'Id={{.Id}} Digest={{.Digest}} Layers={{.RootFS.Layers}}'"
}

PROD_OUT=$(inspect_site "${PROD_USER}@${PROD_HOST}") || die "could not inspect the PROD site"
DR_OUT=$(inspect_site "${DR_USER}@${DR_HOST}")     || die "could not inspect the DR site"

{
    echo "PROD ${PROD_USER}@${PROD_HOST}: ${PROD_OUT}"
    echo "DR   ${DR_USER}@${DR_HOST}: ${DR_OUT}"
} | tee "${REPORT_DIR}/image-inspect.txt"

PROD_ID=$(echo "${PROD_OUT}"     | sed -n 's/^Id=\([^ ]*\).*/\1/p')
DR_ID=$(echo "${DR_OUT}"         | sed -n 's/^Id=\([^ ]*\).*/\1/p')
PROD_DIGEST=$(echo "${PROD_OUT}" | sed -n 's/^.*Digest=\([^ ]*\).*/\1/p')
DR_DIGEST=$(echo "${DR_OUT}"     | sed -n 's/^.*Digest=\([^ ]*\).*/\1/p')
PROD_LAYERS=$(echo "${PROD_OUT}" | sed -n 's/^.*Layers=//p')
DR_LAYERS=$(echo "${DR_OUT}"     | sed -n 's/^.*Layers=//p')

echo ""
printf '  %-18s image id  %s\n' "${PROD_HOST}" "${PROD_ID}"
printf '  %-18s image id  %s\n' "${DR_HOST}"   "${DR_ID}"
echo ""
echo "  layers (identical content, in order):"
echo "${PROD_LAYERS}" | tr -d '[]' | tr ' ' '\n' | grep -v '^$' | nl -w4 -s'  ' | sed 's/^/    /'
echo ""
printf '  manifest digest  PROD %s\n' "${PROD_DIGEST}"
printf '  manifest digest  DR   %s\n' "${DR_DIGEST}"
if [ "${PROD_DIGEST}" != "${DR_DIGEST}" ]; then
    note "(the manifest digests differ because each site rebuilds the manifest with"
    note " its own podman build — the image ID and every layer are identical)"
fi
echo ""

[ -n "${PROD_ID}" ] && [ "${PROD_ID}" = "${DR_ID}" ] \
    || { echo "${C_RED}FAIL: the sites run DIFFERENT images${C_RESET}"; exit 1; }

[ "${PROD_LAYERS}" = "${DR_LAYERS}" ] \
    || { echo "${C_RED}FAIL: the layer digests differ${C_RESET}"; exit 1; }

echo "${C_GREEN}PASS: both sites run the SAME image (${PROD_ID:0:12})${C_RESET}"
echo "${C_GREEN}      and every one of its layers is byte-identical${C_RESET}"

step_end 13
echo ""
note "the drill is over. PROD is live, DR is stopped — the intended DR posture."
note "the transcript of the whole drill is in ${TRANSCRIPT}"
