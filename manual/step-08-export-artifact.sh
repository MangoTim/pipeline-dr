#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 08 — export the artifacts.
#
# Mirrors the Jenkins stage "Export Artifact". The images travel as
# tarballs, not through a registry: the DR site must be able to receive a
# promoted image even when the PROD registry is down. That is the whole
# point of a DR site.
#
# TWO artifacts, ONE version: the inspector and the workload that is moved
# by the drill travel together, so a release is always the pair.
#
#   ./manual/step-08-export-artifact.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 08 — export the artifacts"

state_load
require_state FULL_IMAGE ARTIFACT APP_FULL_IMAGE APP_ARTIFACT

step_start 08 "packing ${FULL_IMAGE} and ${APP_FULL_IMAGE} into tarballs"

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"

rm -f "${ARTIFACT}" "${ARTIFACT}.sha256" "${APP_ARTIFACT}" "${APP_ARTIFACT}.sha256"

podman save "${FULL_IMAGE}"     | gzip > "${ARTIFACT}"
podman save "${APP_FULL_IMAGE}" | gzip > "${APP_ARTIFACT}"
sha256sum "${ARTIFACT}" "${APP_ARTIFACT}" | tee "${ARTIFACT}.sha256"

ls -lh "${ARTIFACT}" "${APP_ARTIFACT}"
echo ""
note "these TWO files are what both sites will load — the PROD site and the"
note "DR site end up with byte-identical content."

step_end 08
echo ""
note "next: step-09-deploy.sh"
