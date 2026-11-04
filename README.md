# PROD/DR MCP Pipeline Demo

One pipeline builds and scans **one** image, Ansible deploys **that exact
artifact** to a PROD and a DR site, and the MCP answers from whichever site
is live — with a recorded transcript proving it.

```
                         .105   PROD  (control plane)
   ┌──────────────────────────────────────────────────────────┐
   │  Jenkins :8081                                            │
   │    Checkout → Fetch → Build → Aqua scan → Trivy           │
   │    → Security Remediation → Trivy Final Scan              │
   │    → Export artifact → Ansible Deploy → Verify PROD       │
   │    → Failover Drill → Failback → Archive + Email          │
   │                                                          │
   │  ansible-playbook ───────────┐                            │
   │  git://127.0.0.1:9418/...    ▼                            │
   │                    ┌───────────────────┐                  │
   │  podman build ──►  │ rhel-mcp:v1.0.x  │                  │
   │                    └─────────┬─────────┘                  │
   │                              │ podman save | gzip         │
   │  rhel-mcp :8095/mcp ─────────┼──────────► tarball         │
   │     ssh 127.0.0.1 ─► host sshd                            │
   └──────────────────────────────┼───────────────────────────┘
                                  ▼
                         .104   DR
   ┌──────────────────────────────────────────────────────────┐
   │  rhel-mcp :8095/mcp   (SAME image, SAME digest)          │
   │    ssh 127.0.0.1 ─► host sshd (as dr)                    │
   └──────────────────────────────────────────────────────────┘
```

The demo punchline: the **same artifact** answers with a **different
hostname** depending on which site is live. That is only possible because the
MCP inspects the host it is deployed on, over SSH.

---

## What is deployed

Red Hat's official **[linux-mcp-server](https://github.com/rhel-lightspeed/linux-mcp-server)**,
**unmodified** — upstream commit `6d7ca1d1da8598c2e816fd69e98b8f7cf97da0d1`
(27 commits past tag `1.5.0`). No custom MCP server, no forked code. The
upstream `Containerfile` is used as-is, straight from the pinned tarball that
the pipeline downloads from GitHub at build time.

> "Unmodified" means the upstream **source** is untouched. The pipeline *does*
> harden the **image** it ships — see [Security remediation](#security-remediation)
> below: five real CVEs are fixed by upgrading the affected Python packages,
> and `pip` is removed from the runtime venv. No upstream file is patched.

The upstream image sets `ENV container=docker`, which makes the server
**refuse to execute locally** and require a remote `host` over SSH. That is
deliberate, and it is exactly what makes this demo work: the container runs
with `--network host` and inspects **its own host's sshd**, so the answer
identifies the site that is actually serving.

19 read-only tools are exposed: `get_system_information`, `get_disk_usage`,
`get_cpu_information`, `get_memory_information`, `list_services`,
`get_service_status`, `get_journal_logs`, `list_processes`,
`get_network_interfaces`, `get_listening_ports`, `list_block_devices`,
`list_files`, `list_directories`, `read_file`, and more.

---

## Layout

```
products/mcp-dr-pipeline/
├── README.md                     # this file
├── RUNBOOK.md                    # one-time setup on both hosts
├── VERSION                       # "1.0" -> tag v1.0.<DDMMYY><NN>
├── Jenkinsfile                   # the pipeline (13 stages + post-actions)
├── ansible/
│   ├── ansible.cfg
│   ├── inventory.ini             # [mcp_prod] .105 as rhai / [mcp_dr] .104 as dr
│   ├── site.yml                  # deploy the artifact to every site
│   ├── failover.yml              # stop PROD, promote DR
│   ├── failback.yml              # stop DR, restore PROD
│   └── roles/mcp/
│       ├── defaults/main.yml
│       ├── tasks/main.yml
│       └── templates/
│           ├── mcp.service.j2    # the systemd USER unit
│           └── policy.yaml.j2    # the MCP authorization policy
└── scripts/
    ├── mcp_verify.py             # MCP client: tools/list + get_system_information
    ├── trivy_cve_packages.py     # Trivy JSON -> pip upgrade list
    └── install-jenkins-tools.sh  # ansible + python3 into the Jenkins container
```

---

## Design decisions worth knowing

**No `become`, anywhere.** Each site is driven as its own non-root user
(`rhai` on PROD, `dr` on DR) with rootless podman. `dr` never needs to be in
`wheel` and no sudo password is involved at any point. The role runs
`systemctl --user`, which needs `loginctl enable-linger` to survive logout.

**The artifact travels as a tarball, not through the registry.** The DR site
must be able to receive a promoted image even when the PROD registry is down —
that is the whole point of a DR site. The pipeline exports
`podman save | gzip`, and Ansible copies that one file to both sites, which
load it into their own rootless podman store. Both sites therefore run
byte-identical content.

**A deploy restarts the unit, and the old image is removed.** `systemctl
--user enable --now` is a **no-op** when the unit is already active, so the
container would keep running the *previous* image even though the new one was
just loaded. The role therefore uses `systemctl --user restart`, which recreates
the container on the new image, and afterwards removes every superseded MCP
image from the site's store — otherwise each build would leave 325 MB behind.

**The keypair is generated on the site.** The role creates
`~/.mcp-keys/id_mcp` on each site and appends its public half to that site's
`authorized_keys`. No secret ever travels from the controller, and each site
gets its own revocable key.

**The key lives in a dedicated directory.** `~/.mcp-keys`, not `~/.ssh`. The
`:z` SELinux relabel that the bind mount needs would otherwise change the
context of the host's own `authorized_keys` and break the host's SSH logins.

**`--userns=keep-id:uid=1001,gid=1001`.** The container's uid 1001 maps to the
host's uid 1001 — the deploy user — so the mounted private key (mode 0600,
owned by that user) stays readable from inside the container.

