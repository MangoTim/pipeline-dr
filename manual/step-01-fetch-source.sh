#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 01 — fetch the upstream MCP source.
#
# Mirrors the Jenkins stage "Fetch MCP Source": the source is downloaded
# from GitHub at build time and pinned to an EXACT commit. Nothing is
# vendored in this repository, so there is no second copy of Red Hat's code
# to keep in sync.
#
#   ./manual/step-01-fetch-source.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 01 — fetch the upstream MCP source"
step_start 01 "downloading ${MCP_REPO} @ ${MCP_COMMIT}"

cd "${WORKDIR}"

rm -rf upstream mcp-src.tar.gz

note "url  : https://github.com/${MCP_REPO}/archive/${MCP_COMMIT}.tar.gz"
curl -fsSL --retry 3 --retry-delay 5 \
    -o mcp-src.tar.gz \
    "https://github.com/${MCP_REPO}/archive/${MCP_COMMIT}.tar.gz"

mkdir -p upstream
tar -xzf mcp-src.tar.gz -C upstream --strip-components=1

[ -f upstream/Containerfile ] || die "upstream/Containerfile is missing — is the commit right?"
[ -d upstream/src ] || die "upstream/src is missing — is the commit right?"

note "OK   the upstream source is ready:"
ls upstream | head -20

step_end 01
echo ""
note "next: step-02-resolve-version.sh"
