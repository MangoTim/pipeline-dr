#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 02 — resolve the image version.
#
# Mirrors the Jenkins stage "Resolve Version": the VERSION file plus the
# Hong Kong date plus a run number produce the tag
#
#     v1.0.<DDMMYY><NN>
#
# In Jenkins <NN> is BUILD_NUMBER. Here it is a counter kept in the state
# file, so a manual run produces the same SHAPE of tag.
#
#   ./manual/step-02-resolve-version.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 02 — resolve the image version"
step_start 02 "building the tag for this run"

cd "${WORKDIR}"

BASE=$(tr -d ' \n' < VERSION)
DAY=$(TZ=Asia/Hong_Kong date +%d%m%y)

# The run counter: the previous value plus one, so re-running this step
# gives a NEW tag instead of overwriting the old one.
PREV=$(sed -n 's/^MANUAL_RUN=//p' "${STATE_FILE}" 2>/dev/null || true)
SEQ=$(printf '%02d' $(( ${PREV:-0} + 1 )))

IMAGE_VERSION="v${BASE}.${DAY}${SEQ}"
BASE_IMAGE="${IMAGE_NAME}:${IMAGE_VERSION}"
REMEDIATED_IMAGE="${IMAGE_NAME}-remediated:${IMAGE_VERSION}"
ARTIFACT="${IMAGE_NAME}-${IMAGE_VERSION}.tar.gz"

state_save \
    "MANUAL_RUN=${SEQ}" \
    "IMAGE_VERSION=${IMAGE_VERSION}" \
    "BASE_IMAGE=${BASE_IMAGE}" \
    "REMEDIATED_IMAGE=${REMEDIATED_IMAGE}" \
    "FULL_IMAGE=${BASE_IMAGE}" \
    "ARTIFACT=${ARTIFACT}"

note "VERSION file     : ${BASE}"
note "Hong Kong date   : ${DAY}"
note "run number       : ${SEQ}"
echo ""
note "image version    : ${IMAGE_VERSION}"
note "pre-remediation  : ${BASE_IMAGE}"
note "post-remediation : ${REMEDIATED_IMAGE}"
note "artifact         : ${ARTIFACT}"

step_end 02
echo ""
note "next: step-03-build-image.sh"