**The MCP needs an authorization policy.** Over an HTTP transport the upstream
server evaluates *every* tool call against a policy file and denies anything
that no rule matches. The "allow everything" behaviour only exists for the
stdio transport. The role installs `policy.yaml` with a single rule
(`host: "*"`, `tools: ["*"]`, `action: ssh_default`, `all_users: true`);
`ssh_default` means "use the SSH user and key from `LINUX_MCP_USER` /
`LINUX_MCP_SSH_KEY_PATH`", which the unit sets per site.

---

## Security remediation

The upstream image ships with 19 HIGH/CRITICAL library findings. Rather than
wave them through, the pipeline **fixes them** in a derived image and then
**re-gates** on the result.

`scripts/trivy_cve_packages.py` reads the Trivy JSON report and turns it into a
concrete `pip install --upgrade` list:

- **14 findings are real** — Authlib 1.7.2, PyJWT 2.13.0, certifi 2026.7.22,
  dnspython 2.8.0, joserfc 1.7.4. These live in the runtime venv and are
  upgraded to their fixed versions.
- **5 findings are `pip`'s own vendored copies** — msgpack ×2, setuptools,
  urllib3 ×2, all reported with `PkgPath: None` from
  `site-packages/pip/_vendor/`. The MCP never imports them. The script
  detects this (the package is not in `pip list`) and skips it; the
  remediation then **deletes `pip` from the runtime venv**, which removes the
  findings for good.

The remediation builds a derived image with `FROM <upstream>` — not
`podman commit`, which would clobber the upstream `Entrypoint`, `Cmd` and
`User`. Only the Python packages change; the entrypoint, labels, environment
and user are inherited untouched. The build then asserts the MCP still
imports (`fastmcp`, `linux_mcp_server`, `asyncssh`).

If Trivy ever finds a HIGH/CRITICAL library CVE **with no published fix**, the
stage exits `3` and the pipeline **fails** rather than shipping a known-vulnerable
image.

The result: **19 → 0** HIGH/CRITICAL library CVEs, with the OS gate
(no CRITICAL) unchanged.

---

## The 10-minute demo script

### 0. Before you start (one-time, see RUNBOOK.md)

Open port 8095 on both hosts, install `python3.9` on both, enable linger for
`rhai` and `dr`, and install ansible + python3 + the git daemon into the
Jenkins container (that script also creates the bare git origin).

### 1. Run the pipeline

Jenkins → `mcp-dr-pipeline` → **Build Now**. Thirteen stages:

```
Checkout → Fetch MCP Source → Resolve Version → Build Image
  → Aqua Image Scan → Trivy Scan → Security Remediation
  → Trivy Final Scan → Export Artifact
  → Ansible Deploy → Verify PROD → Failover Drill → Failback
```

The two scan gates are worth watching. The Aqua gate is a hard stop:

```
+ grep -q Image Is Compliant aqua-report.html
```

The remediation stage shows what it fixed:

