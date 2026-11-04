# PROD/DR MCP Pipeline Demo

One pipeline builds and scans **one** image, Ansible deploys **that exact
artifact** to a PROD and a DR site, and the MCP answers from whichever site
is live — with a recorded transcript proving it.

Repository: <https://github.com/MangoTim/pipeline-dr>

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
│   ├── dr-warmup.yml             # start the DR standby, WITHOUT touching PROD
│   ├── failover.yml              # stop PROD, promote DR
│   ├── failback.yml              # stop DR, restore PROD
│   └── roles/mcp/
│       ├── defaults/main.yml
│       ├── tasks/main.yml
│       └── templates/
│           ├── mcp.service.j2    # the systemd USER unit
│           └── policy.yaml.j2    # the MCP authorization policy
├── manual/                       # the SAME pipeline, one step at a time
│   ├── README.md                 # how to drive it by hand
│   ├── env.sh                    # every host, port, image and version
│   ├── lib.sh                    # the shared helpers
│   ├── step-00-preflight.sh      # ... one script per pipeline stage
│   ├── ...
│   ├── step-13-show-same-artifact.sh
│   ├── run-all.sh                # every step in order
│   └── remote-run.sh             # laptop side: sync + run one step
└── scripts/
    ├── mcp_verify.py             # MCP client: tools/list + get_system_information
    ├── mcp_dr_probe.py           # MCP client: the DR readiness gate
    ├── trivy_cve_packages.py     # Trivy JSON -> pip upgrade list
    └── install-jenkins-tools.sh  # ansible + python3 into the Jenkins container
```

---

## Design decisions worth knowing

**No `become`, anywhere.** Each site is driven as its own non-root user
(`rhai` on PROD, `dr` on DR) with rootless podman. `dr` never needs to be in
`wheel` and no sudo password is involved at any point. The role runs
`systemctl --user`, which needs `loginctl enable-linger` to survive logout.

**The cutover moves the service; the caller is told the new address.** The
failover itself is a real state change — `systemctl --user stop
rhel-mcp.service` on PROD, `start` on DR, so the container really is running
on the other host. What the drill script *also* does is point the next
request at that host: the endpoint the client uses goes from
`http://192.168.147.105:8095/mcp` to `http://192.168.147.104:8095/mcp`.

That is the one simulated part of the demo, and it is simulated on purpose. A
client-facing address that survives a cutover needs a **floating IP** — an
address that belongs to no machine until it is added to one — and on Linux
that is `ip addr add`, which needs `CAP_NET_ADMIN`, i.e. **root on the
target**. Adding it would undo the property the rest of this pipeline is
built on: the deploy user never has root on the site it deploys to.

Production DR solves it with a routing protocol instead — VRRP/keepalived, or
pacemaker + corosync with fencing — where the two servers elect a master and
the address follows it, with split brain actively prevented. Putting that in
this lab would mean a root helper on both hosts plus a rollback path for a
half-finished move.

So the demo draws the line here: **the service moves for real; the address is
changed by the caller.** Everything else is checkable — one tarball, two
rootless stores, a unit genuinely stopped and started, and an MCP that
reports the live site's own kernel state (hostname, cores, RAM, disk) rather
than a canned string.

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

## What the MCP actually does in this pipeline

The MCP is not decoration in the middle of the pipeline — it is the thing
that **decides whether the drill is allowed to happen**. Five of its 19 tools
are load-bearing; the other fourteen are exposed and callable, but the demo
does not need them.

