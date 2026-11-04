"""Build PROD-DR-MCP-Pipeline-Guide.docx.

The PROD/DR MCP pipeline walkthrough: every manual step, how it works, what
it must print, and what the MCP contributes to each one.

    python docs/build_guide.py

Writes PROD-DR-MCP-Pipeline-Guide.docx next to this script. Re-runnable: it
always overwrites the output.
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

HERE = Path(__file__).resolve().parent
OUT = HERE / "PROD-DR-MCP-Pipeline-Guide.docx"

BLUE = RGBColor(0x0B, 0x3D, 0x91)
INK = RGBColor(0x1A, 0x1A, 0x1A)
GREY = RGBColor(0x55, 0x55, 0x55)
GREEN = RGBColor(0x1B, 0x6B, 0x3A)
AMBER = RGBColor(0x8A, 0x4A, 0x00)
RED = RGBColor(0xB3, 0x00, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# code background
CODE_BG = "F2F3F5"
# callout backgrounds, keyed by kind
CALLOUT = {
    "info": ("EAF1F8", BLUE),
    "pass": ("E9F5EE", GREEN),
    "warn": ("FDF4E6", AMBER),
    "fail": ("FBECEC", RED),
    "note": ("F0F0F0", GREY),
}


# --------------------------------------------------------------- primitives --
def _shade(paragraph, fill: str) -> None:
    pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pr.append(shd)


def _shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _border(paragraph, color: str, size: int = 6) -> None:
    pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "4")
        el.set(qn("w:color"), color)
        borders.append(el)
    pr.append(borders)


def _no_space(paragraph) -> None:
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0


# ------------------------------------------------------------------ blocks --
def h1(doc, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(20)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.size = Pt(17)
    run.font.bold = True
    run.font.color.rgb = BLUE
    _border(p, "0B3D91", 4)


def h2(doc, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(13)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.size = Pt(13)
    run.font.bold = True
    run.font.color.rgb = BLUE


def h3(doc, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.color.rgb = INK


def p(doc, text: str, size: int = 10.5, color: RGBColor = INK,
      italic: bool = False, bold: bool = False, space_after: int = 6) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_after = Pt(space_after)
    run = para.add_run(text)
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.italic = italic
    run.font.bold = bold


def rich(doc, parts, size: int = 10.5, space_after: int = 6) -> None:
    """parts = [(text, {'bold':.., 'mono':.., 'color':..}), ...]"""
    para = doc.add_paragraph()
    para.paragraph_format.space_after = Pt(space_after)
    for text, opts in parts:
        run = para.add_run(text)
        run.font.size = Pt(opts.get("size", size))
        run.font.bold = opts.get("bold", False)
        run.font.italic = opts.get("italic", False)
        if opts.get("mono"):
            run.font.name = "Consolas"
            run.font.size = Pt(opts.get("size", size) - 0.5)
        run.font.color.rgb = opts.get("color", INK)


def bullet(doc, text: str, level: int = 0) -> None:
    para = doc.add_paragraph(style="List Bullet")
    para.paragraph_format.left_indent = Inches(0.25 + 0.25 * level)
    para.paragraph_format.space_after = Pt(2)
    run = para.add_run(text)
    run.font.size = Pt(10.5)
    run.font.color.rgb = INK


def code(doc, text: str, caption: str | None = None) -> None:
    if caption:
        cap = doc.add_paragraph()
        cap.paragraph_format.space_before = Pt(6)
        cap.paragraph_format.space_after = Pt(1)
        run = cap.add_run(caption)
        run.font.size = Pt(9)
        run.font.bold = True
        run.font.color.rgb = GREY

    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(2)
    para.paragraph_format.space_after = Pt(8)
    para.paragraph_format.left_indent = Inches(0.12)
    para.paragraph_format.line_spacing = 1.0
    _shade(para, CODE_BG)
    _border(para, "D8D8D8", 4)

    lines = text.strip("\n").split("\n")
    for i, line in enumerate(lines):
        run = para.add_run(line)
        run.font.name = "Consolas"
        run.font.size = Pt(8.5)
        run.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
        if i < len(lines) - 1:
            run.add_break()
    _no_space(para)


def callout(doc, label: str, text: str, kind: str = "info") -> None:
    bg, fg = CALLOUT[kind]
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(6)
    para.paragraph_format.space_after = Pt(8)
    para.paragraph_format.left_indent = Inches(0.10)
    _shade(para, bg)
    _border(para, "%02X%02X%02X" % (fg[0], fg[1], fg[2]), 4)
    lab = para.add_run(f"{label}  ")
    lab.font.size = Pt(9.5)
    lab.font.bold = True
    lab.font.color.rgb = fg
    body = para.add_run(text)
    body.font.size = Pt(10)
    body.font.color.rgb = INK
    _no_space(para)


def table(doc, headers: list[str], rows: list[list[str]],
          widths: list[float] | None = None, mono_cols: list[int] | None = None) -> None:
    tbl = doc.add_table(rows=1, cols=len(headers))
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    mono_cols = mono_cols or []

    hdr = tbl.rows[0].cells
    for i, head in enumerate(headers):
        hdr[i].text = ""
        para = hdr[i].paragraphs[0]
        para.paragraph_format.space_after = Pt(2)
        para.paragraph_format.space_before = Pt(2)
        run = para.add_run(head)
        run.font.size = Pt(9.5)
        run.font.bold = True
        run.font.color.rgb = WHITE
        _shade_cell(hdr[i], "0B3D91")

    for row in rows:
        cells = tbl.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = ""
            para = cells[i].paragraphs[0]
            para.paragraph_format.space_after = Pt(2)
            para.paragraph_format.space_before = Pt(2)
            for j, line in enumerate(value.split("\n")):
                run = para.add_run(line)
                run.font.size = Pt(8.5 if i in mono_cols else 9.5)
                if i in mono_cols:
                    run.font.name = "Consolas"
                if j < len(value.split("\n")) - 1:
                    run.add_break()

    if widths:
        for row in tbl.rows:
            for i, width in enumerate(widths):
                row.cells[i].width = Inches(width)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def step_header(doc, number: str, title: str, script: str, gate: str) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(16)
    para.paragraph_format.space_after = Pt(4)
    para.paragraph_format.keep_with_next = True
    run = para.add_run(f"Step {number} — {title}")
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = BLUE
    _border(para, "0B3D91", 4)

    meta = doc.add_paragraph()
    meta.paragraph_format.space_after = Pt(6)
    meta.paragraph_format.keep_with_next = True
    for text, opts in (
        (f"script  ", {"bold": True, "size": 9}),
        (script, {"mono": True, "size": 9}),
        ("\ngate    ", {"bold": True, "size": 9}),
        (gate, {"size": 9, "color": GREEN if gate != "—" else GREY}),
    ):
        run = meta.add_run(text)
        run.font.size = Pt(opts.get("size", 9))
        run.font.bold = opts.get("bold", False)
        run.font.color.rgb = opts.get("color", INK)
        if opts.get("mono"):
            run.font.name = "Consolas"


def _page_field(paragraph, field: str) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = field
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def _header_footer(doc) -> None:
    section = doc.sections[0]
    section.top_margin = Cm(1.9)
    section.bottom_margin = Cm(1.9)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)

    head = section.header.paragraphs[0]
    head.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = head.add_run("PROD/DR MCP pipeline — the manual run")
    run.font.size = Pt(8.5)
    run.font.color.rgb = GREY

    foot = section.footer.paragraphs[0]
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = foot.add_run("products/mcp-dr-pipeline   ·   page ")
    run.font.size = Pt(8.5)
    run.font.color.rgb = GREY
    _page_field(foot, " PAGE ")
    run = foot.add_run(" of ")
    run.font.size = Pt(8.5)
    run.font.color.rgb = GREY
    _page_field(foot, " NUMPAGES ")
    for r in foot.runs:
        r.font.size = Pt(8.5)
        r.font.color.rgb = GREY


# ------------------------------------------------------------------- build --
def build() -> None:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = INK
    normal.paragraph_format.space_after = Pt(6)
    _header_footer(doc)

    # ------------------------------------------------------------- title ---
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(2)
    run = title.add_run("PROD/DR MCP Pipeline")
    run.font.size = Pt(26)
    run.font.bold = True
    run.font.color.rgb = BLUE

    sub = doc.add_paragraph()
    sub.paragraph_format.space_after = Pt(2)
    run = sub.add_run("Driving the failover drill by hand, one command at a time")
    run.font.size = Pt(13)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    meta = doc.add_paragraph()
    meta.paragraph_format.space_after = Pt(14)
    run = meta.add_run(
        "Repository  github.com/MangoTim/pipeline-dr   ·   "
        "sites  192.168.147.105 (PROD) and 192.168.147.104 (DR)   ·   "
        "artifact  Red Hat linux-mcp-server, unmodified")
    run.font.size = Pt(9.5)
    run.font.color.rgb = GREY
    _border(meta, "D8D8D8", 4)

    # ------------------------------------------------------------ what ---
    h1(doc, "1.  What this guide is")

    p(doc, "One pipeline builds and scans one image, Ansible deploys that "
           "exact artifact to a PROD site and a DR site, and the MCP answers "
           "from whichever site is live. This guide walks through the manual "
           "version of that pipeline: the same stages as the Jenkins job, "
           "unbundled into one script per stage so you can stop between any "
           "two of them and explain what just happened.")

    p(doc, "It also answers a question the pipeline itself cannot answer: "
           "what are the MCP's tools actually for? Only some of them carry "
           "weight here, and this guide is explicit about which ones and why. "
           "The short answer is in section 6 — the MCP is not decoration in "
           "the middle of the pipeline. It is the component that decides "
           "whether the failover is allowed to happen.")

    callout(doc, "THE PUNCHLINE",
            "the SAME artifact, deployed to two different machines, gives a "
            "different answer depending on which one is live — because the "
            "MCP inspects the host it is deployed on, over SSH.",
            "info")

    # --------------------------------------------------------- the sites ---
    h1(doc, "2.  The two sites")

    table(doc,
          ["", "PROD", "DR"],
          [["Host", "192.168.147.105", "192.168.147.104"],
           ["Role", "production + the control plane\n(Jenkins, the scanners, the manual steps)",
            "the standby"],
           ["Deploy user", "rhai  (uid 1001)", "dr  (uid 1001)"],
           ["MCP endpoint", "http://192.168.147.105:8095/mcp",
            "http://192.168.147.104:8095/mcp"],
           ["Hostname the MCP reports", "server-gateway.example.com",
            "localhost.localdomain"],
           ["Privilege model", "rootless podman, no sudo, no become",
            "rootless podman, no sudo, no become"]],
          widths=[1.6, 2.5, 2.5])

    p(doc, "Neither user is in the wheel group and no sudo password is used "
           "anywhere. Ansible drives each site as its own non-root account, "
           "and the MCP container runs as the matching uid so that it can read "
           "the mounted SSH key (mode 0600).", space_after=10)

    # ----------------------------------------------------- before you start --
    h1(doc, "3.  Before you start")

    h3(doc, "The Aqua credential — the one thing you must set up")
    p(doc, "Step 04 is a hard gate on the Aqua console's verdict, and the "
           "console's password is deliberately not in the repository. Put it "
           "in the deploy user's home directory, on the host, once:", space_after=4)
    code(doc, """ssh rhai@192.168.147.105
