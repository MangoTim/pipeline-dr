"""Build PROD-DR-MCP-Pipeline-Cheatsheet.docx.

The fast version of the guide: one line per step (what it is for) plus the
command that step actually runs. Ends with a command sheet you can present
from.

    python docs/guide/build_cheatsheet.py

Writes PROD-DR-MCP-Pipeline-Cheatsheet.docx next to this script. Re-runnable.
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Reuse the guide's house style rather than duplicating it.
from build_guide import (  # noqa: E402
    BLUE, GREY, INK, AMBER, GREEN,
    _border, _header_footer, _page_field, _shade,
    bullet, callout, code, h1, h2, h3, p, rich, table,
)

OUT = HERE / "PROD-DR-MCP-Pipeline-Cheatsheet.docx"

IMG = "rhel-mcp-remediated:v1.0.04112612"
SOCK = "/run/user/1001/podman/podman.sock"
TRIVY = "docker.io/aquasec/trivy:0.76.1"
AQUA = "registry.aquasec.com/scanner:2022.4.868"


# --------------------------------------------------------------- step block --
def step(doc, num: str, script: str, purpose: str, command: str,
         caption: str | None = None) -> None:
    """One step: the number, the script, what it is for, and the command."""
    head = doc.add_paragraph()
    head.paragraph_format.space_before = Pt(14)
    head.paragraph_format.space_after = Pt(0)
    head.paragraph_format.keep_with_next = True

    run = head.add_run(f"STEP {num}")
    run.font.size = Pt(13)
    run.font.bold = True
    run.font.color.rgb = BLUE

    run = head.add_run(f"   {script}")
    run.font.size = Pt(9)
    run.font.name = "Consolas"
    run.font.color.rgb = GREY

    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(1)
    para.paragraph_format.space_after = Pt(2)
    para.paragraph_format.keep_with_next = True
    run = para.add_run(purpose)
    run.font.size = Pt(10.5)
    run.font.color.rgb = INK

    code(doc, command, caption)


# ------------------------------------------------------------------- build ---
def build() -> None:
    doc = Document()
    _header_footer(doc)

    # ------------------------------------------------------------- title ----
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(2)
    run = title.add_run("PROD/DR MCP Pipeline")
    run.font.size = Pt(26)
    run.font.bold = True
    run.font.color.rgb = BLUE

    sub = doc.add_paragraph()
    sub.paragraph_format.space_after = Pt(10)
    run = sub.add_run("Quick reference — what each step is for, and the command it runs")
    run.font.size = Pt(12)
    run.font.color.rgb = GREY
    _border(sub, "0B3D91", 6)

    p(doc, "One pipeline builds and scans ONE image. Ansible ships that exact "
           "artifact to two machines — PROD (.105) and DR (.104) — and the "
           "MCP answers from whichever one is live. The steps below are the "
           "manual version of that pipeline: one script per stage, so you can "
           "stop between any two of them and say what just happened.")

    h2(doc, "How to drive it")
    p(doc, "From the laptop, in the repository:")
    code(doc, """cd products/mcp-dr-pipeline

