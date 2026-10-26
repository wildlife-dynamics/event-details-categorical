"""Assemble a compiled-workflow run into one local dashboard page, laid out
per layout.json (10-column grid) inside the Ecoscope Desktop results page (sidebar
1/5, dashboard 4/5), for reviewing outputs outside Ecoscope. Open it at a laptop
window width (~1440 px) to see tiles at their real size.
When the run is grouped (e.g. by year), a dropdown switches views the way
the Ecoscope dashboard filter does.

  python dev/preview_dashboard.py [/tmp/event-details-categorical/output] [--no-open]

Writes <output>/dashboard.html and opens it.
"""

import html
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUTPUT = Path(args[0] if args else "/tmp/event-details-categorical/output")
# Ecoscope Desktop (ecoscope-web WorkflowResultsGridLayout / IframeWidget / StatWidget):
# rowHeight 28, margin 24, card bg #F9F9F9 + border + 6px radius, title bar p-4 with a bottom
# border (iframe widgets), empty p-2 footer under iframes, stat value text-3xl teal.
ROW_PX = 28
GAP_PX = 24

result = json.loads((OUTPUT / "result.json").read_text())
if result.get("error"):
    sys.exit(f"Workflow failed: {result['error']}")
dash = result["result"]
layout = {item["widget_id"]: item for item in json.loads((REPO / "layout.json").read_text())}


def compact(items: dict[int, dict]) -> dict[int, dict]:
    """As the app's grid (react-grid-layout, vertical): layout entries without a widget are
    dropped, then each widget, top to bottom, moves up until it touches another."""
    placed: dict[int, dict] = {}
    for i, it in sorted(items.items(), key=lambda kv: (kv[1]["y"], kv[1]["x"])):
        it = dict(it)
        while it["y"] > 0 and not any(
            it["x"] < p["x"] + p["w"] and p["x"] < it["x"] + it["w"] and p["y"] < it["y"] < p["y"] + p["h"] + 1
            for p in placed.values()
        ):
            it["y"] -= 1
        placed[i] = it
    return placed


def view_label(key: str) -> str:
    return ", ".join(str(v) for v in json.loads(key).values())


def cell_body(w: dict) -> str:
    if w["widget_type"] == "text":
        items = "".join(f"<li>{html.escape(line.lstrip('- '))}</li>" for line in (w["data"] or "").splitlines())
        return f'<ul class="text">{items}</ul>'
    if w["widget_type"] == "stat":
        return f'<p class="stat">{html.escape(str(w.get("data") or "–"))}</p>'
    if not w.get("data"):
        return '<p class="empty">No data for this selection</p>'
    return f'<div class="frame"><iframe src="{Path(w["data"]).name}"></iframe></div><div class="foot"></div>'


views = {}
for key, widgets in sorted(dash["views"].items(), key=lambda kv: view_label(kv[0])):
    cells = []
    if isinstance(widgets, dict):  # newer result.json: {"dashboard": [...]}
        widgets = widgets.get("dashboard", [])
    missing = [w["title"] for i, w in enumerate(widgets) if i not in layout]
    if missing:  # the app shows only widgets with a layout entry
        print(f"Not in layout.json, not shown: {missing}")
    shown = compact({i: layout[i] for i in range(len(widgets)) if i in layout})
    for i, w in enumerate(widgets):
        if i not in shown:
            continue
        pos = shown[i]
        style = f"grid-column:{pos['x'] + 1}/span {pos['w']};grid-row:{pos['y'] + 1}/span {pos['h']}"
        kind = "statcard" if w["widget_type"] == "stat" else "card"
        cells.append(f'<div class="{kind}" style="{style}"><h3>{html.escape(w["title"])}</h3>{cell_body(w)}</div>')
    views[view_label(key)] = "".join(cells)

labels = list(views)
options = "".join(f'<option value="{html.escape(v)}">{html.escape(v)}</option>' for v in labels)
meta = dash["metadata"]
# Ecoscope Desktop results page (WorkflowResults.tsx): page header, then px-12 / gap-4 with a w-1/5
# sidebar (View selector card when grouped, Context card = metadata) and the w-4/5 Dashboard | Files tabs
view_card = (
    f'<div class="side"><h4>View</h4><select id="view" onchange="show(this.value)">{options}</select></div>'
    if len(labels) > 1
    else ""
)
context = "".join(
    f"<dt>{html.escape(k.replace('_', ' ').capitalize())}</dt><dd>{html.escape(str(v))}</dd>"
    for k, v in meta.items()
    if k != "workflow_id"
)
page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(meta["title"])}</title>
<style>
body{{font-family:Roboto,Helvetica,Arial,sans-serif;margin:0;background:#fff;color:#222}}
.top{{padding:24px 48px 0}} .top h3{{margin:0;font-size:18px;font-weight:400;color:#4b5563}}
.top h2{{margin:2px 0 0;font-size:30px;font-weight:500;letter-spacing:-.02em;color:#1f2937}}
.page{{display:flex;gap:16px;padding:16px 48px 96px}}
.sidebar{{width:20%;display:flex;flex-direction:column;gap:16px}} .main{{width:80%;min-width:0}}
.side{{border:1px solid #dedede;border-radius:6px;padding:16px}} .side h4{{margin:0 0 12px;font-size:16px;font-weight:500;color:#374151}}
.side select{{width:100%;padding:6px 8px;font-size:14px}} dl{{margin:0}} dt{{font-size:14px;color:#6b7280;margin-top:16px}}
dt:first-child{{margin-top:0}} dd{{margin:0;font-size:14px;color:#111827;overflow-wrap:anywhere}}
.tabs{{display:flex;gap:40px;font-size:16px;color:#6b7280}} .tabs b{{color:#111827;border-bottom:2px solid #111827;padding-bottom:6px;font-weight:500}}
.grid{{display:grid;grid-template-columns:repeat(10,1fr);grid-auto-rows:{ROW_PX}px;gap:{GAP_PX}px;padding-top:20px}}
.card,.statcard{{background:#f9f9f9;border:1px solid #dedede;border-radius:6px;display:flex;flex-direction:column;overflow:hidden}}
.card h3,.statcard h3{{margin:0;padding:16px;font-size:16px;font-weight:400;color:#4b5563;line-height:24px}}
.card h3{{border-bottom:1px solid #dedede}}
.frame{{flex:1;position:relative}} .frame iframe{{position:absolute;inset:0;width:100%;height:100%;border:0}} .foot{{height:16px}}
.text{{margin:8px 16px;padding-left:18px;font-size:13px;line-height:1.5;overflow:auto}}
.empty{{margin:auto;color:#999;font-size:13px}} .stat{{margin:0 16px;font-size:30px;line-height:36px;color:#107284;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
</style></head><body>
<div class="top"><h3>Event Details - Categorical Field Workflow</h3><h2>{html.escape(meta["title"])}</h2></div>
<div class="page"><section class="sidebar">{view_card}<div class="side"><h4>Context</h4><dl>{context}</dl></div></section>
<section class="main"><div class="tabs"><b>Dashboard</b><span>Files</span></div><div class="grid" id="grid"></div></section></div>
<script>
const VIEWS = {json.dumps(views)};
function show(v) {{ document.getElementById("grid").innerHTML = VIEWS[v]; }}
show({json.dumps(labels[0])});
</script></body></html>"""

out = OUTPUT / "dashboard.html"
out.write_text(page)
print(f"Written: {out} ({len(labels)} view(s): {', '.join(labels)})")
if "--no-open" not in sys.argv:
    subprocess.run(["open", str(out)])
