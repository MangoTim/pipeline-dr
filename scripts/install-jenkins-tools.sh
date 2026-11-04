#!/usr/bin/env bash
# Install the tools the mcp-dr-pipeline Jenkins job needs, INSIDE the Jenkins
# container on 192.168.147.105.
#
# The jenkins-with-podman image is a slim Debian image that ships neither
# python3 nor ansible. Both are needed:
#
#   ansible-playbook  — stage 7 (Deploy) and the failover / failback drills
#   python3           — the MCP verify client (scripts/mcp_verify.py) is run
#                       inside the MCP image, but the pipeline itself needs
#                       python3 for the Ansible controller
#
# It also starts the local git daemon that serves the pipeline's own bare
# origin to Jenkins.
#
# Why a git daemon and not a file:// URL:
#   The git plugin refuses to check out a LOCAL directory unless the JVM was
#   started with -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true, and
#   that flag is read once into a static final field, so it cannot be set at
#   runtime. Serving the same bare repository over the git protocol
#   (git://127.0.0.1:9418/...) makes it an ordinary REMOTE url and the job
#   works without recreating the shared Jenkins container.
#
# The install is NOT baked into the image, so it is lost if the container is
# recreated. Re-run this script after any container recreate, and keep the
# Containerfile change in the repo so a future rebuild is reproducible.
#
# Usage (from the host, as the account that owns the container):
#
#   podman exec -it jenkins bash -c 'bash /var/jenkins_home/install-jenkins-tools.sh'
#
# or copy it in first:
#
#   podman cp install-jenkins-tools.sh jenkins:/var/jenkins_home/install-jenkins-tools.sh
#   podman exec jenkins bash /var/jenkins_home/install-jenkins-tools.sh
#
set -euo pipefail

GIT_DAEMON_PORT="${GIT_DAEMON_PORT:-9418}"
GIT_ROOT="${GIT_ROOT:-/var/jenkins_home/git}"
GIT_REPO="${GIT_ROOT}/mcp-dr-pipeline.git"

echo "=== before ==="
command -v ansible-playbook || echo "ansible-playbook: MISSING"
command -v python3 || echo "python3: MISSING"

export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y --no-install-recommends \
    ansible \
    python3 \
    python3-pip \
    openssh-client \
    git \
    ca-certificates \
    gzip \
    rsync

apt-get clean
rm -rf /var/lib/apt/lists/*

echo ""
echo "=== local git origin ==="
mkdir -p "${GIT_ROOT}"
if [ ! -d "${GIT_REPO}" ]; then
    git init --bare -b main "${GIT_REPO}"
    echo "created ${GIT_REPO}"
else
    echo "${GIT_REPO} already exists"
fi

# (Re)start the git daemon that serves it. Idempotent: if the daemon is
# already listening, leave it alone.
if pgrep -f "git-daemon.*--port=${GIT_DAEMON_PORT}" >/dev/null 2>&1; then
    echo "git daemon already running on port ${GIT_DAEMON_PORT}"
else
    git daemon --detach --reuseaddr \
        --listen=127.0.0.1 \
        --port="${GIT_DAEMON_PORT}" \
        --base-path="${GIT_ROOT}" \
        --export-all \
        "${GIT_ROOT}"
    sleep 1
    echo "git daemon started on port ${GIT_DAEMON_PORT}"
fi

echo ""
echo "=== after ==="
python3 --version
ansible-playbook --version | head -1
ssh -V 2>&1
git --version
git ls-remote "git://127.0.0.1:${GIT_DAEMON_PORT}/mcp-dr-pipeline.git" 2>&1 | head -3 || true

echo ""
echo "OK — the Jenkins agent can now run ansible-playbook and python3,"
echo "    and the pipeline origin is served at"
echo "    git://127.0.0.1:${GIT_DAEMON_PORT}/mcp-dr-pipeline.git"