./manual/remote-run.sh list        # what the steps are
./manual/remote-run.sh 00          # preflight — checks, changes nothing
./manual/remote-run.sh 03          # copies the repo to .105 and builds
./manual/remote-run.sh 03 --no-sync   # re-run without copying
./manual/remote-run.sh all         # every step, in order""")
    p(doc, "The number is the NN in step-NN-*.sh. Every command copies the "
           "repository to the control plane and runs that ONE step there, as "
           "the rhai user, with rootless podman.")

    h2(doc, "The two sites")
    table(doc,
          ["", "PROD", "DR"],
          [["Host", "192.168.147.105", "192.168.147.104"],
           ["Deploy user", "rhai  (uid 1001)", "dr  (uid 1001)"],
           ["MCP endpoint", "http://192.168.147.105:8095/mcp",
            "http://192.168.147.104:8095/mcp"],
           ["Hostname it reports", "server-gateway.example.com",
            "localhost.localdomain"],
           ["Privilege", "rootless podman, no sudo", "rootless podman, no sudo"]],
          widths=[1.5, 2.6, 2.6])

    # ------------------------------------------------------------- steps ----
    doc.add_page_break()
    h1(doc, "The steps, and the command in each one")

    step(doc, "00", "manual/step-00-preflight.sh",
         "Check the tools, the SSH key, both sites, the port and the Aqua "
         "credential. Changes nothing — it only reports.",
         """# the tools
for c in podman curl python3 gzip sha256sum tar ssh; do command -v $c; done

# both sites, over the pipeline key
cd ansible && ansible -i inventory.ini mcp_sites -m ping

# the MCP port on both sites
curl -s -o /dev/null --connect-timeout 5 http://192.168.147.105:8095/mcp""")

    step(doc, "01", "manual/step-01-fetch-source.sh",
         "Pull Red Hat's lightspeed linux-mcp-server at a pinned commit. "
         "Nothing is vendored in the repo, so there is no second copy to keep "
         "in sync.",
         """curl -fsSL --retry 3 --retry-delay 5 -o mcp-src.tar.gz \\
  https://github.com/rhel-lightspeed/linux-mcp-server/archive/6d7ca1d1da8598c2e816fd69e98b8f7cf97da0d1.tar.gz

tar -xzf mcp-src.tar.gz -C upstream --strip-components=1""")

    step(doc, "02", "manual/step-02-resolve-version.sh",
         "Build the image tag v1.0.<DDMMYY><NN> and remember it for the later "
         "steps. Re-running gives a NEW tag instead of overwriting the old one.",
         """BASE=$(tr -d ' \\n' < VERSION)           # 1.0
DAY=$(TZ=Asia/Hong_Kong date +%d%m%y)   # 041126
SEQ=$(printf '%02d' $(( ${PREV:-0} + 1 ))) # 12

IMAGE_VERSION="v${BASE}.${DAY}${SEQ}"     # v1.0.04112612""")

    step(doc, "03", "manual/step-03-build-image.sh",
         "Build the upstream Containerfile, exactly as Red Hat shipped it. Two "
         "flags are load-bearing: --network host (a bridged build hangs on the "
         "pip install) and --format docker (podman's OCI format drops the "
         "HEALTHCHECK).",
         """podman build \\
    --file upstream/Containerfile \\
    --format docker \\
    --network host \\
    --tag rhel-mcp:v1.0.04112612 \\
    upstream""")

    step(doc, "04", "manual/step-04-scan-aqua.sh",
         "The Aqua console decides whether the image may ship. The step only "
         "continues if the report says so.",
         f"""podman run --rm --network host --security-opt label=disable --user root \\
    -v {SOCK}:/var/run/docker.sock \\
    {AQUA} \\
    scan --host https://192.168.147.105 \\
         --local localhost/rhel-mcp:v1.0.04112612 \\
         --no-verify --user "$AQUA_USER" --password "$AQUA_PASSWORD" --html \\
    > manual-reports/aqua-report.html

grep -q "Image Is Compliant" manual-reports/aqua-report.html""")

    step(doc, "05", "manual/step-05-scan-trivy.sh",
         "Find the CVEs. The library scan is the INPUT to step 06, not a gate "
         "— findings are a work list, not a verdict. The OS scan gates "
         "CRITICAL here.",
         f"""podman run --rm --network host --security-opt label=disable \\
    -v {SOCK}:/var/run/docker.sock \\
    -v trivy-cache:/root/.cache/trivy \\
    {TRIVY} \\
    image --scanners vuln --pkg-types library --severity HIGH,CRITICAL \\
          --exit-code 1 --format json localhost/rhel-mcp:v1.0.04112612 \\
    > manual-reports/trivy-report.json""")

    step(doc, "06", "manual/step-06-remediate.sh",
         "Upgrade the vulnerable packages inside the image and drop pip (which "
         "carries its own vulnerable vendored copies). The result is a DERIVED "
         "image, so every upstream layer, label, user and entrypoint survives.",
         """# the fix list comes out of the Trivy JSON
python3 scripts/trivy_cve_packages.py manual-reports/trivy-report.json \\
        --installed manual-reports/pip-list.txt > manual-reports/cve-fixes.txt

podman build --network host --pull=never --format docker \\
    --file Containerfile.remediated \\
    --tag rhel-mcp-remediated:v1.0.04112612 .""",
         caption="the derived Containerfile it writes")
    code(doc, """FROM localhost/rhel-mcp:v1.0.04112612
USER root
RUN set -eux; /opt/venvs/mcp/bin/python -m pip install --no-cache-dir --no-deps --upgrade \\
      authlib==1.9.1 certifi==2026.10.18 dnspython==2.9.0 joserfc==1.7.5 pyjwt==2.14.0 ; \\
    rm -rf /opt/venvs/mcp/lib/python3.12/site-packages/pip \\
           /opt/venvs/mcp/lib/python3.12/site-packages/pip-*.dist-info \\
           /opt/venvs/mcp/bin/pip*
USER mcp""")

    step(doc, "07", "manual/step-07-scan-trivy-final.sh",
         "The hard gate, run on the image that will actually ship: no "
         "HIGH/CRITICAL library CVE, no CRITICAL OS CVE.",
         f"""podman run --rm --network host --security-opt label=disable \\
    -v {SOCK}:/var/run/docker.sock \\
    -v trivy-cache:/root/.cache/trivy \\
    {TRIVY} \\
    image --scanners vuln --pkg-types library --severity HIGH,CRITICAL \\
          --exit-code 1 localhost/{IMG}""")

    step(doc, "08", "manual/step-08-export-artifact.sh",
         "Pack the image as ONE tarball. It travels as a file, not through a "
         "registry — the DR site must be able to receive a promoted image "
         "even when the PROD registry is down.",
         f"""podman save {IMG} | gzip > rhel-mcp-v1.0.04112612.tar.gz
sha256sum rhel-mcp-v1.0.04112612.tar.gz | tee rhel-mcp-v1.0.04112612.tar.gz.sha256""")

    step(doc, "09", "manual/step-09-deploy.sh",
         "Ansible copies the SAME tarball to .105 and .104. Each site loads it "
         "into its own rootless podman store and runs it as a systemd USER "
         "unit — no root, no sudo, no shared filesystem.",
         """cd ansible
export ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_rhai108_rsa

ansible-playbook -i inventory.ini site.yml \\
    -e mcp_image=rhel-mcp-remediated:v1.0.04112612 \\
    -e mcp_artifact=/home/rhai/mcp-dr-pipeline/rhel-mcp-v1.0.04112612.tar.gz""")

    step(doc, "10", "manual/step-10-verify-prod.sh",
         "Ask PROD who it is, and prove it is real. Two facts in one session: "
         "the hostname, and that port 8095 on that host is actually held by the "
         "MCP process — so the hostname cannot have been a canned string.",
         f"""podman run -i --rm --pull=never --network host --security-opt label=disable \\
    --entrypoint /opt/venvs/mcp/bin/python {IMG} \\
    - --url http://192.168.147.105:8095/mcp --target 192.168.147.105 \\
      --expect server-gateway.example.com \\
      --call get_listening_ports --assert get_listening_ports=8095 \\
    < scripts/mcp_verify.py""")

    step(doc, "11", "manual/step-11-failover.sh",
         "The drill, in four moves: warm the standby, PROVE it can take the "
         "load, cut over, then prove the DR site answers. A standby that "
         "cannot hold the load is never promoted — the step aborts and PROD "
         "keeps serving.",
         """# 1. warm the standby — PROD keeps serving throughout
ansible-playbook -i inventory.ini dr-warmup.yml

# 2. the readiness gate — the DR site is asked what it can see of itself
podman run -i --rm ... mcp_dr_probe.py \\
    --url http://192.168.147.104:8095/mcp --target 192.168.147.104 \\
    --expect localhost.localdomain \\
    --min-cpu-cores 2 --min-free-mem-percent 10 --min-free-disk-percent 10

# 3. the cutover — stop PROD, start DR
ansible-playbook -i inventory.ini failover.yml

# 4. prove the DR site answers
podman run -i --rm ... mcp_verify.py \\
    --url http://192.168.147.104:8095/mcp --expect localhost.localdomain \\
    --call get_listening_ports --assert get_listening_ports=8095""")

    step(doc, "12", "manual/step-12-failback.sh",
         "The exact inverse: stand DR down, bring PROD back. Same artifact, "
         "same socket, the original site.",
         """ansible-playbook -i inventory.ini failback.yml""")

    step(doc, "13", "manual/step-13-show-same-artifact.sh",
         "The evidence: two different machines running the same bytes. The "
         "image ID and every layer digest must match.",
         """ssh -i ~/.ssh/id_rhai108_rsa rhai@192.168.147.105 \\
  "podman image inspect rhel-mcp-remediated:v1.0.04112612 --format 'Id={{.Id}} Layers={{.RootFS.Layers}}'"

ssh -i ~/.ssh/id_rhai108_rsa dr@192.168.147.104 \\
  "podman image inspect rhel-mcp-remediated:v1.0.04112612 --format 'Id={{.Id}} Layers={{.RootFS.Layers}}'""")

    # ------------------------------------------------- when to use which ---
    doc.add_page_break()
    h1(doc, "When do I use which step?")
    p(doc, "You will not run all fourteen every time. Each step exists for a "
           "scene — a point in the demo where you need to show something, or a "
           "job you have to be able to repeat. This is the map from scene to "
           "step.")

    table(doc,
          ["Step", "The scene that calls for it", "What it puts on screen"],
          [["00",
            "first thing on a new day, or after anything changed on the hosts "
            "— a reboot, a new key, a firewall edit",
            "the tools, the key and BOTH sites are reachable. Changes nothing"],
           ["01",
            "you want the upstream MCP source, or you are starting from a "
            "clean tree",
            "Red Hat's repo, pinned to one commit — so the build is "
            "reproducible, not 'whatever is on master today'"],
           ["02",
            "any run that produces a shippable image",
            "the tag: v1.0.<DDMMYY><NN>. Never overwritten, so an old "
            "artifact stays reproducible"],
           ["03",
            "after 01/02, or after any Containerfile change",
            "ONE image, built from Red Hat's own Containerfile, unmodified"],
           ["04",
            "every image that may ship",
            "the Aqua console's verdict — the compliance gate that says "
            "this image may go out"],
           ["05",
            "right after the build, BEFORE you fix anything",
            "the work list: which packages carry the CVEs. An INPUT, not a "
            "verdict — nothing has failed yet"],
           ["06",
            "once you have the work list from 05",
            "the derived image: CVEs upgraded, pip's own vulnerable copies "
            "deleted, every upstream layer still intact"],
           ["07",
            "after 06, on the image that will actually ship",
            "the hard gate: 0 HIGH/CRITICAL library CVEs, 0 CRITICAL OS CVEs"],
           ["08",
            "after 07 passes, before the deploy",
            "ONE tarball plus its sha256 — the artifact that travels to both "
            "sites"],
           ["09",
            "when the artifact changed",
            "the same tarball loaded on .105 and .104, each as a systemd user "
            "unit. No root, no sudo, no shared filesystem"],
           ["10",
            "right after a deploy",
            "the PROD MCP answers AND port 8095 is really held by the MCP "
            "process — so the hostname cannot be a canned string"],
           ["11",
            "the DR drill — the whole point of the demo",
            "the standby was PROVEN fit, then the answer moved to .104"],
           ["12",
            "right after 11, to restore the normal posture",
            "the original site is back: PROD live, DR stopped"],
           ["13",
            "at the end, as the evidence",
            "the image ID and every layer digest are byte-identical on the "
            "two hosts"]],
          widths=[0.45, 2.85, 3.35])

    h2(doc, "Can I skip a step?")
    p(doc, "Yes for most of them — but three are hard gates, and two are "
           "dependencies that fail loudly rather than silently.")
    table(doc,
          ["Step", "Skip it?", "What happens if you do"],
          [["00",
            "yes, once you have done it today",
            "you find out about a missing key or a closed port halfway "
            "through the build"],
           ["01",
            "yes — if upstream/ is already unpacked",
            "nothing. The source is pinned to one commit, so a rebuild is the "
            "same source either way"],
           ["02",
            "no — unless you deliberately reuse the tag",
            "every later step reads the tag from the state file. Skipping it "
            "leaves the OLD tag in place"],
           ["03",
            "yes, if the image is already built",
            "you reuse the image already in the local podman store"],
           ["04",
            "NO — not for a shipping image",
            "it is a hard gate. The step greps for \"Image Is Compliant\" and "
            "FAILS if the console says otherwise"],
           ["05",
            "yes — but only if you already have the fix list",
            "step 06 reads manual-reports/trivy-report.json. Without 05 there "
            "is no work list to apply"],
           ["06",
            "no, if the CVEs are not fixed",
            "the remediated image is what 07 gates and what 09 ships"],
           ["07",
            "NO — not for a shipping image",
            "the hard gate. A HIGH/CRITICAL library CVE fails the step"],
           ["08",
            "yes, if the tarball is already on disk",
            "step 09 needs the file and its sha256 next to it"],
           ["09",
            "YES — for the drill only",
            "the drill playbooks only START and STOP the unit; they never "
            "reference the image. If both hosts already run it, go straight "
            "to 11"],
           ["10",
            "yes, if you are only doing the drill",
            "you lose the 'PROD was healthy before we cut over' proof — "
            "step 11 re-proves it anyway"],
           ["11",
            "only if you are not doing the drill",
            "this IS the failover. Skip it and there is no demo"],
           ["12",
            "yes — if you want to LEAVE DR live",
            "otherwise you finish with PROD live and DR stopped, which is the "
            "intended posture anyway"],
           ["13",
            "yes — it is evidence, not a gate",
            "but it is the answer to \"is it really the same artifact?\", "
            "which is the question the demo invites"]],
          widths=[0.45, 2.05, 4.15])

    h2(doc, "The three runs you will actually do")
    table(doc,
          ["Run", "Steps", "When"],
          [["The full pipeline",
            "00 → 13, in order",
            "a fresh build: new source, new image, new deploy, then the "
            "drill. This is what the Jenkins job does"],
           ["Just the DR drill",
            "00, 11, 12, 13",
            "the image is already deployed on both hosts and you want to show "
            "the failover. No build, no scan, no deploy"],
           ["Rebuild and redeploy",
            "01 → 10",
            "you changed something upstream and want the new artifact live on "
            "both sites. Stop before 11 if you are not drilling today"]],
          widths=[1.5, 1.35, 3.8])

    # ------------------------------------------------------ just the drill --
    h1(doc, "Just the drill, on the live .105 / .104 pair")
    p(doc, "This is the short version — no rebuild, no scan, no deploy. The "
           "image is already loaded on both hosts and both hosts already run "
           "the systemd unit.")
    code(doc, """# from the laptop, in the repository
./manual/remote-run.sh 00            # preflight — changes nothing
./manual/remote-run.sh 11            # warm DR, gate it, cut over, verify
./manual/remote-run.sh 12            # fail back to PROD
./manual/remote-run.sh 13            # the same artifact on both sites""")
    p(doc, "Steps 11, 12 and 13 read the image tag from the state file on the "
           "control plane. It has to name the image that is actually loaded "
           "on both hosts — check it first:")
    code(doc, """ssh rhai@192.168.147.105 'cat ~/mcp-dr-pipeline/.manual-state.env'
ssh rhai@192.168.147.105 'podman images --format \"{{.Repository}}:{{.Tag}}\"'""")
    p(doc, "If FULL_IMAGE does not match what is on the hosts, point it at the "
           "deployed tag. This is the whole state file, hand-edited:")
    code(doc, """ssh rhai@192.168.147.105 \\
  'sed -i "s|^FULL_IMAGE=.*|FULL_IMAGE=rhel-mcp-remediated:v1.0.04112612|" \\
     ~/mcp-dr-pipeline/.manual-state.env'""")
    callout(doc, "WHY THE TAG MATTERS",
            "the drill does not care which image it is — it starts and stops "
            "the unit. But step 13 DOES: it compares the image ID and the "
            "layers of the tag in the state file against what each host has "
            "loaded. If the state file names an image neither host has, step "
            "13 fails on the inspect, not on the comparison.",
            "warn")

    h2(doc, "What you should see")
    table(doc,
          ["After", "The line to look for", "If you do not get it"],
          [["00",
            "both sites ping OK, and the port answers on .105",
            "a missing key or a closed port — fix it before anything else"],
           ["11",
            "DR READINESS PROBE → READY, then FAILOVER: DR is now serving → "
            "localhost.localdomain",
            "the drill aborts and PROD keeps serving. That is the gate "
            "working, not a bug — read the probe's numbers"],
           ["11",
            "http://192.168.147.105:8095/mcp → connection refused",
            "PROD is still up — the cutover did not happen, so the probe "
            "must have blocked it"],
           ["12",
            "PASS: http://192.168.147.105:8095/mcp is serving "
            "server-gateway.example.com",
            "the failback playbook did not finish — check the unit on .105"],
           ["13",
            "PASS: both sites run the SAME image (7f7c651aa225)",
            "the two hosts are not running the same bytes — that is a real "
            "problem, not a formatting one"]],
          widths=[0.55, 3.05, 3.05])

    # ------------------------------------------------------ command sheet ---
    doc.add_page_break()
    h1(doc, "Command sheet — what to type")
    p(doc, "The same fourteen steps, as one clean list, in the order they run. "
           "This is the page to present from.")

    code(doc, """# ---- from the laptop -------------------------------------------------------
cd products/mcp-dr-pipeline

./manual/remote-run.sh 00            # preflight
./manual/remote-run.sh 01            # fetch the upstream MCP source
./manual/remote-run.sh 02            # resolve the version
./manual/remote-run.sh 03            # build the image
./manual/remote-run.sh 04            # the Aqua gate
./manual/remote-run.sh 05            # the baseline Trivy scan
./manual/remote-run.sh 06            # security remediation
./manual/remote-run.sh 07            # the final Trivy gate
./manual/remote-run.sh 08            # export the artifact
./manual/remote-run.sh 09            # deploy to both sites
./manual/remote-run.sh 10            # verify PROD
./manual/remote-run.sh 11            # the failover drill
./manual/remote-run.sh 12            # failback
./manual/remote-run.sh 13            # prove the same artifact on both sites""")

    h2(doc, "The drill at a glance")
    code(doc, """  move   PROD .105                        DR .104
  ----   -----------------------------    -------------------------------
   1     * live, :8095 answering           o stopped

   2     * still serving -- warm it up -->  start the unit, wait for :8095

   3     * still serving -- readiness -->  4 tools, gate on the numbers
          (the gate runs WHILE             XX not ready -> abort,
           PROD is serving)                 PROD keeps serving, step FAILS

   4     * still serving -- THE CUTOVER->  start the unit
          stop the PROD unit                :8095 now answers on .104

   5     o stopped      -- VERIFY ----->   localhost.localdomain
          :8095 refused                     8095 held by linux-mcp-server""")

    h2(doc, "The four moments worth stopping at")
    table(doc,
          ["When", "Say this", "Show this"],
          [["After step 03",
            "one image, built from Red Hat's own Containerfile, unmodified",
            "podman image inspect rhel-mcp:v1.0.04112612"],
           ["After step 04",
            "the Aqua console approved it — this is the gate that says the "
            "image may ship",
            "grep -o 'Image Is (Compliant|Non-compliant)' manual-reports/aqua-report.html"],
           ["After step 07",
            "19 HIGH/CRITICAL findings down to 0, on the image that will "
            "actually ship",
            "cat manual-reports/trivy-final-report.txt"],
           ["After step 11",
            "the DR standby was PROVEN fit before it was allowed to take over "
            "— and the answer changed",
            "cat manual-reports/failover-transcript.txt"]],
          widths=[1.15, 2.75, 2.75])

    h2(doc, "The one command that shows the whole idea")
    p(doc, "Same image, two machines, two different answers. Run this after "
           "step 12:")
    code(doc, """curl -s http://192.168.147.105:8095/mcp -X POST \\
  -H 'Content-Type: application/json' \\
  -H 'Accept: application/json, text/event-stream' \\
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2024-11-05","capabilities":{},
        "clientInfo":{"name":"demo","version":"1"}}}'
# -> the PROD site answers. Stop it, and the DR site answers instead.""")

    callout(doc, "THE PUNCHLINE",
            "the SAME artifact, deployed to two different machines, gives a "
            "different answer depending on which one is live — because the "
            "MCP inspects the host it is deployed on, over SSH.",
            "info")

    callout(doc, "ONE HONEST CAVEAT",
            "the SERVICE moves for real — the unit is stopped on one host and "
            "started on the other. The client's ADDRESS is changed by the "
            "caller: an address that survives a cutover needs a floating IP, "
            "and moving one needs root on the target, which this demo "
            "deliberately never gives. Production DR uses VRRP/keepalived or "
            "pacemaker instead.",
            "warn")

    doc.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
