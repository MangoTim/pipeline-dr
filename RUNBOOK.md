# RUNBOOK — one-time setup for the PROD/DR MCP pipeline demo

Two hosts, two roles:

| Host | Role | Deploy user | MCP endpoint | Page |
|---|---|---|---|---|
| `192.168.147.105` | **PROD** + Jenkins control plane | `rhai` | `http://192.168.147.105:8095/mcp` | `http://192.168.147.105:8084/` |
| `192.168.147.104` | **DR** | `dr` | `http://192.168.147.104:8095/mcp` | `http://192.168.147.104:8084/` |

Everything below is one-time setup. After it, the pipeline is fully automatic.

---

## 1. DR site (`.104`) — run these at the VM console as root

`.104` is a fresh RHEL 8 build. Four things are missing: the pipeline's SSH
key, the two service ports, systemd user-unit persistence, and a Python the
Ansible controller can talk to.

```bash
# ---- 1a. Authorise the pipeline's SSH key ------------------------------
# The pipeline's Ansible controller logs in as 'dr' with the key
# id_rhai108_rsa (the same key your laptop uses).
install -d -m 700 -o dr -g dr /home/dr/.ssh

cat >> /home/dr/.ssh/authorized_keys <<'EOF'
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPZ4XzATvc9OyjL5l5qJjx2HQPgmBTD+w0SIzGv38Gkv rhai-whatsapp-chatbot-linux-mcp
EOF

chown dr:dr /home/dr/.ssh/authorized_keys
chmod 600  /home/dr/.ssh/authorized_keys
restorecon -R -v /home/dr/.ssh          # SELinux is Enforcing on this host

# ---- 1b. Open the two service ports ------------------------------------
#   8095  the MCP server
#   8084  the Lunch Rolltable page
#
# BOTH are needed. The MCP alone is not enough: the drill moves the page and
# the MCP together, and the drill verifies the PAGE from the control plane —
# so a DR site whose firewall only knows 8095 fails the drill with
# "No route to host" even though the page is up and listening locally.
#
# NO --reload. firewalld's reload flushes podman's CNI chains and takes
# down the containers that are already running on this host.
firewall-cmd --permanent --add-port=8095/tcp
firewall-cmd --add-port=8095/tcp
firewall-cmd --permanent --add-port=8084/tcp
firewall-cmd --add-port=8084/tcp

# ---- 1c. Keep the systemd user unit alive ------------------------------
# Without linger, the 'dr' session ends when you log out and the MCP
# container (a systemd USER unit) dies with it.
loginctl enable-linger dr

# ---- 1d. Install python3.9 ---------------------------------------------
# RHEL 8 ships Python 3.6 as /usr/bin/python3, but ansible-core >= 2.15
# requires the TARGET interpreter to be 3.7 or newer. The inventory pins
# /usr/bin/python3.9 on both sites so the controller never auto-discovers a
# different interpreter on one host than the other.
dnf install -y python39
```

### Verify:

```bash
firewall-cmd --zone=public --query-port=8095/tcp    # -> yes
firewall-cmd --zone=public --query-port=8084/tcp    # -> yes
loginctl show-user dr | grep Linger                  # -> Linger=yes
/usr/bin/python3.9 --version                        # -> Python 3.9.x
```

> **Note:** `dr` does **not** need to be in the `wheel` group. The Ansible
> role never escalates to root — it drives the site as `dr` with rootless
> podman, so no sudo password is involved at any point.

---

## 2. PROD site (`.105`) — run these at the VM console as root

`.105` already has everything except the service ports: `rhai` already trusts
the pipeline key, podman 4.9.4 is installed, `python3.9` is present, and
SELinux is Enforcing.

```bash
# ---- 2a. Open the two service ports ------------------------------------
#   8095  the MCP server
#   8084  the Lunch Rolltable page
#
# NO --reload, for the same podman/CNI reason as on .104.
firewall-cmd --permanent --add-port=8095/tcp
firewall-cmd --add-port=8095/tcp
firewall-cmd --permanent --add-port=8084/tcp
firewall-cmd --add-port=8084/tcp

# ---- 2b. Keep the systemd user unit alive ------------------------------
loginctl enable-linger rhai
```

> The podman socket lives at `/run/podman/podman.sock` and is exposed to the
> Jenkins container as `/var/run/docker.sock`. It is **root** podman, so the
> Jenkins build produces an image in the root store — the pipeline exports it
> as a tarball and Ansible loads it into each site's own rootless store, so
> the store the build used never matters.

### Verify:

```bash
firewall-cmd --zone=public --query-port=8095/tcp    # -> yes
loginctl show-user rhai | grep Linger                # -> Linger=yes
```

---

## 3. Jenkins container (`.105`) — the pipeline's toolkit

The `jenkins-with-podman` image ships neither `ansible` nor `python3`.