| Tool | Where it is used | What it proves that nothing else could |
|---|---|---|
| `get_system_information` | steps 10, 11, 12 | **Which site is live.** Same image, different hostname — the MCP answers from whichever host it is deployed on. This is the demo's punchline. |
| `get_listening_ports` | steps 10, 11, 12 | **The answer is real.** Port 8095 on that host is held by the `linux-mcp-server` process, so the hostname cannot have come from a canned string. |
| `get_cpu_information` | step 11 (readiness) | **Is the standby big enough?** The core count of the DR box, measured by the same tool that will later report on it in production. |
| `get_memory_information` | step 11 (readiness) | **Is there room to run?** How much of the DR box's RAM is actually available, not what the spec sheet says. |
| `get_disk_usage` | step 11 (readiness) | **Is there room to write?** Free space on the tightest real filesystem on the DR box. |

### The readiness gate

The failover drill does not blindly promote the standby. Before it touches
production it asks the DR site what it can see of *itself*:

```
[probe] hostname        : localhost.localdomain
[probe]   logical cores : 4
[probe]   RAM available : 5.4 GiB  (72.2 % free)
[probe]   /            xfs      25.4 GiB total     5.8 GiB used    19.6 GiB free  ( 77.2 % free)

[probe] READY: localhost.localdomain has 4 cores, 72.2 % memory free, 77.2 % disk free
```

and it compares that against the minimums in `manual/env.sh` (2 cores, 10 %
memory free, 10 % disk free on the tightest filesystem). If the standby does
not meet them, **the drill is aborted**: the standby goes back down, PROD keeps
serving, and the step exits `1`.

```
[probe] NOT READY for failover:
[probe]   - only 4 logical cores, need at least 64

BLOCKED: the DR site is not fit to take over. Rolling back.
...
    PROD is still serving — production was never at risk.
```

That is the difference between a failover *demonstration* and a failover
*gate*: a demonstration proves the switch happened, a gate proves the switch
was safe.

### The other fourteen tools

`get_hardware_information`, `get_journal_logs`, `read_log_file`,
`get_network_interfaces`, `get_network_connections`, `list_processes`,
`get_process_info`, `list_services`, `get_service_status`, `get_service_logs`,
`list_block_devices`, `list_directories`, `list_files` and `read_file` are all
exposed and all work over the same SSH transport — they are simply not needed
to prove a failover. They are the natural extension points: `get_service_status`
is the tool to reach for if the drill ever needs to assert that `sshd` is
healthy on the site being promoted, and `list_services` / `get_journal_logs`
are how you would show *why* a site was not ready.

One note on the transport: over HTTP the MCP evaluates **every** tool call
against the authorization policy, and a call that matches no rule is denied.
There is no implicit "allow" over HTTP — that behaviour only exists on the
stdio transport. The role therefore installs `policy.yaml` with a single
wildcard rule.

---

## How the PROD/DR drill works

### The pipeline: build once, deploy the same bytes to both sites

```
  ┌──────────── .105  PROD  (control plane) ─────────────┐
  │                                                      │
  │   Jenkins :8081                                      │
  │                                                      │
  │     ① Checkout → ② Fetch MCP source → ③ Version      │
  │            │                                         │
  │            ▼                                         │
  │     ④ podman build    (Red Hat's own Containerfile,   │
  │                       unmodified)                    │
  │            │                                         │
  │            ▼                                         │
  │     ⑤ Aqua scan ──GATE──► ⑥ Trivy (baseline)        │
  │                                  │                   │
  │                                  ▼                   │
  │                        ⑦ Remediate  (upgrade the      │
  │                            packages, drop pip →       │
  │                            a DERIVED image)           │
  │                                  │                   │
  │                                  ▼                   │
  │                        ⑧ Trivy final ──GATE──► ⑨ Export │
  │                           0 HIGH/CRITICAL    rhel-mcp-…tgz│
  └──────────────────────────────────────┬───────────────┘
                                         │  ONE tarball, ONE sha256
                        ┌────────────────┴─────────────────┐
                        ▼                                  ▼
          .105  PROD   (rhai)                  .104  DR   (dr)
          ┌──────────────────────┐            ┌──────────────────────┐
          │ podman load          │            │ podman load          │
          │ systemd --user unit  │            │ systemd --user unit  │
          │ rhel-mcp :8095/mcp   │            │ rhel-mcp :8095/mcp   │
          │        │             │            │        │             │
          │        └─ SSH ───────┼──► .105    │        └─ SSH ───────┼──► .104
          │                      │   sshd     │                      │   sshd
          └──────────────────────┘            └──────────────────────┘
            same image, same bytes              same image, same bytes
            answers                             answers
            "server-gateway.example.com"       "localhost.localdomain"
```

