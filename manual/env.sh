#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Configuration for the MANUAL (by hand) run of the PROD/DR MCP pipeline.
#
# Every step script sources this file. Change a value HERE, never inside a
# step — that is what keeps the manual run and the Jenkins run comparable:
# the same hosts, the same image, the same gates, the same evidence.
#
# This file holds NO secrets. The Aqua console credential lives outside the
# repository (see AQUA_ENV_FILE below and manual/README.md).
# ---------------------------------------------------------------------------

# --- the two sites ---------------------------------------------------------
PROD_HOST="192.168.147.105"     # PROD site — and the control plane
DR_HOST="192.168.147.104"       # DR site
PROD_USER="rhai"                # deploy user on PROD (uid 1001)
DR_USER="dr"                    # deploy user on DR   (uid 1001)

# --- the MCP endpoint ------------------------------------------------------
MCP_PORT="8095"
MCP_PATH="/mcp"

# The hostname each site reports when the MCP inspects it. This is the PROOF
# of which site is serving: the SAME image, a DIFFERENT answer.
PROD_EXPECT="server-gateway.example.com"
DR_EXPECT="localhost.localdomain"

# --- the upstream source ----------------------------------------------------
MCP_REPO="rhel-lightspeed/linux-mcp-server"
MCP_COMMIT="6d7ca1d1da8598c2e816fd69e98b8f7cf97da0d1"

# --- images and scanners ----------------------------------------------------
IMAGE_NAME="rhel-mcp"
SCANNER_IMAGE="registry.aquasec.com/scanner:2022.4.868"
TRIVY_IMAGE="docker.io/aquasec/trivy:0.76.1"
AQUA_HOST="https://192.168.147.105"

# The Aqua console credential (username + password). This file is NEVER
# committed — it lives in the deploy user's home directory.
AQUA_ENV_FILE="${AQUA_ENV_FILE:-${HOME}/.mcp-demo/aqua.env}"

# --- where things live ------------------------------------------------------
# WORKDIR is the checkout of this repository on the control plane. Every
# step writes its reports into REPORT_DIR, so a manual run leaves the same
# kind of evidence a Jenkins build archives.
WORKDIR="${WORKDIR:-${HOME}/mcp-dr-pipeline}"
REPORT_DIR="${WORKDIR}/manual-reports"
STATE_FILE="${WORKDIR}/.manual-state.env"
TRANSCRIPT="${REPORT_DIR}/failover-transcript.txt"
