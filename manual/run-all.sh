#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Run EVERY step in order, on the control plane.
#
# This is the "just do the whole thing by hand" path. Each step is still a
# separate script, so the output of each one can be read on its own — but
# this is the shortcut when you do not want to stop between them.
#
#   ./manual/run-all.sh
# ---------------------------------------------------------------------------

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib.sh
source "${HERE}/lib.sh"

banner "Manual run — every step in order"

for step in "${HERE}"/step-*.sh; do
    bash "${step}"
done

echo ""
echo "${C_BLUE}==============================================================================${C_RESET}"
echo "${C_BLUE} the whole run is done${C_RESET}"
echo "${C_BLUE}==============================================================================${C_RESET}"
note "reports   : ${REPORT_DIR}"
note "transcript: ${TRANSCRIPT}"