The container talks to **its own host's sshd** — that is what makes the answer
identify the site: the MCP inspects the machine it is deployed on, so the same
image gives a different answer on each box.

### The drill: five moves, production never at risk until move ④

```
  move   PROD .105                            DR .104
  ────   ────────────────────────────         ────────────────────────────
   ①     ● live, :8095 answering              ○ stopped

   ②     ● still serving  ─── warm it up ──►  start the unit
          (production untouched)               wait for :8095 to accept

   ③     ● still serving  ── readiness ────►  get_system_information
          the gate runs WHILE                  get_cpu_information
          PROD is serving                      get_memory_information
                                               get_disk_usage
                                            → 4 cores · 72 % RAM free · 77 % disk free
                                            ✔ READY → carry on
                                            ✗ NOT READY → abort: DR goes back
                                              down, PROD keeps serving, the step
                                              FAILS. The standby is never promoted.

   ④     ● still serving  ── THE CUTOVER ──►  start the unit
          stop the PROD unit                   :8095 now answers on .104

   ⑤     ○ stopped      ─── VERIFY ───────►  get_system_information
          :8095 refused                        → localhost.localdomain
                                               get_listening_ports
                                               → 8095 held by linux-mcp-server
```

Move ⑤ is the proof, and it is two facts in one session: the hostname says
*which* site is live, and the socket table says the answer is real — the
`linux-mcp-server` process really holds port 8095 on that host, so the
hostname cannot have been a canned string.

**Failback (step 12)** is the mirror image: stop DR, start PROD, verify that
`.105` answers `server-gateway.example.com` again. The pipeline deliberately
*ends* in that posture — PROD live, DR stopped — so the demo always starts
from a known state.

---

## The 10-minute demo script

> **Want to drive it by hand instead?** [`manual/`](manual/README.md) is the
> same pipeline unbundled — one script per stage, so you can stop between
> any two of them and explain what just happened. From the laptop:
>
> ```bash
> ./manual/remote-run.sh list        # the steps
> ./manual/remote-run.sh 03           # build the image on .105
> ./manual/remote-run.sh 11           # the failover drill
> ./manual/remote-run.sh all          # the whole thing
> ```

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
ssh rhai@192.168.147.105 'podman image inspect localhost/rhel-mcp-remediated:v1.0.<tag> --format "Id={{.Id}} Layers={{.RootFS.Layers}}"'
ssh dr@192.168.147.104  'podman image inspect localhost/rhel-mcp-remediated:v1.0.<tag> --format "Id={{.Id}} Layers={{.RootFS.Layers}}"'
```

Both sites print the **same image ID** and **the same layer digests** —
different hosts, byte-identical content.

> The *manifest* digest (`{{.Digest}}`) can differ between the two sites,
> and that is expected: each site's podman rebuilds the manifest when it
> loads the tarball, and the two hosts do not run the same podman build
> (`.105` has `4.9.4-rhel`, `.104` has `4.9.4-dev`). The image ID — the
> hash of the image configuration — and the layer hashes are the content
> identity, and those do match.

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

> **Say this while you do it.** In production the client would keep the *same*
> address across the cutover — a floating IP, or a DNS name that follows the
> live site. This lab has the drill pass the new address to the caller
> instead, because moving an address between hosts needs root on the target and
> this demo never gives the deploy user root. The **service** really did move:
> the unit is stopped on `.105` and running on `.104`.

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
