# docs/ — what is in here

Everything in this folder is a **document or a picture built from the
pipeline**. Nothing here runs the pipeline; the pipeline lives in
`../Jenkinsfile`, the Ansible roles in `../ansible/`, and the by-hand
scripts in `../manual/`.

The folder is split by what each thing is *for*, so you can find one thing
without reading all of them.

---

## `guide/` — the written walkthroughs (DOCX)

Read these when you want to know **what a step does and what it must print**.
They are Word documents, so you can print them, annotate them, or hand them
to someone who will not be near a terminal.

| File | What it is |
|---|---|
| `PROD-DR-MCP-Pipeline-Guide.docx` | The full walkthrough — every manual step, how it works, what it must print, and what the MCP contributes to each one. |
| `PROD-DR-MCP-Pipeline-Cheatsheet.docx` | The fast one — one line per step (what it is for + the command), then a command sheet to present from. It also has a *"can I skip this step?"* table and the three runs you will actually do. |

Rebuild them:

```bash
python docs/guide/build_guide.py        # the guide
python docs/guide/build_cheatsheet.py   # the cheatsheet
```

Both embed the pictures from `../diagrams/`, so **render the diagrams first**
or the guide will stop with *"…is missing"*.

---

## `diagrams/pipeline/` — the pictures of the pipeline

| File | What it is |
|---|---|
| `PROD-DR-Pipeline-Diagram.png` | The pipeline: one image, built and scanned once, deployed to both sites. Every stage carries the command that runs it. |
| `PROD-DR-Drill-Diagram.png` | The failover drill, move by move — five moves, with the command behind each one. |
| `reference-redhat-pipeline.png` | The Red Hat reference design these two are modelled on — kept for comparison. |

> The **UAT → Manual Approval → PROD** design (the HKU ENGG Intranet
> pipeline) moved to its own repository, `MangoTim/pipeline-uat`, together
> with the pipeline that implements it.

| Builder | What it renders |
|---|---|
| `build_diagrams.py` | The first two pictures. |

```bash
python docs/diagrams/pipeline/build_diagrams.py   # pipeline + drill
```

Each builder also writes the **HTML** it rendered — that HTML is the source.
Edit it in a browser, print it to PDF, or change the builder and re-run.
`--html` writes the HTML without rendering.

---

## `diagrams/uml/` — the pictures drawn as UML

Same story, different drawing: these are formal models rather than
annotated pictures.

| File | What it is |
|---|---|
| `PROD-DR-Sequence-Diagram.png` | The drill as a sequence diagram — four lifelines (your client, Jenkins, the PROD MCP, the DR MCP). A lifeline is solid green while its MCP runs and dashed red while it is stopped. |
| `PROD-DR-Activity-Diagram.png` | The workflow as an activity diagram — build and scan in one column, a fork to the two sites, a join, then the drill with its two gates as decision diamonds. |

```bash
python docs/diagrams/uml/build_uml.py
```

There is no PlantUML on this machine, so both are drawn as SVG and
screenshotted through headless Chrome at 2×.

---

## How the pictures are made

Every picture in this folder comes from the same two steps:

1. A Python builder writes an **HTML** file next to itself.
2. Headless Chrome screenshots that HTML at **2× device scale**, and Pillow
   trims the empty band Chrome leaves at the bottom.

So the PNG is what goes on a slide, and the **HTML is what you edit**. Every
builder takes `--html` if you only want the HTML.

`build_diagrams.py` holds the shared house style (`BASE_CSS`, `COLORS`) and
the shared `render()`; the other builders import from it rather than
duplicating it.
