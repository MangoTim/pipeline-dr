#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 03 — build the image.
#
# Mirrors the Jenkins stage "Build Image": the UPSTREAM Containerfile is
# used as-is, with no edits. The upstream source stays untouched.
#
#   --network host : the build has to reach the UBI registry and PyPI. This
#                    host's container egress is dropped in the firewalld
#                    FORWARD chain, so a bridged build hangs on the pip
#                    install. Host networking routes it through OUTPUT.
#   --format docker: podman's default OCI format silently DROPS the
#                    HEALTHCHECK instruction; the docker format keeps it
#                    and is what the scanners expect.
#
#   ./manual/step-03-build-image.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 03 — build the image"
step_start 03 "building ${BASE_IMAGE} from the unmodified upstream Containerfile"

state_load
require_state BASE_IMAGE

cd "${WORKDIR}"
[ -f upstream/Containerfile ] || die "upstream/Containerfile is missing — run step-01 first"

note "the Containerfile is used exactly as upstream shipped it:"
head -5 upstream/Containerfile | sed 's/^/      /'
echo ""

podman build \
    --file upstream/Containerfile \
    --format docker \
    --network host \
    --tag "${BASE_IMAGE}" \
    --label manual.run="$(cat "${STATE_FILE}" | sed -n 's/^MANUAL_RUN=//p')" \
    upstream

echo ""
note "the image that was built:"
podman image inspect "${BASE_IMAGE}" --format 'id={{.Id}} size={{.Size}} created={{.Created}}'

step_end 03
echo ""
note "next: step-04-scan-aqua.sh"