```bash
# ---- 3a. ansible + python3 into the container --------------------------
podman cp scripts/install-jenkins-tools.sh jenkins:/var/jenkins_home/
podman exec jenkins bash /var/jenkins_home/install-jenkins-tools.sh
```

> This install is **not** baked into the image. Re-run it after any
> container recreate.

```bash
# ---- 3b. the pipeline's SSH key ----------------------------------------
# It goes in JENKINS_HOME, NOT in the container's $HOME: the container
# runs as root, and root's HOME is /home/server — so a "~" in ansible.cfg
# would not resolve to the key. The Jenkinsfile sets ANSIBLE_PRIVATE_KEY_FILE
# explicitly for exactly this reason.
podman exec jenkins mkdir -p /var/jenkins_home/.ssh
podman cp ~/.ssh/id_rhai108_rsa jenkins:/var/jenkins_home/.ssh/
podman exec jenkins chmod 600 /var/jenkins_home/.ssh/id_rhai108_rsa
```

```bash
# ---- 3c. a bare git origin, served over the git protocol ----------------
# The job's SCM url is git://127.0.0.1:9418/mcp-dr-pipeline.git, NOT
# file://... The git plugin refuses to check out a LOCAL directory unless
# the JVM was started with -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true,
# and that flag is read into a static final field at class load — so it
# cannot be enabled at runtime without recreating the shared Jenkins
# container. Serving the same bare repo over the git protocol makes it an
# ordinary REMOTE url and the job just works.
#
# install-jenkins-tools.sh (step 3a) creates the bare repo AND starts the
# daemon, so 3c is already done by the time 3a has run.
podman exec jenkins bash -lc 'git ls-remote git://127.0.0.1:9418/mcp-dr-pipeline.git'
```

```bash
# ---- 3d. push this repository into it ---------------------------------
# /var/jenkins_home/git/... is a path INSIDE the Jenkins container and is
# not reachable from the laptop, so the push runs from inside the container:
podman cp <path-to>/products/mcp-dr-pipeline jenkins:/var/jenkins_home/mcp-dr-pipeline-src
podman exec jenkins bash -c '
  cd /var/jenkins_home/mcp-dr-pipeline-src
  git init -b main
  git add -A
  git commit -m "PROD/DR MCP pipeline demo"
  git push /var/jenkins_home/git/mcp-dr-pipeline.git main
'
```

> `podman cp` of a directory copies its **contents** into the destination,
> so point it at the `mcp-dr-pipeline` directory itself. If the destination
> already exists, remove it first — otherwise the new files land nested
> inside the old directory.

---

## 4. Jenkins job

`Manage Jenkins` → `New Item` → `Pipeline` → name `mcp-dr-pipeline`:

| Field | Value |
|---|---|
| Definition | Pipeline script from SCM |
| SCM | Git |
| Repository URL | `git://127.0.0.1:9418/mcp-dr-pipeline.git` |
| Branches | `*/main` |
| Script Path | `Jenkinsfile` |

Credentials: the `aqua-console` credential (username + password) must
already exist — it is shared with the HKU intranet job.

### 4b. The two drill jobs

Two more pipeline jobs sit next to `mcp-dr-pipeline`, for the times when the
drill is an operator action rather than a side effect of a build:

| Job | Script Path | What it does |
|---|---|---|
| `mcp-failover` | `Jenkinsfile.failover` | warm the DR standby → readiness gate → cut over → verify DR answers |
| `mcp-failback` | `Jenkinsfile.failback` | stop DR → restore PROD → verify PROD answers |

Both are **Pipeline script from SCM**, with the same SCM as above (same URL,
same `*/main` branch). Neither needs the `aqua-console` credential: they do
not build, scan or deploy, so they never touch Aqua — they only need the SSH
key (step 3b) and the Ansible toolkit (step 3a) that are already in the
Jenkins container.

From the Jenkins UI: `Manage Jenkins` → `New Item` → `Pipeline` → the name,
then `Definition: Pipeline script from SCM` with the fields above.

From the API, the `config.xml` of each job is the same as the main job's
apart from the `<scriptPath>` and the absence of a credential:

```bash
TOKEN=$(cat ~/.ssh/jenkins-token)
curl -u admin:${TOKEN} -X POST \
     "http://192.168.147.105:8081/createItem?name=mcp-failover" \
     -H "Content-Type: application/xml" \
     --data-binary @mcp-failover.xml
```

---

## 5. What the pipeline does, in order