```
--- packages to upgrade ---
authlib==1.9.1
certifi==2026.10.18
dnspython==2.9.0
joserfc==1.7.5
pyjwt==2.14.0
```

and the final Trivy scan must come back with zero HIGH/CRITICAL library CVEs.

Then the two verification gates:

```
[verify] tools exposed (19): get_cpu_information, get_disk_usage, ...
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com
```

and, after the failover drill:

```
[verify] PASS: http://192.168.147.104:8095/mcp is serving localhost.localdomain
```

### 2. Show that PROD is live

```bash
curl -s -X POST http://192.168.147.105:8095/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"demo","version":"1.0"}}}'
```

### 3. Show that the artifact is identical on both sites

```bash
ssh rhai@192.168.147.105 'podman image inspect localhost/rhel-mcp-remediated:v1.0.<tag> --format "Id={{.Id}} Digest={{.Digest}}"'
ssh dr@192.168.147.104  'podman image inspect localhost/rhel-mcp-remediated:v1.0.<tag> --format "Id={{.Id}} Digest={{.Digest}}"'
```

Both sites print the **same image ID and the same digest**. Different hosts,
byte-identical content.

### 4. Ask the MCP a question (any MCP client)

```
get_system_information(host="192.168.147.105")
  -> hostname: server-gateway.example.com

get_system_information(host="192.168.147.104")
  -> hostname: localhost.localdomain
```

### 5. Fail over, live

The pipeline ends with the **failback**, so DR is stopped and PROD is the live
site. Start DR, then stop PROD — now there is exactly one live site.

```bash
# bring the DR site up (the pipeline's failback left it stopped)
ssh dr@192.168.147.104 'systemctl --user start rhel-mcp.service'

# take PROD down — DR is now the only live site
ssh rhai@192.168.147.105 'systemctl --user stop rhel-mcp.service'
```

Now `.105` refuses connections and `.104` is the only live site. Ask the MCP
about the DR host — it answers. Ask it about the PROD host — it is down.

```bash
# fail back: stop DR, bring PROD up again
ssh dr@192.168.147.104 'systemctl --user stop rhel-mcp.service'
ssh rhai@192.168.147.105 'systemctl --user start rhel-mcp.service'
```

### 6. Show the evidence

Jenkins build → **Artifacts** → `failover-transcript.txt`:

```
===== PROD verification =====
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com

===== FAILOVER: DR is now serving =====
[verify] PASS: http://192.168.147.104:8095/mcp is serving localhost.localdomain

===== FAILBACK: PROD is serving again =====
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com
```

---

## Driving it by hand (without Jenkins)

This path skips the **security remediation**, so the image you build by hand
still carries the upstream HIGH/CRITICAL library findings. Use it to
experiment with the MCP itself; use the pipeline when you want the hardened
artifact.

```bash
# build
curl -fsSL -o mcp-src.tar.gz \
  "https://github.com/rhel-lightspeed/linux-mcp-server/archive/6d7ca1d1da8598c2e816fd69e98b8f7cf97da0d1.tar.gz"
mkdir -p upstream && tar -xzf mcp-src.tar.gz -C upstream --strip-components=1
podman build --file upstream/Containerfile --format docker --network host \
    -t rhel-mcp:v1.0.manual upstream

# export
podman save rhel-mcp:v1.0.manual | gzip > rhel-mcp-v1.0.manual.tar.gz

# deploy to both sites
cd ansible
ansible-playbook -i inventory.ini site.yml \
    -e mcp_image=rhel-mcp:v1.0.manual \
    -e mcp_artifact=$(cd .. && pwd)/rhel-mcp-v1.0.manual.tar.gz

# verify
podman run -i --rm --network host \
    --entrypoint /opt/venvs/mcp/bin/python \
    rhel-mcp:v1.0.manual \
    - --url http://192.168.147.105:8095/mcp \
       --target 192.168.147.105 --expect server-gateway.example.com \
    < ../scripts/mcp_verify.py
```

---

## Out of scope

- **NetApp / shared storage.** The demo deliberately has no shared
  filesystem: the artifact travels as a tarball, which is the point.
- **The chatbot's MCP registry.** The chatbot can already consume this MCP
  through the existing `mcp-http-bridge.js`; wiring it in is a separate
  exercise.
- **Patching upstream source.** No file in `linux-mcp-server` is edited — the
  policy file, the systemd unit, the verify client and the remediation script
  all live in this repository. The *image* is hardened after the build (see
  [Security remediation](#security-remediation)); the *source* is untouched.
