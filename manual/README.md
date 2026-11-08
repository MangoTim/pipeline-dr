# Driving the pipeline by hand

The Jenkins job does all of this in one click. This folder is the same
thing **unbundled** — every stage of the pipeline is a separate script, so
the demo can be run one command at a time and every step can be explained
while it runs.

Each script mirrors one Jenkins stage, uses the same hosts, the same images,
the same gates and leaves the same evidence behind.

There are **two artifacts** and they travel as one release:

- `rhel-mcp` — the *inspector*. The only privileged component. It SSHes into
  the host it runs on and reports what it sees.
- `lunch-rolltable` — the *workload*. The page a user actually looks at. Its
  panel asks the MCP which site it is talking to, so the failover has a
  user-visible consequence and not just a changed hostname.

```
Jenkins stage                  manual script
─────────────────────────────────────────────────────────────────────────────
                                step-00-preflight.sh
Fetch MCP Source                step-01-fetch-source.sh
Fetch App Source                step-01-fetch-source.sh
Resolve Version                 step-02-resolve-version.sh
Build Image                     step-03-build-image.sh
Build App Image                 step-03-build-image.sh
Aqua Image Scan                 step-04-scan-aqua.sh
Aqua Image Scan (App)           step-04-scan-aqua.sh
Trivy Scan (baseline)           step-05-scan-trivy.sh
Trivy Scan (App)                step-05-scan-trivy.sh
Security Remediation            step-06-remediate.sh
Trivy Final Scan                step-07-scan-trivy-final.sh
Export Artifact                 step-08-export-artifact.sh
Ansible Deploy                  step-09-deploy.sh
Verify PROD                     step-10-verify-prod.sh
Failover Drill                  step-11-failover.sh
Failback                        step-12-failback.sh
                                step-13-show-same-artifact.sh  (the evidence)
```

---

## Where it runs

The steps run **on the PROD host, `192.168.147.105`, as the `rhai` user** —
the same machine Jenkins runs on, with rootless podman. Nothing is installed
there for this; the one-time setup in [../RUNBOOK.md](../RUNBOOK.md) is the
same for the Jenkins run and for this one.

The laptop only drives it. `remote-run.sh` copies the repository across and
runs **one** step:

```bash
cd products/mcp-dr-pipeline

./manual/remote-run.sh list        # what the steps are
./manual/remote-run.sh 03           # copy + build the image on .105
./manual/remote-run.sh 03 --no-sync # run it again without copying
./manual/remote-run.sh all          # every step, in order
```

You can also log in and run them directly:

```bash
ssh rhai@192.168.147.105
cd ~/mcp-dr-pipeline
./manual/step-03-build-image.sh
```

---

## The one thing to set up first: the Aqua credential

The Aqua gate needs the console's username and password. That is **not** in
this repository — it never will be. Put it in the deploy user's home
directory, on the host, once:

```bash
ssh rhai@192.168.147.105
mkdir -p ~/.mcp-demo && umask 077
cat > ~/.mcp-demo/aqua.env <<'EOF'
AQUA_USER=administrator
AQUA_PASSWORD=<the aqua console password>
EOF
```

`step-04-scan-aqua.sh` reads that file and refuses to run without it. The
path can be overridden with `AQUA_ENV_FILE`.

---

## The run

### Just the drill — no rebuild, no scan, no deploy

If the image is **already deployed on both hosts** (which it is, after any
successful pipeline run), you can do the whole PROD/DR story with four
commands and nothing else:

```bash
./manual/remote-run.sh 00      # preflight — changes nothing
./manual/remote-run.sh 11      # warm DR, gate it, cut over, verify
./manual/remote-run.sh 12      # fail back to PROD
./manual/remote-run.sh 13      # the same artifact on both sites
```

Steps 11, 12 and 13 read the image tags from the state file, and they have to
name images that are loaded on **both** hosts. Check them first — the state
file is deliberately NOT overwritten by a sync, so it can drift away from
whatever was last deployed:

```bash
ssh rhai@192.168.147.105 'cat ~/mcp-dr-pipeline/.manual-state.env'
ssh rhai@192.168.147.105 'podman images --format "{{.Repository}}:{{.Tag}}"'
```

If they do not match, point them at the deployed tags:

```bash
ssh rhai@192.168.147.105 \
  'sed -i "s|^FULL_IMAGE=.*|FULL_IMAGE=rhel-mcp-remediated:v1.0.04112612|" \
     ~/mcp-dr-pipeline/.manual-state.env'
ssh rhai@192.168.147.105 \
  'sed -i "s|^APP_FULL_IMAGE=.*|APP_FULL_IMAGE=lunch-rolltable:v1.0.04112612|" \
     ~/mcp-dr-pipeline/.manual-state.env'
```

