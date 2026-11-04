#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 08 — export the artifact.
#
# Mirrors the Jenkins stage "Export Artifact". The image travels as a
# tarball, not through a registry: the DR site must be able to receive a
# promoted image even when the PROD registry is down. That is the whole
# point of a DR site.
#
#   ./manual/step-08-export-artifact.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 08 — export the artifact"

state_load
require_state FULL_IMAGE ARTIFACT

step_start 08 "packing ${FULL_IMAGE} into a tarball"

cd "${WORKDIR}"
mkdir -p "${REPORT_DIR}"

rm -f "${ARTIFACT}" "${ARTIFACT}.sha256"

podman save "${FULL_IMAGE}" | gzip > "${ARTIFACT}"
sha256sum "${ARTIFACT}" | tee "${ARTIFACT}.sha256"

ls -lh "${ARTIFACT}"
echo ""
note "this ONE file is what both sites will load — the PROD site and the DR"
note "site end up with byte-identical content."

step_end 08
echo ""
note "next: step-09-deploy.sh"
