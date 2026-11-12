"""Render the PROD/DR workflow as two UML diagrams.

    python docs/diagrams/uml/build_uml.py

Writes, next to this script:

    PROD-DR-Sequence-Diagram.png   the failover drill, as a sequence diagram
    PROD-DR-Activity-Diagram.png   the pipeline, as an activity diagram
    uml-sequence.html              the source of the first one
    uml-activity.html              the source of the second one

There is no PlantUML on this machine, so the diagrams are drawn as SVG and
screenshot the same way the other two are — through headless Chrome, at 2x
scale. The house style comes from build_diagrams.py, one folder up.

    python docs/diagrams/uml/build_uml.py          # render everything
    python docs/diagrams/uml/build_uml.py --html   # write the HTML only
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "pipeline"))

# Reuse the house style rather than duplicating it.
from build_diagrams import BASE_CSS, COLORS, render  # noqa: E402

FONT = "Segoe UI, Helvetica Neue, Arial, sans-serif"
MONO = "Consolas, DejaVu Sans Mono, monospace"

INK = COLORS["ink"]
BLUE = COLORS["blue"]
GREY = COLORS["grey"]
GREEN = COLORS["green"]
AMBER = COLORS["amber"]
RED = COLORS["red"]
LINE = "#C9D6E8"
PALE = "#EAF1F8"
PALE_GREEN = "#E9F5EE"
PALE_RED = "#FBECEC"
PALE_AMBER = "#FDF3E6"


# --------------------------------------------------------------------------- #
#  svg helpers
# --------------------------------------------------------------------------- #
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markers() -> str:
    def mk(mid: str, color: str) -> str:
        return (f'<marker id="{mid}" markerWidth="12" markerHeight="10" refX="11" '
                f'refY="5" orient="auto" markerUnits="userSpaceOnUse">'
                f'<path d="M0,0 L12,5 L0,10 z" fill="{color}"/></marker>')

    return ("<defs>"
            + mk("m-ink", INK)
            + mk("m-grey", "#8A8A8A")
            + mk("m-green", GREEN)
            + mk("m-red", RED)
            + mk("m-blue", BLUE)
            + "</defs>")


def txt(x: float, y: float, s: str, size: float = 12.5, color: str = INK,
        anchor: str = "middle", weight: str = "400", family: str = FONT,
        halo: bool = False, italic: bool = False) -> str:
    extra = ""
    if halo:
        extra += ' stroke="#FFFFFF" stroke-width="4" paint-order="stroke" stroke-linejoin="round"'
    if italic:
        extra += ' font-style="italic"'
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}" font-weight="{weight}"'
            f'{extra}>{esc(s)}</text>')


def arrow(x1: float, y1: float, x2: float, y2: float, marker: str = "m-ink",
          stroke: str = INK, width: float = 1.6, dash: str | None = None) -> str:
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{width}" marker-end="url(#{marker})"{d}/>')


def self_msg(x: float, y: float, marker: str = "m-ink", stroke: str = INK,
             depth: float = 40, drop: float = 26) -> str:
    return (f'<polyline points="{x},{y} {x + depth},{y} {x + depth},{y + drop} '
            f'{x + 10},{y + drop}" fill="none" stroke="{stroke}" stroke-width="1.6" '
            f'marker-end="url(#{marker})"/>')


def bar(x: float, y0: float, y1: float, color: str = "#CFE0F2") -> str:
    return (f'<rect x="{x - 5}" y="{y0}" width="10" height="{y1 - y0}" '
            f'fill="{color}" rx="2"/>')


def action(x: float, y: float, title: str, cmd: str, w: float = 400,
           fill: str = "#FFFFFF", stroke: str = LINE, tcolor: str = INK) -> str:
    """A UML action node: a rounded box, a title and a command under it."""
    h = 60
    out = [f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" '
           f'rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>']
    out.append(txt(x, y - 4, title, 13.5, tcolor, weight="600"))
    if cmd:
        out.append(txt(x, y + 17, cmd, 11, GREY, family=MONO))
    return "".join(out)


def decision(x: float, y: float, lines: list[str], w: float = 430,
             h: float = 104) -> str:
    """A UML decision node: a diamond with the test inside it."""
    pts = f"{x},{y - h / 2} {x + w / 2},{y} {x},{y + h / 2} {x - w / 2},{y}"
    out = [f'<polygon points="{pts}" fill="#FFFFFF" stroke="{BLUE}" '
           f'stroke-width="1.6"/>']
    first = y - 6 if len(lines) > 1 else y + 5
    out.append(txt(x, first, lines[0], 13, INK, weight="600"))
    if len(lines) > 1:
        out.append(txt(x, first + 20, lines[1], 11, GREY))
    return "".join(out)


def bar_node(x: float, y: float, w: float = 240, h: float = 14) -> str:
    """A UML fork / join bar."""
    return (f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" '
            f'rx="3" fill="{INK}"/>')


def terminal(x: float, y: float, r: float = 15) -> str:
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{INK}"/>'


def band(x: float, y: float, w: float, h: float, label: str, fill: str,
         stroke: str, label_at: str = "top") -> str:
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" '
           f'stroke="{stroke}" stroke-width="1.2" stroke-dasharray="6 5"/>']
    ly = y + 21 if label_at == "top" else y + h - 11
    out.append(txt(x + 16, ly, label, 12, GREY, anchor="start", weight="600"))
    return "".join(out)


def edge(points: list[tuple[float, float]], marker: str = "m-ink",
         stroke: str = INK, width: float = 1.6, dash: str | None = None) -> str:
    pts = " ".join(f"{x},{y}" for x, y in points)
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polyline points="{pts}" fill="none" stroke="{stroke}" '
            f'stroke-width="{width}" marker-end="url(#{marker})"{d}/>')


# --------------------------------------------------------------------------- #
#  1. the sequence diagram — the drill as a conversation
# --------------------------------------------------------------------------- #
CLIENT, JENKINS, PROD, DR = 0, 1, 2, 3

LIFELINES = [
    (210, "Client", "your MCP client", BLUE, PALE),
    (560, "Jenkins", ".105 · control plane", GREY, "#F4F5F6"),
    (930, "PROD MCP", ".105 :8095", BLUE, PALE),
    (1300, "DR MCP", ".104 :8095", GREEN, PALE_GREEN),
]

# (y, source, target, label, kind, activation-bar-on)
MESSAGES = [
    (175, CLIENT, PROD, "get_system_information", "call", (PROD, 265)),
    (212, PROD, PROD, "ssh 127.0.0.1 → its own host's facts", "self", None),
    (258, PROD, CLIENT, "server-gateway.example.com", "ret", None),

    (330, JENKINS, DR, "ansible/dr-warmup.yml → systemctl --user start", "call", None),
    (405, JENKINS, DR, "scripts/mcp_dr_probe.py → system, cpu, memory, disk", "call", (DR, 508)),
    (442, DR, DR, "ssh 127.0.0.1 → its own host's facts", "self", None),
    (500, DR, JENKINS, "READY  (not ready → abort, PROD keeps serving)", "ok", None),

    (585, JENKINS, PROD, "ansible/failover.yml → systemctl --user stop", "call", None),
    (650, JENKINS, DR, "systemctl --user start  (idempotent)", "call", None),

    (725, CLIENT, PROD, "get_system_information", "call", None),
    (770, PROD, CLIENT, "connection refused — :8095 is gone from .105", "bad", None),

    (840, CLIENT, DR, "get_system_information + get_listening_ports", "call", (DR, 950)),
    (877, DR, DR, "ssh 127.0.0.1 → its own host's facts", "self", None),
    (935, DR, CLIENT, "localhost.localdomain · 8095 held by linux-mcp-server", "ok", None),

    (1000, JENKINS, DR, "ansible/failback.yml → systemctl --user stop", "call", None),
    (1060, JENKINS, PROD, "ansible/failback.yml → systemctl --user start", "call", None),

    (1130, CLIENT, PROD, "get_system_information", "call", (PROD, 1183)),
    (1175, PROD, CLIENT, "server-gateway.example.com — back again", "ok", None),
]

# The service state on each site, as (y_from, y_to, state).  The lifeline is
# drawn in that state: solid green while the MCP is running, dashed red while
# it is stopped.  The boundaries are the messages that change the state.
STATE_UP = "up"
STATE_DOWN = "down"

LIFELINE_STATES = {
    # .105 is live at the start of the drill, until failover.yml stops it.
    PROD: [(128, 585, STATE_UP), (585, 1060, STATE_DOWN), (1060, 1190, STATE_UP)],
    # .104 is stopped until dr-warmup.yml starts it, and stopped again by
    # failback.yml at the end.
    DR: [(128, 330, STATE_DOWN), (330, 1000, STATE_UP), (1000, 1190, STATE_DOWN)],
}

# Where the state changes, and what it changes to.
TRANSITIONS = [
    (DR, 330, "RUNNING", "ansible/dr-warmup.yml starts the unit"),
    (PROD, 585, "STOPPED", "ansible/failover.yml stops the unit"),
    (DR, 1000, "STOPPED", "ansible/failback.yml stops the unit"),
    (PROD, 1060, "RUNNING", "ansible/failback.yml starts the unit"),
]


STYLE = {
    "call": ("m-ink", INK, None),
    "ret": ("m-grey", "#8A8A8A", "5 4"),
    "ok": ("m-green", GREEN, "5 4"),
    "bad": ("m-red", RED, "5 4"),
    "self": ("m-ink", INK, None),
}


SEQ_H = 1250
ACT_H = 1870


def state_line(x: float, y0: float, y1: float, state: str) -> str:
    """A lifeline segment, coloured by what the service is doing."""
    if state == STATE_UP:
        return (f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y1}" stroke="{GREEN}" '
                f'stroke-width="3.4" stroke-linecap="round"/>')
    return (f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y1}" stroke="{RED}" '
            f'stroke-width="3.4" stroke-dasharray="9 7" stroke-linecap="round"/>')


def swatch(x1: float, x2: float, y: float, state: str) -> str:
    """A short horizontal sample of a lifeline, for the legend."""
    if state == STATE_UP:
        return (f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{GREEN}" '
                f'stroke-width="3.4" stroke-linecap="round"/>')
    return (f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{RED}" '
            f'stroke-width="3.4" stroke-dasharray="9 7" stroke-linecap="round"/>')


def state_pill(x: float, y: float, label: str, color: str,
               centered: bool = False, solid: bool = True) -> str:
    w = 6.6 * len(label) + 20
    x0 = x - w / 2 if centered else x
    if solid:
        fill, tcolor, stroke = color, "#FFFFFF", "none"
    else:
        fill, tcolor, stroke = "#FFFFFF", color, color
    out = [f'<rect x="{x0}" y="{y - 11}" width="{w}" height="22" rx="10" '
           f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>']
    out.append(txt(x0 + w / 2, y + 4.5, label, 10.5, tcolor, weight="700"))
    return "".join(out)


def sequence_svg() -> str:
    W, H = 1700, SEQ_H
    xs = [x for x, _, _, _, _ in LIFELINES]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}">', markers(),
           f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>']

    # the legend, so the colours mean something
    out.append(swatch(70, 104, 24, STATE_UP))
    out.append(txt(116, 29, "the MCP is running", 12, INK, anchor="start"))
    out.append(swatch(272, 306, 24, STATE_DOWN))
    out.append(txt(318, 29, "the MCP is stopped", 12, INK, anchor="start"))
    out.append(txt(492, 29, "the colour of a lifeline IS the state of the "
                            "service on that host", 12, GREY, anchor="start",
                   italic=True))

    # lifeline heads
    badges: list[str] = []
    for idx, (x, title, sub, color, fill) in enumerate(LIFELINES):
        out.append(f'<rect x="{x - 132}" y="70" width="264" height="58" rx="8" '
                   f'fill="{fill}" stroke="{color}" stroke-width="1.6"/>')
        out.append(txt(x, 96, title, 14.5, color, weight="700"))
        out.append(txt(x, 116, sub, 11, GREY))
        if idx in LIFELINE_STATES:
            # the state badge at the top of the lifeline
            first = LIFELINE_STATES[idx][0][2]
            badges.append(state_pill(
                x, 148, "running" if first == STATE_UP else "stopped",
                GREEN if first == STATE_UP else RED, centered=True, solid=False))
        else:
            out.append(f'<line x1="{x}" y1="128" x2="{x}" y2="{H - 60}" '
                       f'stroke="#C8C8C8" stroke-width="1.4" stroke-dasharray="7 6"/>')

    # the state-coloured lifelines
    for idx, segments in LIFELINE_STATES.items():
        for y0, y1, state in segments:
            out.append(state_line(xs[idx], y0, y1, state))
    out.extend(badges)

    # the cutover marker
    out.append(f'<rect x="60" y="532" width="{W - 120}" height="30" rx="6" '
               f'fill="{PALE_AMBER}"/>')
    out.append(txt(W / 2, 553, "—  THE CUTOVER  —  the PROD unit stops, the DR "
                                 "unit is already running", 12, AMBER, weight="600"))

    # activation bars
    for y, src, dst, label, kind, act in MESSAGES:
        if act is None:
            continue
        idx, end = act
        out.append(bar(xs[idx], y - 8, min(end + 8, H - 60)))

    # messages
    for y, src, dst, label, kind, act in MESSAGES:
        marker, color, dash = STYLE[kind]
        if kind == "self":
            out.append(self_msg(xs[src], y, marker, color))
            out.append(txt(xs[src] + 50, y + 19, label, 11.5, color,
                           anchor="start", family=MONO))
            continue
        x1, x2 = xs[src], xs[dst]
        out.append(arrow(x1, y, x2, y, marker, color, dash=dash))
        mid = (x1 + x2) / 2
        out.append(txt(mid, y - 9, label, 12, color,
                       anchor="middle" if x2 > x1 else "middle"))

    # the state changes, marked on the lifeline they happen on
    for idx, y, label, why in TRANSITIONS:
        color = GREEN if label == "RUNNING" else RED
        out.append(state_pill(xs[idx] + 14, y, label, color))
        out.append(txt(xs[idx] + 14, y + 26, why, 10, GREY, anchor="start"))

    # the honest line
    out.append(f'<rect x="60" y="{H - 46}" width="{W - 120}" height="34" rx="8" '
               f'fill="{PALE}" stroke="{BLUE}" stroke-width="1.2"/>')
    out.append(txt(W / 2, H - 24,
                   "The service moves for real. The client's address is changed "
                   "by the caller — a floating IP would need root on the target, "
                   "and this demo never gives the deploy user root.",
                   11.5, INK))
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- #
#  2. the activity diagram — the pipeline as a flow
# --------------------------------------------------------------------------- #
MAIN = 850
FAIL_X = 330
FAIL2_X = 1370


def activity_svg() -> str:
    W, H = 1700, ACT_H
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}">', markers(),
           f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>']

    edges: list[str] = []
    nodes: list[str] = []
    labels: list[str] = []

    # -- the drill partition, behind everything
    out.append(band(150, 1095, 1400, 725, "THE FAILOVER DRILL", "#F7FAFD", LINE))

    # -- the two site lanes
    out.append(band(350, 908, 420, 132, "PROD · .105 · user rhai", PALE, BLUE,
                    "bottom"))
    out.append(band(930, 908, 420, 132, "DR · .104 · user dr", PALE_GREEN, GREEN,
                    "bottom"))

    # -- build & scan, one column
    nodes.append(terminal(MAIN, 58))
    nodes.append(action(MAIN, 130, "Checkout", "git clone git://127.0.0.1:9418/…"))
    nodes.append(action(MAIN, 205, "Fetch the MCP source",
                        "curl …/linux-mcp-server/archive/6d7ca1d1….tar.gz"))
    nodes.append(action(MAIN, 280, "Resolve the version",
                        "VERSION + date +%d%m%y → v1.0.DDMMYYNN"))
    nodes.append(action(MAIN, 355, "Build the image",
                        "podman build --file upstream/Containerfile"))
    nodes.append(decision(MAIN, 455, ["Image Is Compliant?", "the Aqua console's gate"]))
    nodes.append(action(MAIN, 560, "Trivy baseline scan",
                        "trivy image --scanners vuln --pkg-types library"))
    nodes.append(action(MAIN, 635, "Security remediation",
                        "pip install --no-deps --upgrade … ; drop pip"))
    nodes.append(decision(MAIN, 735, ["0 HIGH / CRITICAL library CVEs?",
                                      "on the image that will actually ship"]))
    nodes.append(action(MAIN, 840, "Export the artifact",
                        "podman save | gzip → tar.gz ; sha256sum"))

    # -- fork / join around the two sites
    nodes.append(bar_node(MAIN, 905, 240))
    nodes.append(action(560, 980, "Deploy to PROD",
                        "podman load → systemctl --user start", 380))
    nodes.append(action(1140, 980, "Deploy to DR",
                        "podman load → systemctl --user start", 380))
    nodes.append(bar_node(MAIN, 1070, 240))

    # -- the drill
    nodes.append(action(MAIN, 1148, "Verify PROD",
                        "mcp_verify.py → hostname + port 8095"))
    nodes.append(action(MAIN, 1223, "Warm the standby",
                        "ansible/dr-warmup.yml → start on .104"))
    nodes.append(decision(MAIN, 1323, ["DR ready?", "4 tools: system, cpu, memory, disk"]))
    nodes.append(action(MAIN, 1428, "THE CUTOVER",
                        "failover.yml → systemctl --user stop on .105", 400,
                        PALE_AMBER, AMBER, AMBER))
    nodes.append(action(MAIN, 1503, "Start DR",
                        "systemctl --user start rhel-mcp.service on .104"))
    nodes.append(action(MAIN, 1578, "Verify DR",
                        "mcp_verify.py → localhost.localdomain + port 8095"))
    nodes.append(action(MAIN, 1653, "Fail back",
                        "failback.yml → stop .104, start .105"))
    nodes.append(action(MAIN, 1728, "Verify PROD again",
                        "mcp_verify.py → server-gateway.example.com"))
    nodes.append(terminal(MAIN, 1788))

    # -- the two failure branches
    nodes.append(action(FAIL_X, 455, "FAIL the build", "the image may not ship",
                        340, PALE_RED, RED, RED))
    nodes.append(action(FAIL2_X, 735, "FAIL the build", "HIGH / CRITICAL remain",
                        340, PALE_RED, RED, RED))
    nodes.append(action(FAIL_X, 1323, "ABORT the drill",
                        "DR goes back down, PROD keeps serving", 350, PALE_RED, RED, RED))

    # -- edges
    def down(y_from: float, y_to: float, x: float = MAIN) -> None:
        edges.append(edge([(x, y_from), (x, y_to)]))

    down(73, 100)          # start -> checkout
    down(160, 175)
    down(235, 250)
    down(310, 325)
    down(385, 403)         # build -> aqua decision
    down(507, 530)         # aqua -> trivy baseline
    down(590, 605)
    down(665, 683)         # remediate -> trivy decision
    down(787, 810)         # trivy -> export
    down(870, 898)         # export -> fork
    edges.append(edge([(730, 905), (560, 950)]))    # fork -> PROD
    edges.append(edge([(970, 905), (1140, 950)]))   # fork -> DR
    edges.append(edge([(560, 1010), (730, 1070)]))  # PROD -> join
    edges.append(edge([(1140, 1010), (970, 1070)]))  # DR -> join
    down(1077, 1118)       # join -> verify prod
    down(1178, 1193)
    down(1253, 1271)       # warm -> decision
    down(1375, 1398)       # decision -> cutover
    down(1458, 1473)
    down(1533, 1548)
    down(1608, 1623)
    down(1683, 1698)
    down(1758, 1773)       # verify -> end

    # aqua "no"
    edges.append(edge([(635, 455), (510, 455)], "m-red", RED))
    labels.append(txt(572, 445, "no", 11.5, RED, weight="600", halo=True))
    labels.append(txt(MAIN + 14, 528, "yes", 11.5, GREEN, anchor="start",
                      weight="600", halo=True))

    # trivy "no"
    edges.append(edge([(1065, 735), (1200, 735)], "m-red", RED))
    labels.append(txt(1132, 725, "no", 11.5, RED, weight="600", halo=True))
    labels.append(txt(MAIN + 14, 806, "yes", 11.5, GREEN, anchor="start",
                      weight="600", halo=True))

    # drill gate "no"
    edges.append(edge([(635, 1323), (525, 1323)], "m-red", RED))
    labels.append(txt(580, 1313, "no", 11.5, RED, weight="600", halo=True))
    labels.append(txt(MAIN + 14, 1396, "yes", 11.5, GREEN, anchor="start",
                      weight="600", halo=True))

    # the same tarball, twice
    labels.append(txt(MAIN, 928, "the SAME tarball, the SAME sha256", 11.5, GREY,
                      weight="600", halo=True))

    out.extend(edges)
    out.extend(nodes)
    out.extend(labels)
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- #
#  build
# --------------------------------------------------------------------------- #
def page(title: str, sub: str, svg: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>{BASE_CSS}
  .sheet {{ padding: 34px 40px 30px; }}
  svg {{ display: block; }}
</style></head>
<body><div class="sheet">
  <h1>{esc(title)}</h1>
  <div class="sub">{esc(sub)}</div>
  <div class="rule"></div>
  {svg}
</div></body></html>
"""


def build() -> None:
    seq_html = HERE / "uml-sequence.html"
    act_html = HERE / "uml-activity.html"
    seq_png = HERE / "PROD-DR-Sequence-Diagram.png"
    act_png = HERE / "PROD-DR-Activity-Diagram.png"

    seq_svg = sequence_svg()
    act_svg = activity_svg()

    seq_html.write_text(page(
        "The failover drill — a sequence diagram",
        "Who talks to whom, and in what order. A green lifeline is a service "
        "that is running; a red one is a service that is stopped.",
        seq_svg), encoding="utf-8")
    act_html.write_text(page(
        "The pipeline — an activity diagram",
        "One column of build and scan, a fork to the two sites, then the drill "
        "with its two gates.",
        act_svg), encoding="utf-8")
    print(f"wrote {seq_html}")
    print(f"wrote {act_html}")

    if "--html" in sys.argv:
        return
    # The window has to be tall enough for the title block plus the SVG,
    # or Chrome crops the bottom of the diagram off.
    render(seq_html, seq_png, 1700, SEQ_H + 200)
    render(act_html, act_png, 1700, ACT_H + 200)


if __name__ == "__main__":
    build()