The drill itself does not care which images they are — `dr-warmup.yml` and
`failover.yml` only `systemctl --user start/stop` the two units and never
mention the images. Step 13 does care: it compares the image ID and the
layer digests of those tags against what each host has loaded.

### Which steps can be skipped

| Step | Skip it? | Why |
|---|---|---|
| 00 | yes, once you have done it today | you find a missing key or a closed port halfway through the build |
| 01 | yes, if `upstream/` and `app-src/` are already unpacked | the sources are pinned to one commit each — the rebuild is the same either way |
| 02 | no, unless you deliberately reuse the tag | every later step reads the tag from the state file |
| 03 | yes, if the images are already built | you reuse the images already in the local podman store |
| 04 | **NO** — hard gate | it greps for `Image Is Compliant` and fails if the console says otherwise |
| 05 | yes, but only if you already have the fix list | step 06 reads `manual-reports/trivy-report.json` |
| 06 | no, if the CVEs are not fixed | the remediated image is what 07 gates and what 09 ships |
| 07 | **NO** — hard gate | a HIGH/CRITICAL library CVE fails the step |
| 08 | yes, if the tarballs are already on disk | step 09 needs the files and their sha256 next to them |
| 09 | **yes, for the drill only** | the drill playbooks only start and stop the units |
| 10 | yes, if you are only doing the drill | step 11 re-proves PROD anyway |
| 11 | only if you are not doing the drill | this IS the failover |
| 12 | yes, if you want to LEAVE DR live | otherwise you end with PROD live and DR stopped — the intended posture |
| 13 | yes — evidence, not a gate | but it answers "is it really the same artifact?" |

### 0 — preflight

```bash
./manual/remote-run.sh 00
```