mkdir -p ~/.mcp-demo && umask 077
cat > ~/.mcp-demo/aqua.env <<'EOF'
AQUA_USER=administrator
AQUA_PASSWORD=<the aqua console password>
EOF""")

    h3(doc, "Everything else is already in place")
    p(doc, "The one-time host setup — port 8095 open on both sites, "
           "python3.9 installed, linger enabled for both users, the pipeline "
           "SSH key authorised on the DR site — is documented in "
           "RUNBOOK.md. It is the same setup for the Jenkins run and for the "
           "manual run; the manual path simply does not need the Jenkins "
           "container.", space_after=10)

    # --------------------------------------------------------- driving it ---
    h1(doc, "4.  Driving it")

    p(doc, "From the laptop, in the repository:", space_after=4)
    code(doc, """cd products/mcp-dr-pipeline

./manual/remote-run.sh list        # what the steps are
./manual/remote-run.sh 00          # preflight — checks, changes nothing
./manual/remote-run.sh 03          # copies the repo to .105 and builds
./manual/remote-run.sh 03 --no-sync    # re-run without copying
./manual/remote-run.sh all         # every step, in order""")

    p(doc, "The number is the NN in step-NN-*.sh. Each command copies the "
           "repository to the control plane and runs that ONE step there, as "
           "the rhai user, with rootless podman. If you prefer to work "
           "directly on the host:", space_after=4)
    code(doc, """ssh rhai@192.168.147.105
cd ~/mcp-dr-pipeline
./manual/step-03-build-image.sh""")

    callout(doc, "NOTE",
            "the steps run on the PROD host, NOT inside the Jenkins "
            "container. That is deliberate: the manual path is the pipeline "
            "unbundled, running on the machine it deploys to, so you can see "
            "every command as it executes.",
            "note")

    # ------------------------------------------------------- the step index --
    h1(doc, "5.  The steps at a glance")

    table(doc,
          ["Step", "Script", "What it does", "Gate"],
          [["00", "step-00-preflight.sh",
            "check the tools, both sites, the key, the port, the credential",
            "— (reports only)"],
           ["01", "step-01-fetch-source.sh",
            "download the upstream MCP source at the pinned commit", "—"],
           ["02", "step-02-resolve-version.sh",
            "build the image tag for this run", "—"],
           ["03", "step-03-build-image.sh",
            "build the upstream Containerfile, unmodified", "—"],
           ["04", "step-04-scan-aqua.sh",
            "scan with the Aqua console", "Image Is Compliant"],
           ["05", "step-05-scan-trivy.sh",
            "baseline Trivy scan: libraries (JSON) + OS packages",
            "no CRITICAL OS CVE"],
           ["06", "step-06-remediate.sh",
            "upgrade the vulnerable Python packages, drop pip from the venv",
            "fails if a CVE has no fix"],
           ["07", "step-07-scan-trivy-final.sh",
            "re-scan the image that will actually ship",
            "no HIGH/CRITICAL library CVE"],
           ["08", "step-08-export-artifact.sh",
            "podman save | gzip, plus the sha256", "—"],
           ["09", "step-09-deploy.sh",
            "Ansible: copy the one tarball to both sites, start both",
            "both units active"],
           ["10", "step-10-verify-prod.sh",
            "the MCP answers as PROD, and 8095 is held by the MCP process",
            "hostname + listening port"],
           ["11", "step-11-failover.sh",
            "warm the standby, PROVE it can take the load, then cut over",
            "the readiness probe"],
           ["12", "step-12-failback.sh",
            "stand DR down, bring PROD back", "PROD answers again"],
           ["13", "step-13-show-same-artifact.sh",
            "prove both sites run the same bytes", "image ID + layers"]],
          widths=[0.4, 1.85, 2.9, 1.45])

    p(doc, "Steps 00 to 13 map one-to-one onto the Jenkins stages. The "
           "manual path adds the same gates in the same order — the only "
           "difference is that you can see each one run.", space_after=10)

    # ------------------------------------------------------- the detail ---
    h1(doc, "6.  Every step, in detail")

    # --- 00
    step_header(doc, "00", "preflight", "manual/step-00-preflight.sh", "—")
    h3(doc, "What it does")
    p(doc, "Checks everything the later steps depend on, before anything is "
           "built. It changes nothing.")
    bullet(doc, "the tools: podman, curl, python3, gzip, sha256sum, tar, ssh, ansible-playbook")
    bullet(doc, "the checkout is complete (Jenkinsfile, the scripts, the inventory)")
    bullet(doc, "the pipeline SSH key is readable")
    bullet(doc, "both sites answer over the pipeline key (ansible -m ping)")
    bullet(doc, "port 8095 on both sites")
    bullet(doc, "the Aqua credential file exists (it is never printed)")
    bullet(doc, "the podman API socket the scanners need")
    h3(doc, "Expected output")
    code(doc, """OK   podman -> /usr/bin/podman
OK   ansible-playbook -> /home/rhai/.local/bin/ansible-playbook
OK   the checkout looks complete
OK   /home/rhai/.ssh/id_rhai108_rsa
192.168.147.105 | SUCCESS => {"changed": false, "ping": "pong"}
192.168.147.104 | SUCCESS => {"changed": false, "ping": "pong"}
OK   192.168.147.105:8095 answers
OK   /home/rhai/.mcp-demo/aqua.env (not printed)
OK   /run/user/1001/podman/podman.sock

<<< [step 00] OK""")
    callout(doc, "GOTCHA",
            "rootless podman does not expose an engine socket by default, and "
            "the Aqua and Trivy scanners need one to reach the local image. "
            "Step 00 starts it on demand: podman system service --time=0 "
            "unix:///run/user/$(id -u)/podman/podman.sock — the unix:// prefix "
            "is required, and the directory has to exist first.",
            "warn")

    # --- 01
    step_header(doc, "01", "fetch the upstream source",
                "manual/step-01-fetch-source.sh", "—")
    h3(doc, "What it does")
    p(doc, "Downloads Red Hat's linux-mcp-server from GitHub and unpacks it "
           "into upstream/. The commit is pinned, so the build is "
           "reproducible. Nothing is vendored in this repository — there is "
           "no second copy of Red Hat's code to keep in sync, and the "
           "upstream source is never modified.")
    code(doc, """url  : https://github.com/rhel-lightspeed/linux-mcp-server/archive/6d7ca1d1da8598c2e816fd69e98b8f7cf97da0d1.tar.gz
OK   the upstream source is ready:
AGENTS.md  Containerfile  docs  licenses  pyproject.toml  src  tests

<<< [step 01] OK""")

    # --- 02
    step_header(doc, "02", "resolve the version",
                "manual/step-02-resolve-version.sh", "—")
    h3(doc, "What it does")
    p(doc, "Builds the image tag from the VERSION file, the Hong Kong date "
           "and a run counter. In Jenkins the counter is BUILD_NUMBER; here it "
           "lives in the state file, so a manual run produces the same SHAPE "
           "of tag. The values are written to .manual-state.env, which every "
           "later step reads.")
    code(doc, """VERSION file     : 1.0
Hong Kong date   : 041126
run number       : 01

image version    : v1.0.04112601
pre-remediation  : rhel-mcp:v1.0.04112601
post-remediation : rhel-mcp-remediated:v1.0.04112601
artifact         : rhel-mcp-v1.0.04112601.tar.gz

<<< [step 02] OK""")
    callout(doc, "NOTE",
            "re-running step 02 gives a NEW tag (the counter increments) "
            "instead of overwriting the old one. Delete .manual-state.env to "
            "start from scratch.",
            "note")

    # --- 03
    step_header(doc, "03", "build the image", "manual/step-03-build-image.sh", "—")
    h3(doc, "What it does")
    p(doc, "Builds the upstream Containerfile exactly as Red Hat shipped it. "
           "Two flags matter and both are load-bearing:")
    bullet(doc, "--network host — this host's container egress is dropped in "
                "the firewalld FORWARD chain, so a bridged build hangs on the "
                "pip install. Host networking routes it through OUTPUT.")
    bullet(doc, "--format docker — podman's default OCI format silently "
                "drops the HEALTHCHECK instruction; the docker format keeps "
                "it and is what the scanners expect.")
    h3(doc, "Expected output")
    code(doc, """    id=ec616084ab360b11f21b9d90a4ed825cd39d795770c43e67eceebf7253a946aa size=325000000 created=...
<<< [step 03] OK""")
    callout(doc, "TAKES A WHILE",
            "the upstream image installs a Python virtualenv from PyPI. "
            "Expect a few minutes. The two scanners take about a minute each, "
            "so the whole manual run is roughly 15 minutes.",
            "warn")

    # --- 04
    step_header(doc, "04", "the Aqua gate", "manual/step-04-scan-aqua.sh",
                "Image Is Compliant")
    h3(doc, "What it does")
    p(doc, "The Aqua console on this host decides whether the image may ship. "
           "The step continues only if the report says so.")
    code(doc, """--- Aqua scan summary ---
Image Is Compliant

<<< [step 04] OK""")
    h3(doc, "How the scanner is invoked")
    code(doc, """podman run --rm --network host \\
    -v /run/user/1001/podman/podman.sock:/var/run/docker.sock \\
    registry.aquasec.com/scanner:2022.4.868 \\
    scan --host https://192.168.147.105 --local localhost/rhel-mcp:v1.0.04112601 \\
         --no-verify --user "$AQUA_USER" --password "$AQUA_PASSWORD" --html""")
    bullet(doc, "--local <image> is the syntax this scanner version accepts; "
                "the plugin generates a form it rejects.")
    bullet(doc, "--html sends the report to STDOUT, which is redirected to a "
                "file. Do NOT use --htmlfile <path> — that writes inside the "
                "scanner container and is lost when --rm deletes it.")
    bullet(doc, "--no-verify is there because the console certificate is "
                "self-signed.")
    callout(doc, "IF IT TIMES OUT",
            "'TLS handshake timeout' means the aqua-web console container on "
            "the host has lost its outbound path. Fix it with: podman network "
            "reload",
            "fail")

    # --- 05
    step_header(doc, "05", "the baseline Trivy scan",
                "manual/step-05-scan-trivy.sh", "no CRITICAL OS CVE")
    h3(doc, "What it does")
    p(doc, "Two scans. The library scan runs as JSON, because step 06 parses "
           "it — it is the INPUT to the remediation, not a gate. The OS scan "
           "gates CRITICAL right here.")
    h3(doc, "Expected output")
    code(doc, """Target: usr/local/lib/python3.11/site-packages/fastmcp (lang-pkgs)
    authlib                1.7.2            HIGH      -> 1.9.1
    pyjwt                  2.13.0           HIGH      -> 2.14.0
    certifi                2026.7.22        HIGH      -> 2026.10.18
    dnspython              2.8.0            HIGH      -> 2.9.0
    joserfc                1.7.4            HIGH      -> 1.7.5
    msgpack                1.1.1            CRITICAL  NO FIX PUBLISHED
    setuptools             65.5.0           HIGH      NO FIX PUBLISHED
    urllib3                2.2.2            HIGH      NO FIX PUBLISHED

trivy (library) exit code: 1
...
trivy (OS packages) exit code: 0

<<< [step 05] OK""")
    callout(doc, "WHY THE LIBRARY SCAN IS NOT A GATE HERE",
            "because these findings are not a verdict, they are a work list. "
            "Step 06 fixes them and step 07 re-scans the image that actually "
            "ships. Gating twice would fail the run for no reason.",
            "info")

    # --- 06
    step_header(doc, "06", "security remediation",
                "manual/step-06-remediate.sh", "fails if a CVE has no fix")
    h3(doc, "What it does")
    p(doc, "Turns the Trivy JSON into a concrete upgrade list and fixes the "
           "image. Two kinds of finding are handled differently:")
    bullet(doc, "the MCP's OWN dependencies — authlib, pyjwt, certifi, "
                "dnspython, joserfc. Upgraded in place to the version Trivy "
                "names as the fix.")
    bullet(doc, "the copies pip bundles in its own _vendor directory — "
                "urllib3, msgpack, setuptools. They are real files in the "
                "image, but the MCP never imports them and there is no "
                "upstream fix to install. pip has no business in a runtime "
                "virtualenv, so it is removed and the vendored copies go "
                "with it.")
    p(doc, "The result is a DERIVED image — FROM the upstream one — so every "
           "upstream layer, label, environment variable, user and entrypoint "
           "is preserved exactly. (podman commit would clobber the "
           "entrypoint.)")
    h3(doc, "Expected output")
    code(doc, """--- packages to upgrade ---
authlib==1.9.1
certifi==2026.10.18
dnspython==2.9.0
joserfc==1.7.5
pyjwt==2.14.0

<<< [step 06] OK""")
    callout(doc, "GOTCHA",
            "upgrade with --no-deps. Without it pip reshuffles the tree, "
            "downgrades jaraco.context and wheel, and ADDS findings rather "
            "than removing them.",
            "warn")

    # --- 07
    step_header(doc, "07", "the final Trivy gate",
                "manual/step-07-scan-trivy-final.sh",
                "no HIGH/CRITICAL library CVE")
    h3(doc, "What it does")
    p(doc, "The hard gate, run against the remediated image — the one that "
           "will actually ship.")
    bullet(doc, "no HIGH or CRITICAL library CVEs")
    bullet(doc, "no CRITICAL OS CVEs")
    code(doc, """trivy (library) exit code: 0
trivy (OS packages) exit code: 0

<<< [step 07] OK""")
    callout(doc, "THE RESULT",
            "19 HIGH/CRITICAL library findings down to 0, with the OS gate "
            "unchanged. The pipeline refuses to ship a known-vulnerable "
            "image, and if Trivy ever finds a HIGH/CRITICAL library CVE with "
            "no published fix, step 06 exits 3 and the run stops.",
            "pass")

    # --- 08
    step_header(doc, "08", "export the artifact",
                "manual/step-08-export-artifact.sh", "—")
    h3(doc, "What it does")
    p(doc, "podman save | gzip, plus the sha256. The artifact travels as a "
           "FILE, not through a registry — the DR site has to be able to "
           "receive a promoted image even when the PROD registry is down. "
           "That is the whole point of a DR site.")
    code(doc, """artifact : rhel-mcp-v1.0.04112601.tar.gz
size     : 118.4M
sha256   : 9c1f...  (also written to rhel-mcp-v1.0.04112601.tar.gz.sha256)

<<< [step 08] OK""")

    # --- 09
    step_header(doc, "09", "deploy to both sites", "manual/step-09-deploy.sh",
                "both units active")
    h3(doc, "What it does")
    p(doc, "ansible-playbook site.yml copies that ONE tarball to .105 and "
           ".104. Each site loads it into its own rootless podman store and "
           "runs it as a systemd USER unit. No root, no sudo password, no "
           "shared filesystem.")
    h3(doc, "Expected output")
    code(doc, """TASK [Load the artifact into the site's own podman store] ****
TASK [Install the MCP policy file] ****
TASK [Install the systemd user unit] ****
TASK [Start the MCP server] ****
TASK [Wait for the MCP endpoint] ****
192.168.147.105 : ok=8  changed=6  failed=0
192.168.147.104 : ok=8  changed=6  failed=0

<<< [step 09] OK""")
    callout(doc, "GOTCHA",
            "systemctl --user enable --now is a NO-OP on an already-active "
            "unit, so a redeploy would load the new image into the store and "
            "leave the container running the OLD one. The role therefore uses "
            "systemctl --user restart, and then removes the superseded "
            "images so each build does not leave 325 MB behind.",
            "warn")

    # --- 10
    step_header(doc, "10", "verify PROD", "manual/step-10-verify-prod.sh",
                "hostname + listening port")
    h3(doc, "What it does")
    p(doc, "Asks the PROD endpoint who it is — and proves the answer is "
           "real. Two MCP tools are called in ONE session:")
    rich(doc, [("get_system_information", {"mono": True, "bold": True}),
               (" says ", {}),
               ("which site", {"bold": True}),
               (" is answering. ", {}),
               ("get_listening_ports", {"mono": True, "bold": True}),
               (" says port 8095 on that host is held by the "
                "linux-mcp-server process. Together they mean the hostname "
                "cannot have come from a canned string — the MCP really "
                "reached the host's kernel over SSH and read its socket "
                "table.", {})])
    h3(doc, "Expected output")
    code(doc, """[verify] tools exposed (19): get_cpu_information, get_disk_usage, ...

[verify] get_system_information(host=192.168.147.105) returned:
{"hostname":"server-gateway.example.com","os_name":"Red Hat Enterprise Linux 8.10 (Ootpa)", ...}

[verify] get_listening_ports(host=192.168.147.105) returned:
=== Listening Ports ===

Proto    Local Address                  Status          PID/Program
--------------------------------------------------------------------------------
TCP      0.0.0.0:8095                   LISTEN          users:(("linux-mcp-serve",pid=2150982,fd=8))
...

[verify] PASS: get_listening_ports reports '8095'
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com

<<< [step 10] OK""")

    # --- 11
    step_header(doc, "11", "the failover drill", "manual/step-11-failover.sh",
                "the readiness probe")
    h3(doc, "What it does — three things, in this order")
    p(doc, "1.  Warm the standby.", bold=True)
    p(doc, "dr-warmup.yml starts the DR MCP and waits for the port. "
           "PRODUCTION KEEPS SERVING THROUGHOUT — the standby is checked "
           "before anything is taken away.")
    p(doc, "2.  The readiness gate.", bold=True)
    p(doc, "The MCP asks the DR site what it can see of ITSELF, and the "
           "answer is compared against the minimums in manual/env.sh "
           "(2 cores, 10 % memory free, 10 % disk free on the tightest real "
           "filesystem).")
    code(doc, """[probe] hostname        : localhost.localdomain
[probe] CPU
[probe]   logical cores : 4
[probe] memory
[probe]   RAM total     : 7.5 GiB
[probe]   RAM available : 5.4 GiB  (72.2 % free)
[probe] disk
[probe]   /            xfs      25.4 GiB total     5.9 GiB used    19.5 GiB free  ( 76.8 % free)
[probe]   (14 pseudo filesystems skipped — tmpfs, overlay, ... — only real ones are gated)

[probe] READY: localhost.localdomain has 4 cores, 72.2 % memory free, 76.8 % disk free (tightest: / (xfs))""")
    callout(doc, "IF THE GATE FAILS",
            "the drill is ABORTED. The standby goes back down, PROD keeps "
            "serving, and the step exits 1:",
            "fail")
    code(doc, """[probe] NOT READY for failover:
[probe]   - only 4 logical cores, need at least 64

BLOCKED: the DR site is not fit to take over. Rolling back.
...
    PROD is still serving — production was never at risk.""")

    p(doc, "3.  The cutover.", bold=True)
    p(doc, "failover.yml stops the PROD MCP and promotes DR, then the "
           "endpoint is asked again.")
    code(doc, """[verify] PASS: get_listening_ports reports '8095'
[verify] PASS: http://192.168.147.104:8095/mcp is serving localhost.localdomain

    the PROD endpoint is now down. Ask it anything — it will not answer:
  http://192.168.147.105:8095/mcp -> HTTP 000
  connection refused (expected)

<<< [step 11] OK""")

    # --- 12
    step_header(doc, "12", "failback", "manual/step-12-failback.sh",
                "PROD answers again")
    h3(doc, "What it does")
    p(doc, "The exact inverse. failback.yml stops the DR MCP and starts PROD "
           "again, then the endpoint is asked again — and the listening-ports "
           "proof shows the MCP process is back on 8095 on the PROD host. "
           "The same artifact, the same socket, the original site.")
    code(doc, """[verify] PASS: get_listening_ports reports '8095'
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com

<<< [step 12] OK""")

    # --- 13
    step_header(doc, "13", "the evidence", "manual/step-13-show-same-artifact.sh",
                "image ID + layers")
    h3(doc, "What it does")
    p(doc, "This is not a Jenkins stage — it is the proof that ties the "
           "demo together. Two different machines loaded the same tarball, "
           "so the image they run MUST be identical. It compares the image "
           "ID (the authoritative identity) and every layer digest (the "
           "content itself).")
    code(doc, """  192.168.147.105    image id  ec616084ab360b11f21b9d90a4ed825cd39d795770c43e67eceebf7253a946aa
  192.168.147.104    image id  ec616084ab360b11f21b9d90a4ed825cd39d795770c43e67eceebf7253a946aa

  layers (identical content, in order):
       1  sha256:50830ca4b47aab8a2525635f36c715ec73d0f48c37549bdcdd6a5fb0cf4c354a
       2  sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef
       ...

  manifest digest  PROD sha256:3974f7bd233198a2760f4951d3fee133bbeeb5cf8cc7aa92565126c80fff196c
  manifest digest  DR   sha256:bc8db3c2b1660dc11bfe0ea4624d8bdd2e61551334e322d25101655bb05c7bab

PASS: both sites run the SAME image (ec616084ab36)
      and every one of its layers is byte-identical""")
    callout(doc, "WHY THE MANIFEST DIGESTS DIFFER",
            "and why that is fine. Each site's podman rebuilds the manifest "
            "when it loads the tarball, and the two hosts do not run the "
            "same podman build (.105 has 4.9.4-rhel, .104 has 4.9.4-dev). "
            "The manifest bytes — and therefore their hash — differ even "
            "though every layer is identical. The image ID and the layer "
            "hashes are the content identity, and those match.",
            "info")

    # ------------------------------------------------------ the MCP ------
    h1(doc, "7.  The MCP: what each tool is for")

    p(doc, "The MCP is Red Hat's own linux-mcp-server, deployed unmodified "
           "at commit 6d7ca1d1. Two things about it matter here:")
    bullet(doc, "its upstream Containerfile sets ENV container=docker, which "
                "makes the server REFUSE to execute locally and require a "
                "remote host over SSH. That is exactly what this demo needs: "
                "the container inspects its own host's sshd, so the answer "
                "identifies the site that is actually serving.")
    bullet(doc, "over an HTTP transport the server evaluates EVERY tool call "
                "against an authorization policy, and a call that matches no "
                "rule is denied. There is no implicit 'allow' over HTTP — "
                "that behaviour only exists on the stdio transport. The role "
                "therefore installs a policy file with a single wildcard rule "
                "(action: ssh_default, all_users: true).")

    h2(doc, "The five tools that carry weight")
    p(doc, "These are the tools the pipeline actually calls. Each one proves "
           "something the others cannot.")

    table(doc,
          ["Tool", "Used in", "What it proves that nothing else could"],
          [["get_system_information",
            "steps 10, 11, 12",
            "WHICH SITE IS LIVE. Same image, different hostname — the MCP "
            "answers from whichever host it is deployed on. This is the "
            "demo's punchline."],
           ["get_listening_ports",
            "steps 10, 11, 12",
            "THAT THE ANSWER IS REAL. Port 8095 on that host is held by the "
            "linux-mcp-server process, so the hostname cannot have come from "
            "a canned string."],
           ["get_cpu_information",
            "step 11 (readiness)",
            "IS THE STANDBY BIG ENOUGH? The core count of the DR box, "
            "measured by the same tool that will later report on it in "
            "production."],
           ["get_memory_information",
            "step 11 (readiness)",
            "IS THERE ROOM TO RUN? How much of the DR box's RAM is actually "
            "available, not what the spec sheet says."],
           ["get_disk_usage",
            "step 11 (readiness)",
            "IS THERE ROOM TO WRITE? Free space on the tightest real "
            "filesystem on the DR box."]],
          widths=[1.5, 1.2, 3.9], mono_cols=[0])

    h2(doc, "The readiness gate in detail")
    p(doc, "This is the difference between a failover DEMONSTRATION and a "
           "failover GATE. A demonstration proves the switch happened. A gate "
           "proves the switch was safe.")
    p(doc, "The probe runs before any cutover, against the standby's own MCP, "
           "while production is still serving. It calls four tools in one "
           "session and checks the numbers:")
    table(doc,
          ["Check", "Minimum", "Why"],
          [["logical cores", "2",
            "the workload has to fit on the box you are failing over to"],
           ["RAM available", "10 % free",
            "a standby that is already swapping will not survive the load"],
           ["tightest real filesystem", "10 % free",
            "a full disk on the standby is an outage waiting to happen"]],
          widths=[1.6, 1.2, 3.8])
    p(doc, "Only real filesystems are gated. tmpfs, overlay and the other "
           "pseudo mounts are skipped, because a 3-byte devtmpfs would "
           "otherwise dominate the calculation. The tightest one wins — "
           "capacity is only as good as the worst filesystem.")

    h2(doc, "The other fourteen tools")
    p(doc, "All nineteen tools are exposed and all nineteen work over the "
           "same SSH transport. The remaining fourteen are simply not needed "
           "to prove a failover, and using them for their own sake would "
           "make the pipeline longer without making it stronger:")
    table(doc,
          ["Tool", "What it would be for here"],
          [["get_service_status",
            "asserting that sshd is healthy on the site being promoted — the "
            "natural next gate if the drill ever needs to prove the "
            "transport itself, not just the destination"],
           ["list_services",
            "showing what else is running on the standby, and therefore what "
            "else a cutover would disturb"],
           ["get_journal_logs / read_log_file / get_service_logs",
            "the 'why was the standby not ready' investigation — the first "
            "thing you reach for after a readiness gate fails"],
           ["get_network_interfaces / get_network_connections",
            "confirming the standby is reachable on the network the traffic "
            "will actually use"],
           ["list_processes / get_process_info",
            "checking that nothing unexpected is already consuming the "
            "capacity the readiness gate just measured"],
           ["get_hardware_information",
            "recording the standby's hardware for the DR documentation — "
            "useful, but not a gate"],
           ["list_block_devices / list_directories / list_files / read_file",
            "read-only filesystem inspection. Genuinely useful tools, but "
            "they have no bearing on whether a failover is safe"]],
          widths=[2.2, 4.4], mono_cols=[0])

    callout(doc, "THE POINT",
            "the pipeline calls five of nineteen tools, and each of the five "
            "carries a gate that can stop the run. The other fourteen are "
            "available and working, but a tool that is never called is not "
            "part of the pipeline — it is only part of the API surface.",
            "pass")

    # ------------------------------------------------------ evidence ------
    h1(doc, "8.  The evidence a run leaves behind")

    p(doc, "Everything lands in manual-reports/ on the control plane. The "
           "Jenkins job archives the same kind of file — build #11 on "
           "2026-11-04 archived 14 of them and passed every gate, ending "
           "with the transcript below.")
    table(doc,
          ["File", "What it is"],
          [["aqua-report.html", "the Aqua compliance report"],
           ["aqua-scan.err", "the scanner's own log"],
           ["trivy-report.json / trivy-report.txt",
            "the baseline library scan (machine + human readable)"],
           ["trivy-os-report.txt", "the baseline OS scan"],
           ["pip-list.txt", "what is really installed in the upstream image"],
           ["cve-fixes.txt", "the packages the remediation upgraded"],
           ["trivy-final-report.txt", "the final library gate"],
           ["trivy-final-os-report.txt", "the final OS gate"],
           ["image-inspect.txt", "the image ID and layers from both sites"],
           ["failover-transcript.txt", "the whole drill, in order"]],
          widths=[2.4, 4.2])

    h2(doc, "The transcript")
    p(doc, "This is the real transcript archived by Jenkins build #11, cut "
           "down to the lines that carry the argument. The numbers are live "
           "measurements, so they move a little from run to run.")
    code(doc, """===== PROD verification =====
[verify] PASS: get_listening_ports reports '8095'
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com

===== DR READINESS PROBE (before any cutover) =====
[probe] hostname        : localhost.localdomain
[probe] CPU
[probe]   logical cores : 4
[probe] memory
[probe]   RAM available : 5.4 GiB  (72.2 % free)
[probe] disk
[probe]   /            xfs      25.4 GiB total     5.9 GiB used    19.5 GiB free  ( 76.8 % free)
[probe]   (14 pseudo filesystems skipped - tmpfs, overlay, ... - only real ones are gated)

[probe] READY: localhost.localdomain has 4 cores, 72.2 % memory free, 76.8 % disk free (tightest: / (xfs))

===== FAILOVER: DR is now serving =====
[verify] PASS: get_listening_ports reports '8095'
[verify] PASS: http://192.168.147.104:8095/mcp is serving localhost.localdomain

===== FAILBACK: PROD is serving again =====
[verify] PASS: get_listening_ports reports '8095'
[verify] PASS: http://192.168.147.105:8095/mcp is serving server-gateway.example.com""")

    h2(doc, "The end state")
    p(doc, "The drill ends with the FAILBACK, so PROD is live and DR is "
           "stopped. That is the intended DR posture, not a failure: a "
           "standby that is left running when it is not needed is standby "
           "you cannot trust.")

    # -------------------------------------------------- troubleshooting ----
    h1(doc, "9.  When it goes wrong")

    table(doc,
          ["Symptom", "Cause", "Fix"],
          [["the PROD endpoint refuses connections",
            "firewalld is blocking port 8095",
            "firewall-cmd --permanent --add-port=8095/tcp && firewall-cmd "
            "--add-port=8095/tcp — never --reload, it flushes podman's CNI "
            "chains"],
           ["the MCP container dies when you log out",
            "a systemd user unit without linger",
            "loginctl enable-linger <user>"],
           ["the site still runs the previous image after a deploy",
            "systemctl --user enable --now is a no-op on an active unit",
            "use systemctl --user restart — the role does"],
           ["Authorization denied: tool 'get_system_information'",
            "the policy file is missing, so over HTTP every call is denied",
            "check the unit mounts the policy and sets "
            "LINUX_MCP_POLICY_PATH"],
           ["the Aqua scan times out with a TLS handshake error",
            "the aqua-web console container lost its outbound path",
            "podman network reload on the host"],
           ["'API Service endpoint scheme \"\" is not supported'",
            "podman system service needs the unix:// prefix, and the "
            "directory must exist",
            "mkdir -p /run/user/$(id -u)/podman, then start the service with "
            "the unix:// prefix"],
           ["the build hangs on the pip install",
            "container egress is dropped in the firewalld FORWARD chain",
            "build with --network host"],
           ["the image lost its entrypoint after remediation",
            "podman commit was used instead of a derived build",
            "build the derived image with FROM <upstream>"],
           ["'version 3.6 is not supported' from Ansible",
            "the target interpreter is too old for ansible-core >= 2.15",
            "dnf install -y python39 on the target; the inventory already "
            "pins /usr/bin/python3.9"],
           ["a podman --format '{{.Repository}}' fails with a template error",
            "Ansible templated the Go template before podman saw it",
            "wrap it in {% raw %}{{...}}{% endraw %}"]],
          widths=[2.0, 2.2, 2.4])

    # ------------------------------------------------------- appendix -----
    h1(doc, "10.  Appendix — the interesting details")

    h3(doc, "Why the MCP answers over SSH at all")
    p(doc, "The upstream Containerfile sets ENV container=docker. That makes "
           "the server refuse local execution and require a remote host over "
           "SSH. In this demo the container runs with --network host and "
           "inspects its own host's sshd — so the answer identifies the site "
           "that is actually serving. The image is unmodified; this is how "
           "Red Hat intends it to be used.")

    h3(doc, "Why the artifact is a tarball and not a registry push")
    p(doc, "A DR site has to be able to receive a promoted image even when "
           "the PROD registry is down. That is the whole point of a DR site. "
           "The pipeline exports podman save | gzip and Ansible copies that "
           "ONE file to both sites, which load it into their own rootless "
           "podman stores. Both sites therefore run byte-identical content.")

    h3(doc, "Why the key lives in ~/.mcp-keys and not ~/.ssh")
    p(doc, "The bind mount needs the :z SELinux relabel, and that relabel "
           "would otherwise change the context of the host's own "
           "authorized_keys and break host SSH logins. A dedicated "
           "directory keeps the blast radius to the key that is supposed to "
           "be relabelled.")

    h3(doc, "Why --userns=keep-id:uid=1001,gid=1001")
    p(doc, "It makes the container's uid 1001 map to the host's uid 1001 — "
           "the deploy user — so the mounted private key (mode 0600, owned "
           "by that user) stays readable from inside the container.")

    h3(doc, "Why there is no become, anywhere")
    p(doc, "Each site is driven as its own non-root user (rhai on PROD, dr on "
           "DR) with rootless podman. dr never needs to be in the wheel group "
           "and no sudo password is involved at any point. The role runs "
           "systemctl --user, which needs loginctl enable-linger to survive "
           "logout.")

    h3(doc, "Why the client's address changes at the cutover")
    p(doc, "The service moves for real: the MCP unit is stopped on one host "
           "and started on the other, so the container really is running on "
           "the other site. The client's endpoint is changed by the caller — "
           "from http://192.168.147.105:8095/mcp to "
           "http://192.168.147.104:8095/mcp.")
    p(doc, "That is the one simulated part of the drill, and it is simulated "
           "on purpose. A client-facing address that survives a cutover needs "
           "a floating IP, and moving an address between hosts means "
           "'ip addr add', which needs CAP_NET_ADMIN — root on the target. "
           "Giving the deploy user root would undo the property the rest of "
           "the role is built on. Production DR uses a routing protocol "
           "instead: VRRP with keepalived, or pacemaker and corosync with "
           "fencing, so the address follows the elected master and split "
           "brain is actively prevented.")
    callout(doc, "THE LINE THE DEMO DRAWS",
            "the SERVICE moves for real; the ADDRESS is changed by the "
            "caller. Everything else is checkable — one tarball, two rootless "
            "stores, a unit genuinely stopped and started, and an MCP that "
            "reports the live site's own kernel state (hostname, cores, RAM, "
            "disk) rather than a canned string.",
            "info")

    h3(doc, "What is deliberately out of scope")
    bullet(doc, "NetApp and shared storage — the demo has no shared "
                "filesystem on purpose; the artifact travels as a file.")
    bullet(doc, "patching the upstream source — no file in linux-mcp-server "
                "is edited. The policy file, the systemd unit, the verify "
                "client and the probe all live in this repository. The IMAGE "
                "is hardened after the build; the SOURCE is untouched.")
    bullet(doc, "the chatbot's MCP registry — the chatbot can already "
                "consume this MCP through the existing HTTP bridge.")

    doc.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
