"""Render the pipeline and the PROD/DR drill as PNG diagrams.

    python docs/diagrams/pipeline/build_diagrams.py

Writes, next to this script:

    PROD-DR-Pipeline-Diagram.png   the pipeline: one image, two sites
    PROD-DR-Drill-Diagram.png      the failover drill, move by move
    diagram-pipeline.html          the source of the first one
    diagram-drill.html             the source of the second one

The HTML is written out on purpose: it is the thing to edit when a command
changes, and it can be opened in a browser and printed to PDF as well. The
PNG is what goes on a slide.

The rendering uses headless Chrome at 2x device scale, so the PNG is crisp
enough to read when it is projected.

    python docs/diagrams/pipeline/build_diagrams.py          # render everything
    python docs/diagrams/pipeline/build_diagrams.py --html   # HTML only
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# The house style, shared with build_guide.py.
BLUE = "#0B3D91"
INK = "#1A1A1A"
GREY = "#555555"
GREEN = "#1B6B3A"
AMBER = "#8A4A00"
RED = "#B30000"

COLORS = dict(ink=INK, blue=BLUE, grey=GREY, green=GREEN, amber=AMBER, red=RED,
              code="#F2F3F5", greenbg="#E9F5EE", infobg="#EAF1F8",
              redbg="#FBECEC")

BASE_CSS = """
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; background: #FFFFFF; color: %(ink)s;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .sheet { padding: 34px 40px 30px; }
  h1 {
    font-size: 30px; font-weight: 700; color: %(blue)s; margin: 0 0 2px 0;
    letter-spacing: -0.2px;
  }
  .sub { font-size: 15px; color: %(grey)s; margin: 0 0 22px 0; }
  .rule { height: 5px; background: %(blue)s; border-radius: 3px; margin: 0 0 22px 0; }
  code, .mono { font-family: Consolas, "DejaVu Sans Mono", monospace; }

  /* ---- boxes ---- */
  .panel {
    border: 1px solid #D5D5D5; border-radius: 10px; background: #FFFFFF;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
  }
  .panel-head {
    background: %(blue)s; color: #FFFFFF; border-radius: 9px 9px 0 0;
    padding: 8px 14px; font-size: 13px; font-weight: 600; letter-spacing: .3px;
  }
  .panel-body { padding: 14px; }

  .chip {
    border: 1px solid #D5D5D5; border-radius: 8px; background: #FFFFFF;
    padding: 8px 10px 9px 10px; position: relative; width: 302px;
  }
  .chip .n {
    display: inline-block; width: 20px; height: 20px; border-radius: 50%%;
    background: %(blue)s; color: #FFFFFF; font-size: 11px; font-weight: 700;
    text-align: center; line-height: 20px; margin-right: 6px;
  }
  .chip .t { font-size: 13.5px; font-weight: 600; color: %(ink)s; }
  .chip .c {
    font-family: Consolas, monospace; font-size: 10.5px; color: #333333;
    background: %(code)s; border-radius: 4px; padding: 4px 6px; margin-top: 6px;
    line-height: 1.35; word-break: break-word;
  }
  .chip.gate { border-color: %(green)s; background: %(greenbg)s; }
  .chip.gate .n { background: %(green)s; }
  .chip .gatebadge {
    float: right; font-size: 9.5px; font-weight: 700; letter-spacing: .6px;
    color: %(green)s; border: 1px solid %(green)s; border-radius: 3px;
    padding: 1px 5px; margin-top: 2px;
  }

  .arrow { text-align: center; color: %(blue)s; font-size: 20px; line-height: 1;
           margin: 8px 0; }

  .site {
    border: 1px solid #D5D5D5; border-radius: 10px; overflow: hidden; width: 640px;
  }
  .site .hd { padding: 8px 14px; color: #FFFFFF; font-size: 14px; font-weight: 600; }
  .site.prod .hd { background: %(blue)s; }
  .site.dr   .hd { background: #2C6E49; }
  .site .bd { padding: 12px 14px 14px 14px; }
  .row {
    font-family: Consolas, monospace; font-size: 11.5px; color: #333333;
    background: %(code)s; border-radius: 4px; padding: 5px 8px; margin-bottom: 6px;
    line-height: 1.4;
  }
  .row .lbl { color: %(grey)s; }
  .answer {
    font-size: 14px; font-weight: 600; color: %(blue)s; margin-top: 9px;
    font-family: Consolas, monospace;
  }
  .site.dr .answer { color: #2C6E49; }

  .note {
    background: %(infobg)s; border-left: 4px solid %(blue)s; border-radius: 0 6px 6px 0;
    padding: 9px 13px; font-size: 12.5px; color: %(ink)s; line-height: 1.45;
  }
  .note b { color: %(blue)s; }
""" % COLORS


# --------------------------------------------------------------------------- #
#  1.  THE PIPELINE
# --------------------------------------------------------------------------- #
PIPELINE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>%(base)s

  .jenkins {
    border: 1px solid #D5D5D5; border-radius: 10px; overflow: hidden;
  }
  .jenkins .hd {
    background: %(blue)s; color: #fff; padding: 9px 14px;
    font-size: 14px; font-weight: 600;
  }
  .jenkins .hd .mono { color: #C8D8F0; font-weight: 400; font-size: 12px; }
  .grid { display: flex; flex-wrap: wrap; gap: 12px; }
  .artbar {
    background: %(greenbg)s; border: 1px solid %(green)s; border-radius: 8px;
    padding: 10px 14px; text-align: center; font-size: 14px; font-weight: 600;
    color: %(green)s; width: 640px;
  }
  .artbar .mono { display: block; font-size: 11.5px; font-weight: 400;
                  color: #33503F; margin-top: 4px; }
  .cols { display: flex; gap: 28px; justify-content: center; }
  .sites { display: flex; gap: 28px; justify-content: center; margin-top: 10px; }
</style></head>
<body><div class="sheet">

  <h1>PROD/DR MCP Pipeline</h1>
  <div class="sub">One image, built and scanned once, deployed to two sites.
     Every stage is a stage of the <span class="mono">Jenkinsfile</span>.</div>
  <div class="rule"></div>

  <div class="jenkins">
    <div class="hd">Jenkins on .105 (control plane) &nbsp;&middot;&nbsp;
      <span class="mono">Jenkinsfile</span></div>
    <div class="panel-body">
      <div class="grid">
        %(chips)s
      </div>
    </div>
  </div>

  <div class="arrow">&#9660;</div>

  <div style="display:flex; justify-content:center;">
    <div class="artbar">
      ONE tarball &middot; ONE sha256 &mdash; it travels as a file, not through a registry
      <span class="mono">rhel-mcp-v1.0.&lt;DDMMYY&gt;&lt;NN&gt;.tar.gz</span>
    </div>
  </div>

  <div class="arrow">&#9660;</div>

  <div class="sites">
    <div class="site prod">
      <div class="hd">PROD &nbsp;&middot;&nbsp; 192.168.147.105 &nbsp;&middot;&nbsp; deploy user rhai</div>
      <div class="bd">
        <div class="row"><span class="lbl">load   </span>podman load --input rhel-mcp-....tar.gz</div>
        <div class="row"><span class="lbl">run    </span>systemctl --user restart rhel-mcp.service</div>
        <div class="row"><span class="lbl">serve  </span>rhel-mcp :8095/mcp &nbsp;(LINUX_MCP_HOST=0.0.0.0)</div>
        <div class="row"><span class="lbl">ssh    </span>MCP --SSH--&gt; .105's own sshd (127.0.0.1)</div>
        <div class="answer">answers: server-gateway.example.com</div>
      </div>
    </div>

    <div class="site dr">
      <div class="hd">DR &nbsp;&middot;&nbsp; 192.168.147.104 &nbsp;&middot;&nbsp; deploy user dr</div>
      <div class="bd">
        <div class="row"><span class="lbl">load   </span>podman load --input rhel-mcp-....tar.gz</div>
        <div class="row"><span class="lbl">run    </span>systemctl --user restart rhel-mcp.service</div>
        <div class="row"><span class="lbl">serve  </span>rhel-mcp :8095/mcp &nbsp;(LINUX_MCP_HOST=0.0.0.0)</div>
        <div class="row"><span class="lbl">ssh    </span>MCP --SSH--&gt; .104's own sshd (127.0.0.1)</div>
        <div class="answer">answers: localhost.localdomain</div>
      </div>
    </div>
  </div>

  <div class="arrow">&#9660;</div>

  <div style="display:flex; justify-content:center;">
    <div class="note" style="width:1308px;">
      <b>The MCP inspects the host it is deployed on.</b> The upstream image sets
      <span class="mono">ENV container=docker</span>, so the server refuses to run locally
      and must reach a host over SSH &mdash; and it reaches <b>its own</b> host's sshd.
      That is why the same bytes give a different answer on each site:
      the answer is the live machine's real hostname, cores, RAM and disk,
      read over SSH from the kernel &mdash; never a canned string.
    </div>
  </div>

</div></body></html>
"""

PIPELINE_CHIPS = [
    (1, "Checkout",
     "git clone git://127.0.0.1:9418/\n mcp-dr-pipeline.git", False),
    (2, "Fetch the MCP source",
     "curl -fsSL .../linux-mcp-server/\n archive/6d7ca1d1....tar.gz", False),
    (3, "Resolve the version",
     "VERSION + date +%d%m%y\n -&gt; v1.0.&lt;DDMMYY&gt;&lt;NN&gt;", False),
    (4, "Build the image",
     "podman build --file upstream/\n Containerfile --format docker", False),
    (5, "Aqua scan",
     "podman run ...scanner scan\n --local ... | grep Compliant", True),
    (6, "Trivy scan (baseline)",
     "podman run ...trivy image\n --scanners vuln --pkg-types library", False),
    (7, "Security remediation",
     "scripts/trivy_cve_packages.py\n -&gt; Containerfile.remediated", False),
    (8, "Trivy final scan",
     "trivy image --exit-code 1\n -&gt; 0 HIGH / CRITICAL", True),
    (9, "Export the artifact",
     "podman save &lt;image&gt; | gzip\n &gt; ....tar.gz ; sha256sum", False),
    (10, "Deploy to BOTH sites",
     "ansible-playbook -i inventory.ini\n site.yml", False),
]


def _pipeline_chips() -> str:
    out = []
    for num, title, cmd, gate in PIPELINE_CHIPS:
        badge = '<span class="gatebadge">GATE</span>' if gate else ""
        cls = "chip gate" if gate else "chip"
        out.append(
            f'<div class="{cls}">{badge}'
            f'<div><span class="n">{num}</span><span class="t">{title}</span></div>'
            f'<div class="c">{cmd}</div></div>'
        )
    return "\n".join(out)


# --------------------------------------------------------------------------- #
#  2.  THE DRILL
# --------------------------------------------------------------------------- #
DRILL_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>%(base)s

  .dgrid {
    display: grid; grid-template-columns: 1fr 268px 268px; gap: 0;
    border: 1px solid #D5D5D5; border-radius: 10px; overflow: hidden;
  }
  .gh { padding: 8px 12px; color: #fff; font-size: 13.5px; font-weight: 700; }
  .gh.m { background: #3C3C3C; }
  .gh.p { background: %(blue)s; }
  .gh.d { background: #2C6E49; }
  .cell { padding: 12px; border-top: 1px solid #E4E4E4; }
  .cell.p, .cell.d { border-left: 1px solid #E4E4E4; }

  .move { display: flex; gap: 12px; }
  .mnum {
    flex: 0 0 30px; height: 30px; border-radius: 50%%; background: %(blue)s;
    color: #fff; font-size: 14px; font-weight: 700; text-align: center;
    line-height: 30px;
  }
  .mnum.gate { background: %(green)s; }
  .mbody { flex: 1; }
  .mtitle { font-size: 14.5px; font-weight: 600; margin-bottom: 2px; }
  .mwhat { font-size: 12px; color: %(grey)s; margin-bottom: 7px; line-height: 1.4; }
  .mcmd {
    font-family: Consolas, monospace; font-size: 10.5px; line-height: 1.5;
    background: %(code)s; border-radius: 5px; padding: 7px 9px; color: #2B2B2B;
    white-space: pre-wrap;
  }
  .mcmd b { color: %(blue)s; }
  .state { font-size: 12px; padding: 7px 9px; border-radius: 5px; line-height: 1.4; }
  .state.live { background: %(greenbg)s; color: %(green)s; font-weight: 600; }
  .state.down { background: %(redbg)s; color: %(red)s; font-weight: 600; }
  .state.warm { background: %(infobg)s; color: %(blue)s; font-weight: 600; }
</style></head>
<body><div class="sheet">

  <h1>The failover drill</h1>
  <div class="sub">Five moves. Production is never at risk until move&nbsp;4 &mdash;
     the standby has to prove it can carry the load first.</div>
  <div class="rule"></div>

  <div class="dgrid">
    <div class="gh m">WHAT HAPPENS &mdash; AND THE COMMAND THAT DOES IT</div>
    <div class="gh p">PROD &middot; 192.168.147.105</div>
    <div class="gh d">DR &middot; 192.168.147.104</div>
    %(rows)s
  </div>

  <div style="height:16px"></div>
  <div style="display:flex; justify-content:center;">
    <div class="note" style="width:1300px;">
      <b>The honest line.</b> The <b>service</b> moves for real: the unit is stopped on
      one host and started on the other. The <b>client's address</b> is changed by the
      caller &mdash; a floating IP would need <span class="mono">ip addr add</span>, i.e. root
      on the target, and this demo never gives the deploy user root. Production DR does
      it with VRRP/keepalived or pacemaker&nbsp;+&nbsp;corosync instead.
    </div>
  </div>

</div></body></html>
"""

MOVES = [
    dict(n="1", gate=False, title="Warm the standby",
         what="Bring the DR MCP up while PROD keeps serving. "
              "<span class=\"mono\">ansible/dr-warmup.yml</span>",
         cmd="<b>ansible-playbook</b> -i inventory.ini dr-warmup.yml\n"
             "  -&gt; systemctl --user start rhel-mcp.service   (on .104)",
         prod=("live", "&#9679; live<br>:8095 answering"),
         dr=("down", "&#9675; stopped")),
    dict(n="2", gate=True, title="The readiness gate",
         what="Ask the standby what it can see of <i>itself</i>, through the MCP, "
              "before anything is cut over. <span class=\"mono\">scripts/mcp_dr_probe.py</span>",
         cmd="<b>podman run</b> -i --rm --network host &lt;image&gt; - \\\n"
             "    --url http://192.168.147.104:8095/mcp \\\n"
             "    --target 192.168.147.104 \\\n"
             "    --expect localhost.localdomain ...\n"
             "  < scripts/mcp_dr_probe.py\n"
             "  get_system_information / get_cpu_information /\n"
             "  get_memory_information / get_disk_usage",
         prod=("live", "&#9679; still serving<br><span style=\"font-weight:400\">the gate runs "
                        "WHILE production is up</span>"),
         dr=("warm", "&#9679; started<br><span style=\"font-weight:400\">4 cores &middot; 72 % RAM "
                      "free &middot; 77 % disk free<br>&rarr; <b>READY</b> &nbsp;|&nbsp; "
                      "not ready &rarr; abort, PROD untouched</span>")),
    dict(n="3", gate=False, title="The cutover",
         what="Stop the MCP on PROD, start it on DR. "
              "<span class=\"mono\">ansible/failover.yml</span>",
         cmd="<b>ansible-playbook</b> -i inventory.ini failover.yml\n"
             "  -&gt; systemctl --user stop  rhel-mcp.service   (on .105)\n"
             "  -&gt; systemctl --user start rhel-mcp.service   (on .104)",
         prod=("live", "&#9679; still serving<br><span style=\"font-weight:400\">until the unit "
                        "is stopped</span>"),
         dr=("live", "&#9679; live<br><span style=\"font-weight:400\">:8095 now answers on .104</span>")),
    dict(n="4", gate=True, title="Verify the new live site",
         what="Two facts in one session: the hostname says <i>which</i> site is live, "
              "the socket table says the answer is real. "
              "<span class=\"mono\">scripts/mcp_verify.py</span>",
         cmd="<b>podman run</b> -i --rm --network host &lt;image&gt; - \\\n"
             "    --url http://192.168.147.104:8095/mcp \\\n"
             "    --expect localhost.localdomain \\\n"
             "    --call get_listening_ports \\\n"
             "    --assert get_listening_ports=8095\n"
             "  &lt; scripts/mcp_verify.py",
         prod=("down", "&#9675; stopped<br>:8095 refused"),
         dr=("live", "&#9679; live<br><span style=\"font-weight:400\">localhost.localdomain, "
                      "and 8095 held by<br>linux-mcp-server</span>")),
    dict(n="5", gate=False, title="Fail back",
         what="The exact mirror: stop DR, start PROD, verify again. "
              "<span class=\"mono\">ansible/failback.yml</span>",
         cmd="<b>ansible-playbook</b> -i inventory.ini failback.yml\n"
             "  -&gt; systemctl --user stop  rhel-mcp.service   (on .104)\n"
             "  -&gt; systemctl --user start rhel-mcp.service   (on .105)",
         prod=("live", "&#9679; live again<br><span style=\"font-weight:400\">answers "
                        "server-gateway.example.com</span>"),
         dr=("down", "&#9675; stopped<br>:8095 refused")),
]


def build_drill_html() -> str:
    rows = []
    for m in MOVES:
        cls = "mnum gate" if m["gate"] else "mnum"
        move = (f'<div class="move"><div class="{cls}">{m["n"]}</div>'
                f'<div class="mbody">'
                f'<div class="mtitle">{m["title"]}</div>'
                f'<div class="mwhat">{m["what"]}</div>'
                f'<div class="mcmd">{m["cmd"]}</div>'
                f'</div></div>')
        pk, pv = m["prod"]
        dk, dv = m["dr"]
        rows.append(
            f'<div class="cell m">{move}</div>'
            f'<div class="cell p"><div class="state {pk}">{pv}</div></div>'
            f'<div class="cell d"><div class="state {dk}">{dv}</div></div>'
        )
    return DRILL_HTML % dict(base=BASE_CSS, rows="\n".join(rows), **COLORS)


# --------------------------------------------------------------------------- #
#  render
# --------------------------------------------------------------------------- #
def trim(png_path: Path, pad: int = 56) -> None:
    """Cut the empty space off the bottom of the screenshot.

    Chrome renders whatever window size it is given, so a page shorter than
    the window leaves a band of white at the bottom.  The background is plain
    white, so the content is whatever differs from it.
    """
    from PIL import Image, ImageChops

    with Image.open(png_path) as im:
        rgb = im.convert("RGB")
        white = Image.new("RGB", rgb.size, (255, 255, 255))
        bbox = ImageChops.difference(rgb, white).getbbox()
        if bbox is None:
            return
        bottom = min(rgb.height, bbox[3] + pad)
        if bottom >= rgb.height:
            return
        rgb.crop((0, 0, rgb.width, bottom)).save(png_path)


def render(html_path: Path, png_path: Path, width: int, height: int) -> None:
    """Screenshot the page with headless Chrome at 2x scale."""
    cmd = [
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-sandbox",
        "--default-background-color=FFFFFFFF",
        "--force-device-scale-factor=2",
        f"--window-size={width},{height}",
        f"--screenshot={png_path}",
        html_path.as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if not png_path.exists():
        raise SystemExit(f"chrome did not write {png_path}\n{result.stderr[:2000]}")
    trim(png_path)
    from PIL import Image

    with Image.open(png_path) as im:
        size = f"{im.width}x{im.height}"
    print(f"wrote {png_path}  ({png_path.stat().st_size // 1024} KB, {size})")


def main() -> int:
    html_only = "--html" in sys.argv

    pipeline_html = HERE / "diagram-pipeline.html"
    drill_html = HERE / "diagram-drill.html"
    pipeline_png = HERE / "PROD-DR-Pipeline-Diagram.png"
    drill_png = HERE / "PROD-DR-Drill-Diagram.png"

    pipeline_html.write_text(
        PIPELINE_HTML % dict(base=BASE_CSS, chips=_pipeline_chips(), **COLORS),
        encoding="utf-8")
    drill_html.write_text(build_drill_html(), encoding="utf-8")
    print(f"wrote {pipeline_html}")
    print(f"wrote {drill_html}")

    if html_only:
        return 0

    if not Path(CHROME).exists():
        raise SystemExit(f"chrome not found at {CHROME}")

    render(pipeline_html, pipeline_png, 1700, 1180)
    render(drill_html, drill_png, 1700, 1240)
    return 0


if __name__ == "__main__":
    sys.exit(main())
