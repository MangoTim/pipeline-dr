#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Step 01 — fetch the upstream sources.
#
# Mirrors the Jenkins stages "Fetch MCP Source" and "Fetch App Source": both
# sources are downloaded from GitHub at build time and pinned to an EXACT
# commit. Nothing is vendored in this repository, so there is no second copy
# of either upstream's code to keep in sync.
#
#   ./manual/step-01-fetch-source.sh
# ---------------------------------------------------------------------------

# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

banner "Step 01 — fetch the upstream sources"
step_start 01 "downloading ${MCP_REPO} @ ${MCP_COMMIT}"
step_start 01 "downloading ${APP_REPO} @ ${APP_COMMIT}"

cd "${WORKDIR}"

# ---- the MCP server ------------------------------------------------------
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
echo ""

# ---- the Lunch Rolltable app ---------------------------------------------
rm -rf app-src app-src.tar.gz

note "url  : https://github.com/${APP_REPO}/archive/${APP_COMMIT}.tar.gz"
curl -fsSL --retry 3 --retry-delay 5 \
    -o app-src.tar.gz \
    "https://github.com/${APP_REPO}/archive/${APP_COMMIT}.tar.gz"

mkdir -p app-src
tar -xzf app-src.tar.gz -C app-src --strip-components=1

[ -f app-src/Dockerfile ]    || die "app-src/Dockerfile is missing — is the commit right?"
[ -f app-src/serve.py ]      || die "app-src/serve.py is missing — is the commit right?"
[ -f app-src/mcp_client.py ] || die "app-src/mcp_client.py is missing — is the commit right?"

note "OK   the app source is ready:"
ls app-src

step_end 01
echo ""
note "next: step-02-resolve-version.sh"
