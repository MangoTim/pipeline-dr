#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 03 — build the images.
#
# Mirrors the Jenkins stages "Build Image" and "Build App Image": BOTH
# UPSTREAM Containerfiles are used as-is, with no edits. The upstream sources
# stay untouched.
#
#   --network host : the build has to reach the UBI registry, PyPI, the
#                    Debian registry and the apt mirrors. This host's
#                    container egress is dropped in the firewalld FORWARD
#                    chain, so a bridged build hangs on the pip install.
#                    Host networking routes it through OUTPUT.
#   --format docker: podman's default OCI format silently DROPS the
#                    HEALTHCHECK instruction; the docker format keeps it
#                    and is what the scanners expect.
#
#   ./manual/step-03-build-image.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 03 — build the images"

state_load
require_state BASE_IMAGE APP_BASE_IMAGE

RUN_LABEL="$(sed -n 's/^MANUAL_RUN=//p' "${STATE_FILE}")"

step_start 03 "building ${BASE_IMAGE} from the unmodified upstream Containerfile"

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
    --label manual.run="${RUN_LABEL}" \
    upstream

echo ""
note "the image that was built:"
podman image inspect "${BASE_IMAGE}" --format 'id={{.Id}} size={{.Size}} created={{.Created}}'
echo ""

step_start 03 "building ${APP_BASE_IMAGE} from the unmodified upstream Dockerfile"

[ -f app-src/Dockerfile ] || die "app-src/Dockerfile is missing — run step-01 first"

note "the Dockerfile is used exactly as upstream shipped it:"
head -5 app-src/Dockerfile | sed 's/^/      /'
echo ""

podman build \
    --file app-src/Dockerfile \
    --format docker \
    --network host \
    --tag "${APP_BASE_IMAGE}" \
    --label manual.run="${RUN_LABEL}" \
    app-src

echo ""
note "the app image that was built:"
podman image inspect "${APP_BASE_IMAGE}" --format 'id={{.Id}} size={{.Size}} created={{.Created}}'

step_end 03
echo ""
note "next: step-04-scan-aqua.sh"