Checks the tools, both sites (over the pipeline's SSH key), the MCP port and
the credential. It changes nothing.

### 1 — fetch the upstream sources

```bash
./manual/remote-run.sh 01
```

Downloads Red Hat's `linux-mcp-server` at the pinned commit into `upstream/`,
and the Lunch Rolltable app at its pinned commit into `app-src/`. Neither
source is **modified** at any point.

### 2 — resolve the version

```bash
./manual/remote-run.sh 02
```

`VERSION` + the Hong Kong date + a run number give the tag
`v1.0.<DDMMYY><NN>` — the same shape the Jenkins job produces from
`BUILD_NUMBER`. The value is kept in `.manual-state.env`, so the later steps
know which images they are dealing with. The app ships as the **same**
version: one release, two artifacts, one pair.

### 3 — build

```bash
./manual/remote-run.sh 03
```

Builds both upstream Containerfiles **as they are**. Two flags matter:

- `--network host` — this host's container egress is dropped in the
  firewalld FORWARD chain, so a bridged build hangs on the `pip install`.
- `--format docker` — podman's default OCI format silently drops the
  HEALTHCHECK instruction; the docker format keeps it and is what the
  scanners expect.

### 4 — the Aqua gate

```bash
./manual/remote-run.sh 04
```

The console decides whether an image may ship — and **both** images go
through it. The step only continues if the report says:

```
Image Is Compliant
```

Anything else stops the run. The HTML reports land in
`manual-reports/aqua-report.html` and `manual-reports/aqua-report-app.html`.

### 5 — the baseline Trivy scan

```bash
./manual/remote-run.sh 05
```

Three scans: the Python dependency tree of the MCP (as JSON — the remediation
step parses it), the OS packages of the MCP base image, and the OS packages
of the app image. **CRITICAL** is a hard gate on both OS scans.

The library findings are deliberately **not** a gate here. This scan is the
input to the next step.

The app has no library tree and no remediation step — it is the Python
standard library and three source files — so its single OS scan *is* its
gate. Its Dockerfile carries an `apt-get upgrade`, and the gate proves the
Debian package set was patched at build time.

### 6 — security remediation

```bash
./manual/remote-run.sh 06
```

Turns the Trivy JSON into a concrete upgrade list and fixes the image:

```
--- packages to upgrade ---
authlib==1.9.1
certifi==2026.10.18
dnspython==2.9.0
joserfc==1.7.5
pyjwt==2.14.0
```

The result is a **derived** image (`FROM` the upstream one), so every
upstream layer, label, env var, user and entrypoint is preserved exactly.
`pip` is deleted from the runtime virtualenv, which takes pip's own vendored
copies (urllib3, msgpack, setuptools) with it.

If Trivy ever finds a HIGH/CRITICAL library CVE **with no published fix**,
this step exits `3` and the run stops rather than shipping a known-vulnerable
image.

### 7 — the final Trivy gate

```bash
./manual/remote-run.sh 07
```

The hard gate, on the image that is about to ship:

- no HIGH/CRITICAL library CVEs
- no CRITICAL OS CVEs

### 8 — export the artifacts

```bash
./manual/remote-run.sh 08
```

`podman save | gzip`, plus the sha256, for **both** images. The artifacts
travel as **files**, not through a registry — the DR site must be able to
receive a promoted image even when the PROD registry is down. That is the
whole point of a DR site.

### 9 — deploy to both sites

```bash
./manual/remote-run.sh 09
```

`ansible-playbook site.yml` copies those two tarballs to `.105` and `.104`.
Each site loads them into its own rootless podman store and runs them as
systemd **user** units. No root, no sudo password, no shared filesystem.

### 10 — verify PROD

```bash
./manual/remote-run.sh 10
```

Asks the PROD endpoint who it is — **and** proves it really reached the host:

```
[verify] get_system_information(host=192.168.147.105) returned:
{"hostname":"server-gateway.example.com", ...}
...
[verify] get_listening_ports(host=192.168.147.105) returned:
=== Listening Ports ===
TCP      0.0.0.0:8095                   LISTEN          users:(("linux-mcp-serve",pid=2150982,fd=8))
...
[verify] PASS: get_listening_ports reports '8095'
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com
```

Two different facts, one MCP session. The first says *which* site is answering;
the second says the answer is real — the MCP process is actually holding port
8095 on that host's socket table, so the hostname cannot have come from a
canned string.

Then the **page** is asked the same question, one layer up:

```
[app] page reports role     : PROD
[app] page reports hostname : server-gateway.example.com
[app] page talks to         : http://127.0.0.1:8095/mcp
[app] MCP tools exposed     : 19
[app] cluster tiles         : PROD=server-gateway.example.com (online) | DR=connection refused
[app] PASS: http://192.168.147.105:8084/api/mcp/status is serving PROD (server-gateway.example.com)
```

The page asks its **own** MCP which site it is talking to, and the MCP
answers with the hostname of the host that is serving the page. That is the
chain `page -> MCP -> host`, and it is what makes the failover visible to a
user.

### 11 — failover

```bash
./manual/remote-run.sh 11
```

This is the step where the MCP earns its place. It does three things in order:

1. **Warm the standby** — `dr-warmup.yml` starts the DR MCP **and** the DR
   page, and waits for both ports. PROD keeps serving throughout.
2. **The readiness gate** — the MCP asks the DR site what it can see of
   *itself*, and the answer is checked:

```
[probe] hostname        : localhost.localdomain
[probe] CPU
[probe]   logical cores : 4
[probe] memory
[probe]   RAM total     : 7.5 GiB
[probe]   RAM available : 5.4 GiB  (72.2 % free)
[probe] disk
[probe]   /            xfs      25.4 GiB total     5.8 GiB used    19.6 GiB free  ( 77.2 % free)
[probe]   (14 pseudo filesystems skipped — tmpfs, overlay, ... — only real ones are gated)

[probe] READY: localhost.localdomain has 4 cores, 72.2 % memory free, 77.2 % disk free
```

   **If the probe fails, the drill is aborted** — the standby goes back down,
   PROD keeps serving, and the step exits `1`:

```
[probe] NOT READY for failover:
[probe]   - only 4 logical cores, need at least 64

BLOCKED: the DR site is not fit to take over. Rolling back.
...
    PROD is still serving — production was never at risk.
```

   A standby that cannot hold the load is never promoted. That is the whole
   reason for putting the MCP in front of the cutover.

3. **The cutover** — stops the PROD page and the PROD MCP, promotes DR, and
   asks again:

```
[verify] PASS: http://192.168.147.104:8095/mcp is serving localhost.localdomain
[app]    PASS: http://192.168.147.104:8084/api/mcp/status is serving DR (localhost.localdomain)
```

**Order matters.** On the way down the page goes first — a page whose MCP has
gone would show a broken panel. On the way up the MCP goes first — the
page's panel has nothing to ask until the MCP answers.

The PROD endpoint is now dead — the script shows that too, for the MCP and
for the page.

> **One honest caveat.** The *service* moves for real — the units are stopped
> on one host and started on the other. The *client's* endpoint is changed by
> the caller, because an address that survives a cutover needs a floating IP,
> and moving an address between hosts needs root on the target. This lab does
> not give the deploy user root; production DR uses VRRP/keepalived or
> pacemaker + corosync with fencing instead. Everything else in the drill is
> real.

### 12 — failback

```bash
./manual/remote-run.sh 12
```

The exact inverse. PROD answers again, and the listening-ports proof shows the
MCP process is back on 8095 on the PROD host. The page comes back too, and
its panel says PROD again.

### 13 — the evidence

```bash
./manual/remote-run.sh 13
```

Both sites, different machines, the same image ID and the same layers — for
**both** artifacts:

```
  192.168.147.105    image id  ec616084ab360b11f21b9d90a4ed825cd39d795770c43e67eceebf7253a946aa
  192.168.147.104    image id  ec616084ab360b11f21b9d90a4ed825cd39d795770c43e67eceebf7253a946aa

  layers (identical content, in order):
       1  sha256:50830ca4b47aab8a2525635f36c715ec73d0f48c37549bdcdd6a5fb0cf4c354a
       2  sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef
       ...

PASS: both sites run the SAME MCP image (ec616084ab36)
      and every one of its layers is byte-identical
```

The *manifest* digest is reported but is not a gate: each site's podman
rebuilds the manifest when it loads the tarball, and the two hosts do not
run the same podman build (`.105` has `4.9.4-rhel`, `.104` has
`4.9.4-dev`), so the manifest bytes — and their hash — differ even though
every layer is identical.

That is what makes the failover meaningful: the same bytes, a different
answer.

---

## The evidence a manual run leaves behind

Everything lands in `manual-reports/` on the control plane:

| File | What it is |
|---|---|
| `aqua-report.html` | the Aqua compliance report (MCP) |
| `aqua-report-app.html` | the Aqua compliance report (app) |
| `aqua-scan.err` / `aqua-scan-app.err` | the scanner's own log |
| `trivy-report.json` / `trivy-report.txt` | the baseline library scan (machine + human readable) |
| `trivy-os-report.txt` | the baseline OS scan (MCP) |
| `trivy-app-os-report.txt` | the OS scan of the app image |
| `pip-list.txt` | what is really installed in the upstream image |
| `cve-fixes.txt` | the packages the remediation upgraded |
| `trivy-final-report.txt` | the final library gate |
| `trivy-final-os-report.txt` | the final OS gate |
| `image-inspect.txt` | the image ID and digest from both sites, for both artifacts |
| `failover-transcript.txt` | the PROD → DR → PROD transcript |

The transcript is the same file the Jenkins job archives:

```
===== PROD verification =====
[verify] PASS: get_listening_ports reports '8095'
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com

===== DR READINESS PROBE (before any cutover) =====
[probe] READY: localhost.localdomain has 4 cores, 72.2 % memory free, 77.2 % disk free

===== FAILOVER: DR is now serving =====
[verify] PASS: http://192.168.147.104:8095/mcp is serving localhost.localdomain

===== FAILBACK: PROD is serving again =====
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com
```

---

## Notes and gotchas

- **The rootless podman API socket.** The Aqua and Trivy scanners reach the
  local image through a container engine socket. Rootless podman does not
  expose one by default, so `step-00` starts `podman system service` on
  demand. In the Jenkins container the root socket is bind-mounted at
  `/var/run/docker.sock` instead — same idea.
- **`systemctl --user enable --now` is a no-op** on an already-active unit.
  A redeploy would load the new image into the store but leave the container
  running the old one. The Ansible role therefore uses `restart`.
- **Never `firewall-cmd --reload`** on these hosts. It flushes podman's CNI
  chains and takes down the containers that are already running.
- **The state file is `.manual-state.env`** in the repository root on the
  host. Delete it to start a fresh run with a new tag.
- **`remote-run.sh` does NOT sync the state file** — it is excluded from the
  copy on purpose, so a fresh `FULL_IMAGE` does not overwrite the one the
  later steps are using. The flip side: it does **not** follow a deploy
  either. If the pipeline shipped a newer image, `FULL_IMAGE` and
  `APP_FULL_IMAGE` still point at the old tags and steps 11–13 fail on the
  image inspect. Point them at the deployed tags before running the drill.
- **Both service ports have to be open on both sites** — 8095 for the MCP and
  8084 for the page. A site whose firewall only knows 8095 fails the drill's
  page check with `No route to host` even though the page is up and
  listening locally. See ../RUNBOOK.md.
- **Step 02 can be re-run** to get a new version number — it increments the
  counter in the state file.
- **The build takes a while** (the upstream image installs a Python venv
  from PyPI). The scanners take a minute each. The whole run is roughly 15
  minutes.

---

## Files

| File | What it is |
|---|---|
| `env.sh` | every host, port, image name and version — change things here |
| `lib.sh` | the shared helpers: banners, state, podman socket, the verify call |
| `step-NN-*.sh` | one step each |
| `run-all.sh` | every step in order |
| `remote-run.sh` | the laptop-side driver: sync + run one step |