| # | Stage | Gate |
|---|---|---|
| 1 | Checkout | clone from the bare origin inside the Jenkins container |
| 2 | Fetch MCP Source | upstream `linux-mcp-server` @ `6d7ca1d1` from GitHub |
| 3 | Fetch App Source | `MangoTim/aqua-rolltable-demo` @ `70cd368` from GitHub |
| 4 | Resolve Version | `v1.0.<DDMMYY><NN>` (Hong Kong time) — ONE version for both artifacts |
| 5 | Build Image | upstream Containerfile, unmodified |
| 6 | Build App Image | upstream Dockerfile, unmodified |
| 7 | Aqua Image Scan | **must print `Image Is Compliant`** |
| 8 | Aqua Image Scan (App) | **must print `Image Is Compliant`** |
| 9 | Trivy Scan | baseline report only (the OS CVEs are gated here) |
| 10 | Trivy Scan (App) | baseline report only |
| 11 | Security Remediation | upgrade the vulnerable Python packages, drop `pip` from the runtime venv; **fails if a CVE has no published fix** |
| 12 | Trivy Final Scan | **no HIGH/CRITICAL library CVEs, no CRITICAL OS CVEs** on the shipped image |
| 13 | Export Artifact | `podman save \| gzip` + `sha256sum`, for both artifacts |
| 14 | Ansible Deploy | the SAME two tarballs to `.105` and `.104` |
| 15 | Verify PROD | the MCP answers `server-gateway.example.com`, **and** the page answers `server-gateway.example.com` through it |
| 16 | Failover Drill | the DR standby is warmed up (MCP **and** page), the **MCP readiness probe** must pass (cores / memory / disk), then PROD stopped → DR answers `localhost.localdomain` |
| 17 | Failback | DR stopped → PROD answers `server-gateway.example.com` again |
| 18 | Archive + Email | `failover-transcript.txt` + scan reports |

> **Two artifacts, one release.** The MCP is the *inspector* — the only
> privileged component, the one that SSHes into the host it runs on. The
> Lunch Rolltable page is the *workload* — what a user actually looks at. Its
> panel asks the MCP which site it is talking to, so the drill has a
> user-visible consequence and not just a changed hostname. They ship as one
> version and they move as one pair.

> The **readiness gate** in stage 16 is the one with teeth. If the MCP reports
> that the DR standby does not have the headroom to take production, the drill
> is **aborted before production is touched**: the standby goes back down, PROD
> keeps serving, and the build fails. The minimums live in `manual/env.sh` and
> in the `environment` block of the Jenkinsfile.

> The scan is deliberately **two-stage**: the first scan is a baseline that
> tells the remediation what to fix, the second scan is the gate on what is
> actually shipped. See README.md → *Security remediation*.

> **What the cutover moves, and what it does not.** The service moves for
> real — the MCP unit and the page unit are stopped on one site and started on
> the other. The *client's* endpoint is changed by the caller, because a
> client-facing address that survives a cutover needs a floating IP, and moving
> an address between hosts requires root on the target (`ip addr add` needs
> `CAP_NET_ADMIN`). Production DR does this with VRRP/keepalived or
> pacemaker + corosync with fencing; this lab deliberately does not, because
> giving the deploy user root on the site it deploys to would undo the one
> property the whole role is built on. README.md → *Design decisions worth
> knowing* has the full reasoning.

> The **readiness gate** in stage 12 is the one with teeth. If the MCP reports
> that the DR standby does not have the headroom to take production, the drill
> is **aborted before production is touched**: the standby goes back down, PROD
> keeps serving, and the build fails. The minimums live in `manual/env.sh` and
> in the `environment` block of the Jenkinsfile.

> The scan is deliberately **two-stage**: the first scan is a baseline that
> tells the remediation what to fix, the second scan is the gate on what is
> actually shipped. See README.md → *Security remediation*.

> **What the cutover moves, and what it does not.** The service moves for
> real — the MCP unit is stopped on one site and started on the other. The
> *client's* endpoint is changed by the caller, because a client-facing
> address that survives a cutover needs a floating IP, and moving an address
> between hosts requires root on the target (`ip addr add` needs
> `CAP_NET_ADMIN`). Production DR does this with VRRP/keepalived or
> pacemaker + corosync with fencing; this lab deliberately does not, because
> giving the deploy user root on the site it deploys to would undo the one
> property the whole role is built on. README.md → *Design decisions worth
> knowing* has the full reasoning.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Authorization denied: tool 'get_system_information'` | the MCP's policy file is missing, so over HTTP every call is denied | check the unit has `-v <home>/.mcp-config:/var/lib/mcp/.config:z` and `-e LINUX_MCP_POLICY_PATH=...` |
| `Failed to connect to ... Connection refused` on `:8095` | firewalld is blocking the port | `firewall-cmd --permanent --add-port=8095/tcp && firewall-cmd --add-port=8095/tcp` |
| `[app] FAIL: cannot reach http://<site>:8084/... [Errno 113] No route to host` | the page IS up and listening locally, but firewalld does not know the app port — 8095 was opened and 8084 was not | `firewall-cmd --permanent --add-port=8084/tcp && firewall-cmd --add-port=8084/tcp` on that site |
| MCP container dies when you log out | systemd user unit without linger | `loginctl enable-linger <user>` |
| `podman run` tries to pull from a registry | the image tag is normalised to `localhost/<name>` | the unit already passes `--pull=never`; keep it |
| SSH key rejected from inside the container | the mounted key lost its SELinux label | the unit mounts with `:z`; do not remove it |
| `podman: permission denied` on the socket | the socket is root podman | expected — the Jenkins container runs as root |
| Jenkins: `ansible-playbook: not found` | the container was recreated | re-run `scripts/install-jenkins-tools.sh` |
| Jenkins: `fatal: repository ... does not exist` on Checkout | the git daemon is not running (container recreated) | re-run `scripts/install-jenkins-tools.sh`, then check `podman exec jenkins git ls-remote git://127.0.0.1:9418/mcp-dr-pipeline.git` |
| Ansible: `/usr/bin/python3: version 3.6 is not supported` | the target interpreter is too old for ansible-core ≥ 2.15 | `dnf install -y python39` on the target; the inventory already pins `/usr/bin/python3.9` |
| Ansible: `Syntax error in template: unexpected '.'` | a podman `--format '{{.Repository}}'` Go template was resolved by Ansible's own templating | wrap the placeholders in `{% raw %}...{% endraw %}` |
| The site still runs the previous image after a deploy | `systemctl --user enable --now` is a no-op on an already-active unit | use `systemctl --user restart` — the role does |
| The site's disk fills up with old images | superseded images are never removed | the role removes them after the restart; check `podman images` |
| Aqua: `TLS handshake timeout` | the aqua-web container lost its outbound path | `podman network reload` on the host |
| Security Remediation: `BLOCKED: ... no published fix` | Trivy found a HIGH/CRITICAL CVE that upstream has not fixed yet | wait for a fix, or add an explicit exception in the remediation script — do not just delete the finding |
| Trivy Final Scan fails after a successful remediation | a `pip install --upgrade` pulled in a vulnerable transitive dependency | upgrade with `--no-deps` (already the default in the Jenkinsfile) so the tree is not reshuffled |

---

## 7. Validating a Jenkinsfile change before pushing it

A Groovy `sh '''...'''` block is **not** the shell script Jenkins runs.
Groovy processes escape sequences inside a single-quoted string:

| In the Jenkinsfile | What the shell actually receives |
|---|---|
| `\\` | `\` |
| `\` at end of line | the backslash **and** the newline vanish — the lines are joined |
| `\n` | a real newline |
| `'''` | **ends the string early** — the rest of the block becomes Groovy code |

So `bash -n` on the raw file proves nothing. Compile the Jenkinsfile against
the same Groovy the controller uses, then render each `sh` block through
Groovy and `bash -n` the result:

```bash
# on .105, inside the Jenkins container
java -cp /tmp/warx/WEB-INF/lib/groovy-all-2.4.21.jar \
    org.codehaus.groovy.tools.FileSystemCompiler -d /tmp/gout Jenkinsfile

java -cp /tmp/warx/WEB-INF/lib/groovy-all-2.4.21.jar \
    groovy.ui.GroovyMain /tmp/ExtractShBlocks.groovy Jenkinsfile /tmp/shblocks

for f in /tmp/shblocks/shblock_*.sh; do bash -n "$f" || echo "FAIL $f"; done
```

`/tmp/ExtractShBlocks.groovy` renders every `sh` block through a
`GroovyShell` and writes out exactly what Jenkins would write to disk.

---

## 8. The manual path — the pipeline, one step at a time

[`manual/README.md`](manual/README.md) has the full guide. The short version:

```bash
# from the laptop
cd products/mcp-dr-pipeline
./manual/remote-run.sh list     # the steps
./manual/remote-run.sh 03        # copy the repo to .105 and run that step
./manual/remote-run.sh all       # every step, in order
```

The steps run on `.105` as `rhai` with **rootless** podman, so they need
nothing from the Jenkins container — except the Aqua credential:

```bash
# on .105, as rhai
mkdir -p ~/.mcp-demo && umask 077
cat > ~/.mcp-demo/aqua.env <<'EOF'
AQUA_USER=administrator
AQUA_PASSWORD=<the aqua console password>
EOF
```

The file is outside the repository on purpose — the Jenkins job takes the
same credential from its own credential store (`aqua-console`).

One difference worth knowing: the Jenkins container has the **root** podman
socket mounted at `/var/run/docker.sock`, while the manual path runs with
rootless podman and therefore starts the podman API service on demand:

```bash
podman system service --time=0 unix:///run/user/$(id -u)/podman/podman.sock
```

Both the Aqua and the Trivy scanner container mount whichever socket they
find there.
