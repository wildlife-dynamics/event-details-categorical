"""Categorical event fields: which values were recorded, how often, when and where.

Not part of any compiled workflow: a prototype for a future
"Event Details - Categorical Field" workflow, the categorical counterpart of
ecoscope-platform-workflows-releases/event-details (which sums a numeric field).
Each top-level function is written so it can become a workflow task (inputs in,
output out, no hidden globals). See PLAN.md.

Steps:
  1. events of the selected event types in [SINCE, UNTIL), with event_details
  2. each event type's schema (v2 first, v1 fallback; ecoscope's _fetch_v2_schema /
     _normalize_v1_schema) -> field catalogue: kind (single / multi / yes_no / text /
     numeric ...), choice labels, parent field (v2 allOf if/then)
  3. selected fields -> one long table, one row per event x field x value. Multi-choice
     fields give one row per ticked value. Unknown and blank are their own values
  4. outputs 1-7 of the PRD

One event type per run, like the numeric Event Details workflow.

Outputs (.scripts/outputs/<connection>/<event_type>/):
  index.html                 dashboard: outputs 1-7, one block per event type
  data/events.parquet        events (cache, reused with --render-only)
  data/catalogue.csv         every field of every selected event type, with its kind
  data/values_long.csv       one row per event x field x value
  tables/summary.csv         output 7: event type, field, value, count, share, grid squares, reporters
  tables/crosstab_*.csv      output 5, one per pair
  tables/events_<type>.csv   output 7: one row per event, personal fields left out
  maps/*.html                output 6: points, grid (small grids + summary grid), small multiples

Run with download-attachments' compiled env:
  cd /Users/zak/Documents/w-dynamics/event-details_categorical_analysis
  ../download-attachments/ecoscope-workflows-event-photo-records-workflow/.pixi/envs/default/bin/python \\
    .scripts/categorical_analysis.py --connection wd [--event-type entry_alert_rep] [--render-only] [--no-open]
"""

import argparse
import html
import json
import math
import re
import subprocess
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import shapely

warnings.filterwarnings("ignore")

from ecoscope.io.earthranger import ERClientNotFound  # noqa: E402
from ecoscope.platform.connections import EarthRangerConnection  # noqa: E402
from ecoscope.platform.tasks.io._earthranger import (  # noqa: E402
    _fetch_v2_schema,
    _normalize_v1_schema,
)
from ecoscope.platform.tasks.results._map_utils import set_base_maps  # noqa: E402
from ecoscope.platform.tasks.results._pydeck import (  # noqa: E402
    LegendSegment,
    LegendStyle,
    LegendValue,
    PolygonLayerStyle,
    ScatterplotLayerStyle,
    TextLayerStyle,
    ViewState,
    create_polygon_layer_pydeck,
    create_scatterplot_layer,
    create_text_layer_pydeck,
    draw_map,
)

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / ".scripts" / "outputs"

# User settings per connection (in the workflow: the form). `fields` = categorical fields
# to summarise; `main` = drives tiles, map colours and small multiples; `crosstabs` =
# field pairs; `sunburst` = levels below the event type (fields of that type).
SETTINGS = {
    "wd": {
        "since": "2026-05-01T00:00:00Z",
        "until": "2026-09-01T00:00:00Z",
        "event_types": {
            "wildlife_sighting": {  # area grouper test: wd has spatial feature groups, naibungalower none
                "since": "2026-01-01T00:00:00Z",
                "until": "2026-10-20T00:00:00Z",
                "grouper": {"area": "ROIs"},
                "main": "Wildlife Species",
                "fields": ["Wildlife Species"],
                "crosstabs": [],
                "sunburst": ["Wildlife Species"],
            },
        },
    },
    # v2 forms with real dropdowns (PLAN.md section 4). Fields typed as they read on the form (phase 1).
    "naibungalower": {
        "since": "2025-01-01T00:00:00Z",
        "until": "2026-10-15T00:00:00Z",
        "event_types": {
            "wildlife_sighting": {  # started late Sep 2026: its own, shorter range (weekly trends)
                "since": "2026-09-20T00:00:00Z",
                "grouper": {"reported_by": True},
                "main": "Species",
                "fields": ["Species", "Sighting type"],
                "crosstabs": [("Species", "Sighting type")],
                "sunburst": ["Sighting type", "Species"],
            },
            "post_rep": {
                "natural_order": ["Water Status"],  # Full / 75% / 50% / 25% / Empty, as on the form
                "grouper": {"time": "quarter"},
                "main": "Water Status",
                "fields": ["Water Status", "Post", "Morning Call Up Conducted", "Evening Call Up Conducted",
                           "Technical Issues", "Watch Keeper Checklist"],
                "crosstabs": [("Post", "Water Status")],
                "sunburst": ["Post", "Water Status"],
            },
            "wildlife_sighting_rep_ranger": {
                "main": "Location",
                "fields": ["Location", "Conservancy",
                           "Actions Checklist"],
                "crosstabs": [("Location", "Conservancy")],
                "sunburst": ["Conservancy", "Location"],
            },
        },
    },
}

# Top N + Other (PLAN.md section 4). Values tied at the cut go to Other together (Ranked.head).
TOP_BAR = 10  # bar charts, cross-tabs: no colour per value, so the PRD's 10. Setting full_list: all values
TOP_BAR_MAX = 15  # ties at the 10th place can grow the list up to here; past it they all go to Other
TOP_COLOR = 8  # sunburst, stacked bars, points map: one colour each, and there are 8 safe colour slots
TOP_SMALL = 6  # small multiples, small grids: one map each, PRD's 6
MIN_CELL_EVENTS = 5  # grid squares with fewer events are drawn pale
STACK_DECIMALS = 4  # ~10 m: events closer than this count as the same spot
UNKNOWN_WORDS = {"unknown", "unk", "not known", "don't know", "dont know", "n/a"}
UNKNOWN, BLANK = "Unknown", "(blank)"
PERSONAL = re.compile(r"(^|_)(user|attribution|email|phone|reporter|observer|name)(_|$)|user_name|watch_?keeper|commander|team_(leader|members)|ranger", re.I)

# dataviz reference palette (validated), fixed order; grey for Unknown / blank and Other
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GREY_UNKNOWN, GREY_OTHER, GREY_FAINT = "#8f8d87", "#c9c7c0", "#b5b3ad"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]  # sequential blue
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


# --------------------------------------------------------------------------- data


def get_events(er, event_types: list[str], since: str, until: str) -> gpd.GeoDataFrame:
    """Events of the selected types, with event_details, located or not."""
    ets = er.get_event_types(include_inactive=True, api_version="both").drop_duplicates("value")
    ids = ets.loc[ets["value"].isin(event_types), "id"].tolist()
    ev = er.get_events(
        event_type=ids, since=since, until=until, include_details=True, drop_null_geometry=False
    )
    ev = ev.reset_index()
    display = dict(zip(ets["value"], ets["display"]))
    ev["event_type_display"] = ev["event_type"].map(display).fillna(ev["event_type"])
    ev["time"] = pd.to_datetime(ev["time"], utc=True, format="ISO8601")
    ev["reported_by_name"] = ev["reported_by"].map(lambda r: r.get("name") if isinstance(r, dict) else None)
    keep = ["id", "serial_number", "time", "event_category", "event_type", "event_type_display",
            "reported_by_name", "event_details", "geometry"]  # fmt: skip
    return gpd.GeoDataFrame(ev[keep], geometry="geometry", crs="EPSG:4326")


def clear_null_island(events: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Points within 1 degree of (0, 0) (open sea, Gulf of Guinea) are GPS placeholders, not
    locations: treat them as unlocated. Seen on naibungalower: 7 at exactly (0, 0), 7 more nearby."""
    pts = events.geometry
    null_island = pts.notna() & ~pts.is_empty & (pts.x.abs() < 1) & (pts.y.abs() < 1)
    events = events.copy()
    events.loc[null_island, "geometry"] = None
    return events


def get_event_schema(er, slug: str) -> tuple[str, dict, dict]:
    """(api version, canonical schema with enumNames, raw schema)."""
    try:
        with er._use_v2_api():
            raw = er._get(f"activity/eventtypes/{slug}/schema")
        return "v2", _fetch_v2_schema(er, slug), raw
    except ERClientNotFound:  # v1 form: listed in the catalogue, rejected by validate_fields
        raw = er._get(f"activity/events/schema/eventtype/{slug}")
        return "v1", _normalize_v1_schema(raw), raw


def classify_field(prop: dict) -> str:
    """single | multi | yes_no | text | numeric | date | url | subform | other."""
    items = prop.get("items") or {}
    if prop.get("enumNames") or prop.get("enum") or prop.get("anyOf"):
        return "single"
    if prop.get("type") == "array" and (items.get("enumNames") or items.get("anyOf") or items.get("enum")):
        return "multi"
    t = prop.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    if t == "boolean":
        return "yes_no"
    if t in ("number", "integer"):
        return "numeric"
    if t == "string":
        return {"date-time": "date", "date": "date", "uri": "url"}.get(prop.get("format"), "text")
    if t == "object" or (t == "array" and items.get("type") == "object"):
        return "subform"
    return "multi" if t == "array" else "other"


def v2_parents(raw: dict) -> dict[str, str]:
    """child field -> parent field, from v2 allOf if/then blocks (an answer opens a question)."""
    parents = {}
    for cond in (raw.get("json") or {}).get("allOf", []):
        parent = next(iter((cond.get("if") or {}).get("properties", {}) or {}), None)
        for child in (cond.get("then") or {}).get("properties", {}):
            if parent and child != parent:
                parents[child] = parent
    return parents


def get_field_catalogue(er, event_types: list[str]) -> pd.DataFrame:
    """One row per event type x field: title, kind, choice labels (in form order), parent."""
    rows = []
    for slug in event_types:
        version, schema, raw = get_event_schema(er, slug)
        parents = v2_parents(raw) if version == "v2" else {}
        for key, prop in schema["properties"].items():
            labels = prop.get("enumNames") or (prop.get("items") or {}).get("enumNames") or {}
            rows.append({
                "event_type": slug, "api": version, "field": key, "title": prop.get("title") or key,
                "kind": classify_field(prop), "choices": json.dumps(labels), "parent": parents.get(key),
            })  # fmt: skip
    return pd.DataFrame(rows)


CATEGORICAL_KINDS = {"single": "pick one", "multi": "pick several", "yes_no": "yes/no"}


def _name_key(name: str) -> str:
    return re.sub(r"[\s_]+", " ", str(name)).strip().casefold()


def resolve_field_names(catalogue: pd.DataFrame, event_type: str, cfg: dict) -> dict:
    """Phase 1: the user types each field as it reads on the form ("Water Status"). The field key
    ("water_status") works too. Case, spaces and underscores don't matter. Returns cfg with keys
    in place of names (main, fields, crosstabs, sunburst, natural_order)."""
    cat = catalogue[catalogue["event_type"] == event_type]
    lookup: dict[str, set[str]] = {}
    for r in cat.itertuples():
        for n in (r.title, r.field):
            lookup.setdefault(_name_key(n), set()).add(r.field)
    dropdowns = ", ".join(f'"{r.title}"' for r in cat[cat["kind"].isin(CATEGORICAL_KINDS)].itertuples()) or "none"

    def key(name: str) -> str:
        found = lookup.get(_name_key(name), set())
        if not found:
            raise ValueError(f'"{name}" is not a field on this form. Dropdown fields: {dropdowns}')
        if len(found) > 1:  # two questions with the same label: the key tells them apart
            raise ValueError(f'"{name}" matches more than one field ({", ".join(sorted(found))}); type the field key instead.')
        return next(iter(found))

    return {
        **cfg,
        "main": key(cfg["main"]),
        "fields": list(dict.fromkeys(key(f) for f in cfg["fields"])),
        "crosstabs": [(key(a), key(b)) for a, b in cfg.get("crosstabs", [])],
        "sunburst": [key(f) for f in cfg.get("sunburst", [])],
        "natural_order": [key(f) for f in cfg.get("natural_order", [])],
    }


def validate_fields(catalogue: pd.DataFrame, event_type: str, main: str, fields: list[str]) -> None:
    """Phase 1 (PLAN.md section 3): the user types field keys, so check them before the run.
    v2 form only; each field must exist and be a dropdown: pick one / pick several / yes-no. Free
    text is never categorical, not even standardised integration text (decided 2026-10-20). The
    main field can't be pick several (it colours the map points)."""
    cat = catalogue[catalogue["event_type"] == event_type]
    if (cat["api"] != "v2").any() or cat.empty:
        raise ValueError(f"{event_type} is not a v2 form. This workflow only supports v2 forms.")
    allowed = cat[cat["kind"].isin(CATEGORICAL_KINDS)]
    options = ", ".join(f'"{r.title}" ({CATEGORICAL_KINDS[r.kind]})' for r in allowed.itertuples()) or "none"
    kinds, titles = dict(zip(cat["field"], cat["kind"])), dict(zip(cat["field"], cat["title"]))
    for f in dict.fromkeys([main, *fields]):
        if f not in kinds:
            raise ValueError(f'"{f}" is not a field on this form. Dropdown fields: {options}')
        if kinds[f] not in CATEGORICAL_KINDS:
            raise ValueError(f'"{titles[f]}" is a {kinds[f]} field, not a dropdown. Dropdown fields: {options}')
    if kinds[main] == "multi":
        raise ValueError(f'Main field "{titles[main]}" is pick several; choose a pick-one or yes/no field.')


def _norm(v) -> tuple[str, str]:
    """(value label, status) for one answer."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip()):
        return BLANK, "blank"
    if isinstance(v, bool):
        return ("Yes" if v else "No"), "filled"
    s = str(v).strip()
    if s.lower() in UNKNOWN_WORDS:
        return UNKNOWN, "unknown"
    return s, "filled"


def categorical_long(events: gpd.GeoDataFrame, catalogue: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """One row per event x selected field x value. Multi-choice: one row per ticked value
    (an event with nothing ticked gets one (blank) row). Choice codes -> form labels."""
    cat = catalogue.set_index(["event_type", "field"])
    rows = []
    for ev in events.itertuples():
        cfg = settings["event_types"].get(ev.event_type)
        if not cfg:
            continue
        details = ev.event_details if isinstance(ev.event_details, dict) else {}
        for field in cfg["fields"]:
            meta = cat.loc[(ev.event_type, field)]
            labels = json.loads(meta["choices"])
            raw = details.get(field)
            answers = raw if isinstance(raw, list) else [raw]
            for a in answers or [None]:
                value, status = _norm(labels.get(a, a) if isinstance(a, str) else a)
                rows.append((ev.id, ev.event_type, field, meta["title"], meta["kind"], value, status))
    return pd.DataFrame(rows, columns=["id", "event_type", "field", "field_title", "kind", "value", "status"])


# --------------------------------------------------------------------------- groupers

TIME_LABELS = {"month": ("M", "%b %Y"), "quarter": ("Q", None), "year": ("Y", "%Y")}


def get_areas(er, group_name: str) -> gpd.GeoDataFrame:
    """Features of an EarthRanger spatial feature group (name, geometry), for the area grouper."""
    from ecoscope.platform.schemas import SpatialFeaturesGroup

    sfg = SpatialFeaturesGroup(**er.get_spatial_features_group(
        spatial_features_group_name=group_name, spatial_features_group_id=None, with_group_data=True))  # fmt: skip
    f = sfg.features
    name_col = next((c for c in ("name", "title", "display_name") if c in f.columns), None)
    names = f[name_col] if name_col else pd.Series([f"Area {i + 1}" for i in range(len(f))], index=f.index)
    return gpd.GeoDataFrame({"area": names.astype(str).values}, geometry=f.geometry.values, crs=f.crs).to_crs("EPSG:4326")


def assign_groups(events: gpd.GeoDataFrame, grouper: dict, areas: gpd.GeoDataFrame | None = None) -> pd.Series:
    """One view label per event, in display order (categorical). grouper: {"time": "month" |
    "quarter" | "year"}, {"reported_by": true} or {"area": "<spatial feature group>"}. Events
    can fall in more than one area: the first one wins (same as ecoscope's spatial index)."""
    if "time" in grouper:
        freq, fmt = TIME_LABELS[grouper["time"]]
        p = events["time"].dt.tz_localize(None).dt.to_period(freq)
        labels = p.map(lambda x: f"{x.year} Q{x.quarter}" if freq == "Q" else x.start_time.strftime(fmt))
        order = [lab for _, lab in sorted(set(zip(p, labels)))]
    elif grouper.get("reported_by"):
        labels = events["reported_by_name"].fillna("(not recorded)")
        order = sorted(set(labels), key=lambda v: (v == "(not recorded)", v))
    elif "area" in grouper:
        j = gpd.sjoin(events[["id", "geometry"]], areas, how="left", predicate="within").drop_duplicates("id")
        labels = j.set_index("id").reindex(events["id"])["area"].fillna("(outside the areas)").set_axis(events.index)
        order = sorted(set(labels), key=lambda v: (v.startswith("("), v))
    else:
        raise ValueError(f"Unknown grouper {grouper}")
    return pd.Series(pd.Categorical(labels, categories=order), index=events.index)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "group"


# --------------------------------------------------------------------------- helpers


class Ranked(list):
    """Values by event count, highest first (ties listed by name), Unknown / blank left out."""

    def __init__(self, counts: pd.Series):
        super().__init__(sorted(counts.index, key=lambda v: (-counts[v], v)))
        self.counts = counts

    def head(self, n: int | None, limit: int | None = None) -> list[str]:
        """Top n, never splitting values tied at the cut by name. Tied values are all kept
        (n grows), unless that passes `limit` (the 8 colour slots): then they all go to Other.
        e.g. 3 species tied at 5 events for places 5-7 of a top 6: all three kept (7 named);
        2 species tied at 4 for the 8th colour: both go to Other (7 named). n=None: all."""
        if n is None or len(self) <= n:
            return list(self)
        cut = self.counts[self[n - 1]]
        if self.counts[self[n]] != cut:
            return list(self[:n])
        with_ties = [v for v in self if self.counts[v] >= cut]
        if limit is None or len(with_ties) <= limit:
            return with_ties
        without = [v for v in self if self.counts[v] > cut]
        return without or list(self[:n])  # everything tied: fall back to the first n


def rank_values(long_f: pd.DataFrame) -> Ranked:
    return Ranked(long_f[long_f["status"] == "filled"].groupby("value")["id"].nunique())


def rank_column(col: pd.Series) -> Ranked:
    """Same, for a column with one value per event (the sunburst rings)."""
    c = col[~col.isin([UNKNOWN, BLANK])].value_counts()
    return Ranked(c)


def natural_sort(values, natural_order: list[str]) -> list[str]:
    """Values in form order (natural_order = choice labels as on the form), then Other, then
    Unknown / blank. For fields like age class or tank level, where count order would scramble them."""
    pos = {v: i for i, v in enumerate(natural_order)}
    return sorted(values, key=lambda x: (x in (UNKNOWN, BLANK), is_other(x), x == BLANK, pos.get(x, len(pos)), x))


def natural_orders(catalogue_t: pd.DataFrame, cfg: dict) -> dict[str, list[str]]:
    """field -> labels in form order, for the fields in the `natural_order` setting. Yes/no fields
    always read Yes, No."""
    out = {r.field: ["Yes", "No"] for r in catalogue_t.itertuples() if r.kind == "yes_no"}
    for r in catalogue_t[catalogue_t["field"].isin(cfg.get("natural_order", []))].itertuples():
        out[r.field] = list(json.loads(r.choices).values())
    return out


def other_members(values: pd.Series, keep: list[str], limit: int = 25) -> str:
    """Hover text listing what Other holds, with counts: '<br>Gerenuk (4)<br>Olive Baboon (3)…'."""
    rest = values[~values.isin([*keep, UNKNOWN, BLANK])].value_counts()
    rows = [f"{html.escape(str(v))} ({n:,})" for v, n in rest.head(limit).items()]
    return "<br>" + "<br>".join(rows) + ("<br>…" if len(rest) > limit else "")


OTHER_RE = re.compile(r"^Other \(\d+ values?\)$")


def is_other(label) -> bool:
    """The lumped 'Other (k values)' group, not a form option that is itself called 'Other'."""
    return isinstance(label, str) and bool(OTHER_RE.match(label))


def lump(values: pd.Series, keep: list[str]) -> pd.Series:
    """Values outside `keep` (and not Unknown / blank) -> 'Other (k values)'."""
    others = sorted(set(values) - set(keep) - {UNKNOWN, BLANK})
    if not others:
        return values
    label = f"Other ({len(others)} value{'s' if len(others) > 1 else ''})"
    return values.where(values.isin([*keep, UNKNOWN, BLANK]), label)


def rgba(hex_color: str) -> tuple[int, int, int, int]:
    """'#rrggbb' or '#rrggbbaa' -> (r, g, b, a): pydeck layers take tuples, a string is read as a column name."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4)) + (int(h[6:8], 16) if len(h) == 8 else 255,)


def color_for(value: str, top: list[str]) -> str:
    if value in (UNKNOWN, BLANK):
        return GREY_UNKNOWN
    slots = top.head(TOP_COLOR, len(SLOTS)) if isinstance(top, Ranked) else top[:TOP_COLOR]
    if value in slots:
        return SLOTS[slots.index(value)]
    return GREY_OTHER


def time_period(since: str, until: str) -> tuple[str, str]:
    """Trend period from the date range: weekly up to 2 months, monthly up to 3 years, else quarterly."""
    days = (pd.Timestamp(until) - pd.Timestamp(since)).days
    if days <= 62:
        return "W-MON", "week"
    return ("MS", "month") if days <= 3 * 366 else ("QS", "quarter")


def nice_cell_km(gdf_m: gpd.GeoDataFrame, target: int = 25) -> float:
    """Grid square size: about `target` squares across the longer side, rounded to 1/2/5 x 10^n km."""
    x0, y0, x1, y1 = gdf_m.total_bounds
    raw = max(x1 - x0, y1 - y0, 1000) / target / 1000
    exp = 10 ** math.floor(math.log10(raw))
    return next(m * exp for m in (1, 2, 5, 10) if m * exp >= raw)


def grid_index(located: gpd.GeoDataFrame, cell_km: float) -> tuple[pd.Series, str]:
    """Grid square id per located event, in a local UTM CRS."""
    crs = located.estimate_utm_crs()
    pts = located.to_crs(crs)
    size = cell_km * 1000
    gx = np.floor(pts.geometry.x / size).astype(int)
    gy = np.floor(pts.geometry.y / size).astype(int)
    return gx.astype(str) + "_" + gy.astype(str), crs


def grid_polygons(cell_ids: pd.Index, cell_km: float, crs) -> gpd.GeoSeries:
    size = cell_km * 1000
    boxes = []
    for cid in cell_ids:
        gx, gy = map(int, cid.split("_"))
        boxes.append(shapely.box(gx * size, gy * size, (gx + 1) * size, (gy + 1) * size))
    return gpd.GeoSeries(boxes, index=cell_ids, crs=crs).to_crs("EPSG:4326")


def plot_html(fig: go.Figure, height: int) -> str:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=36, b=8), font=dict(family=FONT, size=12, color="#0b0b0b"),
        paper_bgcolor="#fcfcfb", plot_bgcolor="#fcfcfb", hoverlabel=dict(font_family=FONT),
    )  # fmt: skip
    fig.update_xaxes(gridcolor="#ebe9e4", zerolinecolor="#d6d4ce")
    fig.update_yaxes(gridcolor="#ebe9e4", zerolinecolor="#d6d4ce")
    return fig.to_html(full_html=False, include_plotlyjs=False, default_width="100%",
                       config={"displaylogo": False, "responsive": True})


# --------------------------------------------------------------------------- output 1: tiles


def sparkline_svg(y: list[float], w: int = 120, h: int = 28, color: str = "#2a78d6") -> str:
    if len(y) < 2:
        return ""
    lo, hi = min(y), max(y)
    span = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(y) - 1):.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}" for i, v in enumerate(y))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polyline points="{pts}" fill="none" '
            f'stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>')  # fmt: skip


def tiles_for_type(events_t: pd.DataFrame, long_t: pd.DataFrame, main: str, main_title: str) -> str:
    """Events (weekly sparkline) | distinct values (weekly + running total) | % Unknown or blank."""
    weeks = pd.date_range(events_t["time"].min().floor("D"), events_t["time"].max().ceil("D"), freq="W-MON")
    wk = events_t["time"].dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
    n_week = wk.value_counts().reindex(weeks.tz_localize(None), fill_value=0)
    m = long_t[long_t["field"] == main].merge(events_t[["id", "time"]], on="id")
    filled = m[m["status"] == "filled"].sort_values("time")
    m_wk = filled["time"].dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
    distinct_week = filled.groupby(m_wk)["value"].nunique().reindex(weeks.tz_localize(None), fill_value=0)
    first_seen = filled.drop_duplicates("value")
    first_wk = first_seen["time"].dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
    accum = first_wk.value_counts().reindex(weeks.tz_localize(None), fill_value=0).cumsum()
    per_event = m.groupby("id")["status"].agg(lambda s: "filled" if (s == "filled").any() else s.iloc[0])
    n_missing = (per_event != "filled").sum()
    pct = 100 * n_missing / max(len(per_event), 1)
    return f"""
    <div class="tile"><div class="lbl">Events</div><div class="val">{len(events_t):,}</div>
      {sparkline_svg(n_week.tolist())}<div class="sub">per week</div></div>
    <div class="tile"><div class="lbl">Distinct values · {html.escape(main_title)}</div>
      <div class="val">{filled["value"].nunique():,}</div>
      <div class="pair"><div>{sparkline_svg(distinct_week.tolist(), 90)}<div class="sub">per week</div></div>
      <div>{sparkline_svg(accum.tolist(), 90, color="#1baf7a")}<div class="sub">running total</div></div></div></div>
    <div class="tile"><div class="lbl">% Unknown or blank · {html.escape(main_title)}</div>
      <div class="val">{pct:.0f}%</div><div class="sub">{n_missing:,} of {len(per_event):,} events</div></div>"""


# --------------------------------------------------------------------------- output 2: sunburst


def sunburst_wide(events: pd.DataFrame, long: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """One row per event: event_category, event_type_display, main (main-field value) and
    L0, L1, ... (the type's sunburst fields). Multi-choice fields are left out."""
    wide = events[["id", "event_category", "event_type", "event_type_display"]].copy()
    for et, cfg in settings["event_types"].items():
        rows = wide["event_type"] == et
        single = long[(long["event_type"] == et) & (long["kind"] != "multi")]
        piv = single.drop_duplicates(["id", "field"]).pivot(index="id", columns="field", values="value")
        for col, f in [("main", cfg["main"]), *[(f"L{i}", f) for i, f in enumerate(cfg["sunburst"])]]:
            wide.loc[rows, col] = wide.loc[rows, "id"].map(piv[f]) if f in piv else BLANK
    return wide


def draw_sunburst(wide: pd.DataFrame, levels: list[str], color_level: int, color_rank: "Ranked | None" = None) -> str:
    """Rings = `levels` (columns of wide). Top TOP_COLOR per parent + 'Other (k values)',
    whose hover lists what it holds. Ring `color_level` takes the colour slots (by overall
    rank); deeper rings inherit, outer grey = Unknown / blank / Other. Click to zoom."""
    col0 = wide[levels[color_level]].fillna(BLANK)
    ranked = (color_rank or rank_column(col0)).head(TOP_COLOR, len(SLOTS))  # colours: whole run, not this view
    ids, labels, parents, values, hover, colors = [], [], [], [], [], []

    def add(df, depth, parent_id, inherited):
        if depth >= len(levels):
            return
        col = df[levels[depth]].fillna(BLANK)
        keep = rank_column(col).head(TOP_COLOR, len(SLOTS))
        lumped = lump(col, keep)
        for v, part in df.groupby(lumped, sort=False):
            node = f"{parent_id}/{v}"
            listing = other_members(col.loc[part.index], keep) if is_other(v) else ""
            if v in (UNKNOWN, BLANK):
                c = GREY_UNKNOWN
            elif is_other(v):
                c = GREY_OTHER
            elif depth < color_level:
                c = "#e6e4de" if depth == 0 else "#d6d4ce"
            elif depth == color_level:
                c = SLOTS[ranked.index(v)] if v in ranked else GREY_OTHER
            else:
                c = inherited
            ids.append(node)
            labels.append(v)
            parents.append(parent_id)
            values.append(len(part))
            hover.append(f"<b>{html.escape(v)}</b><br>{len(part):,} events{listing}")
            colors.append(c)
            add(part, depth + 1, node, c)

    add(wide, 0, "", None)
    fig = go.Figure(go.Sunburst(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="total", hovertext=hover,
        hoverinfo="text", textinfo="label+percent parent", insidetextorientation="radial",
        marker=dict(colors=colors, line=dict(color="#fcfcfb", width=2)),
    ))  # fmt: skip
    return plot_html(fig, 560)


# --------------------------------------------------------------------------- output 3: bars


def draw_value_bars(long_f: pd.DataFrame, n_events: int, title: str, natural_order: list[str] | None,
                    top_n: int | None = TOP_BAR, ranked: "Ranked | None" = None) -> str:
    """Horizontal bars, top TOP_BAR + Other + Unknown/blank. Single: count and %;
    multi: counts only (bars can add up to more than the number of events)."""
    multi = (long_f["kind"] == "multi").any()
    rk = ranked or rank_values(long_f)
    top = rk.head(top_n, TOP_BAR_MAX)
    v = lump(long_f["value"], top)
    tied = ""  # head() fell back to the first n: too many values share the cut-off count
    if top and len(top) < len(rk) and rk.counts.get(top[-1]) == rk.counts.get(rk[len(top)]):
        n_tied = int((rk.counts == rk.counts[top[-1]]).sum())
        tied = (f"<p class='note'>{n_tied} values have {rk.counts[top[-1]]} event{'s' if rk.counts[top[-1]] > 1 else ''} each; "
                f"only the first {sum(rk.counts[t] == rk.counts[top[-1]] for t in top)} by name are shown, the rest are in Other.</p>")
    per_event = long_f.drop_duplicates(["id", "value"])["value"]
    counts = long_f.assign(v=v).groupby("v")["id"].nunique()
    order = natural_sort(counts.index, natural_order) if natural_order else sorted(
        counts.index, key=lambda x: (x in (UNKNOWN, BLANK), is_other(x), -counts[x], x)
    )
    order += [x for x in counts.index if x not in order]
    counts = counts.reindex(order)
    colors = [GREY_UNKNOWN if x in (UNKNOWN, BLANK) else (GREY_OTHER if is_other(x) else SLOTS[0]) for x in order]
    text = [f"{c:,}" if multi else f"{c:,} · {100 * c / n_events:.0f}%" for c in counts]
    fig = go.Figure(go.Bar(
        y=order, x=counts.values, orientation="h", marker=dict(color=colors, cornerradius=4),
        text=text, textposition="outside", cliponaxis=False, hoverinfo="text",
        hovertext=[f"<b>{html.escape(x)}</b>: {c:,} events" + (other_members(per_event, top) if is_other(x) else "")
                   for x, c in zip(order, counts)],
    ))  # fmt: skip
    head = f"{n_events:,} events" + (f" · {len(long_f[long_f['status'] == 'filled']):,} values ticked" if multi else "")
    fig.update_layout(title=dict(text=f"<b>{html.escape(title)}</b>  <span style='color:#52514e'>{head}</span>", font_size=13),
                      yaxis=dict(autorange="reversed"), bargap=0.25,
                      xaxis=dict(showgrid=True, range=[0, counts.max() * 1.25]))  # fmt: skip
    note = "<p class='note'>Multi-choice: one event can have several values, so bars can add up to more than the number of events.</p>" if multi else ""
    return plot_html(fig, 60 + 26 * len(order)) + note + tied


# --------------------------------------------------------------------------- output 4: over time


def draw_over_time(long_f: pd.DataFrame, events_t: pd.DataFrame, freq: str, period: str, title: str,
                   ranked: "Ranked | None" = None, natural_order: list[str] | None = None) -> str:
    """100% stacked bars per period (counts on hover; button to switch to counts).
    Multi-choice: one line per value."""
    multi = (long_f["kind"] == "multi").any()
    top = ranked or rank_values(long_f)
    m = long_f.merge(events_t[["id", "time"]], on="id")
    m["v"] = lump(m["value"], top.head(TOP_COLOR, len(SLOTS)))
    m["p"] = m["time"].dt.tz_localize(None).dt.to_period({"W-MON": "W-SUN", "MS": "M", "QS": "Q"}[freq]).dt.start_time
    tab = m.groupby(["p", "v"])["id"].nunique().unstack(fill_value=0)
    order = [v for v in top.head(TOP_COLOR, len(SLOTS)) if v in tab] + [c for c in tab if is_other(c)] + [
        c for c in (UNKNOWN, BLANK) if c in tab
    ]
    if natural_order:  # stack in form order (e.g. Full / 75% / 50% / 25% / Empty), not by count
        order = natural_sort(order, natural_order)
    if multi:  # (blank) = nothing ticked; as a line it dwarfs the values, the bar chart still shows it
        order = [v for v in order if v != BLANK]
    tab = tab[order]
    share = tab.div(tab.sum(axis=1), axis=0) * 100
    fig = go.Figure()
    for v in order:
        c = color_for(v, top)
        if multi:
            fig.add_trace(go.Scatter(x=tab.index, y=tab[v], name=v, mode="lines+markers", line=dict(color=c, width=2),
                                     marker=dict(size=8), hovertemplate=f"{html.escape(v)}: %{{y:,}}<extra></extra>"))  # fmt: skip
        else:
            members = ""
            if is_other(v):
                rest = m[m["v"] == v].drop_duplicates(["id", "value"]).groupby(["p", "value"]).size()
                members = [("<br>" + "<br>".join(f"{html.escape(str(val))} ({n})" for val, n in rest.loc[p].sort_values(ascending=False).head(15).items()))
                           if p in rest.index.get_level_values(0) else "" for p in tab.index]
            fig.add_trace(go.Bar(x=tab.index, y=share[v], name=v, marker=dict(color=c, line=dict(color="#fcfcfb", width=2)),
                                 customdata=np.column_stack([tab[v], members or [""] * len(tab)]),
                                 hovertemplate=f"{html.escape(v)}: %{{customdata[0]:,}} events (%{{y:.0f}}%)%{{customdata[1]}}<extra></extra>"))  # fmt: skip
    if not multi:
        fig.update_layout(barmode="stack", yaxis=dict(title="% of events", ticksuffix="%", range=[0, 100]),
            updatemenus=[dict(type="buttons", direction="right", x=1, y=1.14, xanchor="right", showactive=True, buttons=[
                dict(label="100%", method="update", args=[{"y": [share[v] for v in order]}, {"yaxis.title.text": "% of events", "yaxis.ticksuffix": "%", "yaxis.range": [0, 100]}]),
                dict(label="Counts", method="update", args=[{"y": [tab[v] for v in order]}, {"yaxis.title.text": "Events", "yaxis.ticksuffix": "", "yaxis.autorange": True}]),
            ])])  # fmt: skip
    else:
        fig.update_layout(yaxis=dict(title="Events"))
    fig.update_layout(title=dict(text=f"<b>{html.escape(title)}</b> per {period}", font_size=13), bargap=0.2,
                      legend=dict(orientation="h", y=-0.15), xaxis=dict(tickformat="%b %Y" if period != "week" else "%d %b"))  # fmt: skip
    return plot_html(fig, 420)


# --------------------------------------------------------------------------- output 5: cross-tab


def crosstab(long_t: pd.DataFrame, a: str, b: str, top_n: int | None = TOP_BAR, ranks: dict | None = None,
             natural: dict | None = None) -> pd.DataFrame:
    """Events by value of field a (rows) x field b (cols), top_n + Other each (None: all).
    tab.attrs['other'] = what each axis's Other holds, for the note under the heatmap."""
    fa, fb = long_t[long_t["field"] == a], long_t[long_t["field"] == b]
    rank_a = (ranks or {}).get(a) or rank_values(fa)
    rank_b = (ranks or {}).get(b) or rank_values(fb)
    keep_a, keep_b = rank_a.head(top_n, TOP_BAR_MAX), rank_b.head(top_n, TOP_BAR_MAX)
    other = {k: f.drop_duplicates(["id", "value"])["value"].pipe(lambda s: s[~s.isin([*keep, UNKNOWN, BLANK])].value_counts())
             for k, f, keep in (("a", fa, keep_a), ("b", fb, keep_b))}  # fmt: skip
    fa = fa.assign(v=lump(fa["value"], keep_a))
    fb = fb.assign(v=lump(fb["value"], keep_b))
    j = fa[["id", "v"]].merge(fb[["id", "v"]], on="id", suffixes=("_a", "_b"))
    tab = j.groupby(["v_a", "v_b"])["id"].nunique().unstack(fill_value=0)

    def order(idx, ranked, nat):
        out = [x for x in ranked if x in idx] + [x for x in idx if is_other(x)] + [x for x in (UNKNOWN, BLANK) if x in idx]
        return natural_sort(out, nat) if nat else out

    natural = natural or {}
    tab = tab.loc[order(tab.index, rank_a, natural.get(a)), order(tab.columns, rank_b, natural.get(b))]
    tab.attrs["other"] = other
    return tab


def draw_crosstab(tab: pd.DataFrame, title_a: str, title_b: str) -> str:
    rowpct = tab.div(tab.sum(axis=1), axis=0) * 100
    scale = [[i / (len(SEQ) - 1), c] for i, c in enumerate(SEQ)]
    fig = go.Figure(go.Heatmap(
        z=tab.values, x=list(tab.columns), y=list(tab.index), colorscale=scale, xgap=2, ygap=2,
        text=tab.values, texttemplate="%{text}", customdata=rowpct.round(0).values, showscale=False,
        hovertemplate=f"{html.escape(title_a)}: %{{y}}<br>{html.escape(title_b)}: %{{x}}<br>%{{z:,}} events (%{{customdata:.0f}}% of row)<extra></extra>",
    ))  # fmt: skip
    fig.update_layout(
        title=dict(text=f"<b>{html.escape(title_a)}</b> × <b>{html.escape(title_b)}</b>", font_size=13),
        yaxis=dict(autorange="reversed", title=title_a), xaxis=dict(title=title_b, side="bottom", tickangle=-30),
        margin=dict(t=64), updatemenus=[dict(type="buttons", direction="right", x=1, y=1, yanchor="bottom", pad=dict(b=28), xanchor="right", buttons=[
            dict(label="Counts", method="restyle", args=[{"z": [tab.values], "text": [tab.values], "texttemplate": "%{text}"}]),
            dict(label="Row %", method="restyle", args=[{"z": [rowpct.values], "text": [rowpct.round(0).values], "texttemplate": "%{text}%"}]),
        ])],
    )  # fmt: skip
    notes = [f"<b>Other</b> ({t}): " + ", ".join(f"{html.escape(str(v))} ({n})" for v, n in tab.attrs["other"][k].items())
             for k, t in (("a", title_a), ("b", title_b)) if len(tab.attrs.get("other", {}).get(k, []))]  # fmt: skip
    return plot_html(fig, 140 + 34 * len(tab)) + "".join(f"<p class='note'>{n}</p>" for n in notes)


# --------------------------------------------------------------------------- output 6: maps


def _draw(layers, view_state: ViewState | None = None) -> str:
    return draw_map(
        geo_layers=[layer for layer in layers if layer is not None],
        tile_layers=set_base_maps(base_maps=None), static=False, title=None, max_zoom=17,
        legend_style=LegendStyle(placement="bottom-right"), output_type="html", view_state=view_state,
    )  # fmt: skip


def shared_view(g: gpd.GeoDataFrame, width_px: int = 340, height_px: int = 300) -> ViewState:
    """One view for every small map (all located events), so the maps line up and compare."""
    x0, y0, x1, y1 = g.total_bounds
    lat = (y0 + y1) / 2
    span_x = max(x1 - x0, 0.01) * 1.4
    span_y = max(y1 - y0, 0.01) * 1.4 / math.cos(math.radians(lat))
    zoom = min(math.log2(360 * width_px / (span_x * 512)), math.log2(360 * height_px / (span_y * 512)))  # deck.gl: 512 px world at zoom 0
    return ViewState(longitude=(x0 + x1) / 2, latitude=lat, zoom=round(zoom, 2), pitch=0, bearing=0)


def located_main(events_t: gpd.GeoDataFrame, long_t: pd.DataFrame, main: str) -> gpd.GeoDataFrame:
    """Located events with their main-field value (multi: one row per ticked value), colour, tooltip."""
    m = long_t[long_t["field"] == main][["id", "value"]]
    g = events_t[events_t.geometry.notna() & ~events_t.geometry.is_empty].merge(m, on="id")
    g = gpd.GeoDataFrame(g, geometry="geometry", crs="EPSG:4326")
    g["Time"] = g["time"].dt.strftime("%Y-%m-%d %H:%M")
    g["Event type"] = g["event_type_display"]
    g["Event"] = "#" + g["serial_number"].astype(str)
    return g


def legend_for(values: list[str], top: list[str], title: str) -> LegendSegment:
    return LegendSegment(title=title, values=[LegendValue(label=v, color=color_for(v, top)) for v in values])


def draw_points_map(g: gpd.GeoDataFrame, top: list[str], title: str, field_cols: list[str]) -> str:
    """Points coloured by the main field, sized by events at the same spot, count on larger points."""
    g = g.copy()
    g["v"] = lump(g["value"], top.head(TOP_COLOR, len(SLOTS)))
    g["color"] = g["v"].map(lambda v: rgba(color_for(v, top)))
    key = pd.DataFrame({"x": g.geometry.x.round(STACK_DECIMALS), "y": g.geometry.y.round(STACK_DECIMALS), "v": g["v"]})
    g["Events here"] = key.groupby(["x", "y", "v"])["x"].transform("size").to_numpy()
    g = g[~key.duplicated().to_numpy()].sort_values("Events here", ascending=False)
    g["radius"] = 4 + 2.2 * np.sqrt(g["Events here"])
    g["label"] = np.where(g["Events here"] >= 10, g["Events here"].astype(str), "")
    legend_vals = list(dict.fromkeys([v for v in top.head(TOP_COLOR, len(SLOTS)) if v in set(g["v"])] + sorted(set(g["v"]) - set(top.head(TOP_COLOR, len(SLOTS))))))
    pts = create_scatterplot_layer(
        geodataframe=g[["geometry", "color", "radius", "label", "Events here", "Time", "Event type", "Event", *field_cols]],
        layer_style=ScatterplotLayerStyle(get_fill_color="color", get_radius="radius", radius_units="pixels",
                                          stroked=True, get_line_color=(255, 255, 255, 255), line_width_min_pixels=1, opacity=0.9),
        legend=legend_for(legend_vals, top, title), zoom=True,
        tooltip_columns=["Event", "Event type", "Time", "Events here", *field_cols],
    )  # fmt: skip
    lbl = g[g["label"] != ""]
    text = create_text_layer_pydeck(
        geodataframe=lbl[["geometry", "label"]], layer_style=TextLayerStyle(
            get_text="label", get_color=(255, 255, 255, 255), get_size=11, font_family=FONT, pickable=False,
            font_weight="bold"),
    ) if len(lbl) else None  # fmt: skip
    return _draw([pts, text])


def draw_grid_maps(g: gpd.GeoDataFrame, top: list[str], cell_km: float, title: str) -> tuple[list[tuple[str, str]], str]:
    """Small grids, one per top value: squares shaded by that value's events (pale under
    MIN_CELL_EVENTS). Plus the summary grid: each square in its most common value's colour,
    darker = more dominant, labelled 'share, n'."""
    view = shared_view(g)
    cells, crs = grid_index(g, cell_km)
    g = g.assign(cell=cells.values)
    all_counts = g.drop_duplicates(["id"]).groupby("cell").size()
    polys = grid_polygons(all_counts.index, cell_km, crs)
    out = []
    for v in top.head(TOP_SMALL, len(SLOTS)):
        c = g[g["value"] == v].drop_duplicates("id").groupby("cell").size()
        if c.empty:
            continue
        gdf = gpd.GeoDataFrame({"Events": c, "All events": all_counts.reindex(c.index)}, geometry=polys.reindex(c.index))
        bins = np.minimum((np.log1p(gdf["Events"]) / np.log1p(c.max()) * (len(SEQ) - 1)).round().astype(int), len(SEQ) - 1)
        gdf["color"] = [SEQ[b] for b in bins]
        gdf["color"] = [rgba(col if n >= MIN_CELL_EVENTS else "#e6e4de") for col, n in zip(gdf["color"], gdf["Events"])]
        layer = create_polygon_layer_pydeck(
            geodataframe=gdf.reset_index(drop=True), layer_style=PolygonLayerStyle(get_fill_color="color", opacity=0.75,
                stroked=True, get_line_color=(255, 255, 255, 255), get_line_width=1),
            tooltip_columns=["Events", "All events"],
        )  # fmt: skip
        out.append((f"{v} (max {int(c.max())} per square)", _draw([layer], view)))
    # summary grid
    single = g.drop_duplicates(["id"])
    by = single.groupby(["cell", "value"]).size().rename("n").reset_index().sort_values("n", ascending=False)
    dom = by.drop_duplicates("cell").set_index("cell")
    dom["Events"] = all_counts.reindex(dom.index)
    dom["Share"] = (100 * dom["n"] / dom["Events"]).round(0)
    gdf = gpd.GeoDataFrame(dom, geometry=polys.reindex(dom.index)).rename(columns={"value": "Most common"})

    def shade(row):
        base = color_for(row["Most common"], top)
        if row["Events"] < MIN_CELL_EVENTS:
            return base + "40"
        return base + format(int(90 + 165 * row["Share"] / 100), "02x")

    gdf["color"] = [rgba(shade(r)) for _, r in gdf.iterrows()]
    gdf["label"] = [f"{int(s)}%, n={n}" if n >= MIN_CELL_EVENTS else "" for s, n in zip(gdf["Share"], gdf["Events"])]
    vals = [v for v in top.head(TOP_COLOR, len(SLOTS)) if v in set(gdf["Most common"])]
    layer = create_polygon_layer_pydeck(
        geodataframe=gdf.reset_index(drop=True)[["geometry", "color", "Most common", "Share", "Events"]],
        layer_style=PolygonLayerStyle(get_fill_color="color", stroked=True, get_line_color=(255, 255, 255, 255), get_line_width=1),
        legend=legend_for(vals, top, title), zoom=True, tooltip_columns=["Most common", "Share", "Events"],
    )  # fmt: skip
    lab = gdf[gdf["label"] != ""].copy()
    lab["geometry"] = lab.geometry.representative_point()
    text = create_text_layer_pydeck(
        geodataframe=lab.reset_index(drop=True)[["geometry", "label"]],
        layer_style=TextLayerStyle(get_text="label", get_color=(11, 11, 11, 255), get_size=10, font_family=FONT, pickable=False),
    ) if len(lab) else None  # fmt: skip
    return out, _draw([layer, text])


def draw_small_multiples(g: gpd.GeoDataFrame, top: list[str]) -> list[tuple[str, str]]:
    """One map per top value + Other; every other event as a faint grey dot."""
    out = []
    small = top.head(TOP_SMALL, len(SLOTS))
    rest_values = [v for v in top if v not in small]
    other = f"Other ({len(rest_values)} value{'s' if len(rest_values) > 1 else ''})"  # never a form option's own name
    groups = small + ([other] if rest_values else [])
    base = g.drop_duplicates("id")[["geometry", "id"]]
    view = shared_view(g)
    for v in groups:
        sel = g[g["value"].isin(rest_values)] if v == other else g[g["value"] == v]
        rest = base[~base["id"].isin(sel["id"])]
        color = GREY_OTHER if v == other else color_for(v, top)
        bg = create_scatterplot_layer(
            geodataframe=rest[["geometry"]], layer_style=ScatterplotLayerStyle(get_fill_color=rgba(GREY_FAINT), get_radius=3,
                radius_units="pixels", opacity=0.35, pickable=False),
        )  # fmt: skip
        fg = create_scatterplot_layer(
            geodataframe=sel[["geometry", "value", "Time", "Event"]],
            layer_style=ScatterplotLayerStyle(get_fill_color=rgba(color), get_radius=5, radius_units="pixels", stroked=True,
                                              get_line_color=(255, 255, 255, 255), line_width_min_pixels=1),
            tooltip_columns=["Event", "value", "Time"],
        )  # fmt: skip
        out.append((f"{v} ({sel['id'].nunique():,})", _draw([bg, fg], view)))
    return out


# --------------------------------------------------------------------------- output 7: tables


def summary_table(long: pd.DataFrame, events: gpd.GeoDataFrame, cells: pd.Series) -> pd.DataFrame:
    """Every value of every selected field: count, share (blank for multi-choice),
    distinct grid squares and distinct reporters."""
    m = long.merge(events[["id", "event_type_display", "reported_by_name"]], on="id")
    m["cell"] = m["id"].map(cells)
    n_type = events.groupby("event_type")["id"].nunique()
    t = m.groupby(["event_type", "event_type_display", "field_title", "kind", "value"]).agg(
        count=("id", "nunique"), grid_squares=("cell", "nunique"), reporters=("reported_by_name", "nunique")
    ).reset_index()
    t["share"] = np.where(t["kind"] == "multi", np.nan, (100 * t["count"] / t["event_type"].map(n_type)).round(1))
    t = t.sort_values(["event_type_display", "field_title", "count"], ascending=[True, True, False])
    return t.rename(columns={"event_type_display": "Event type", "field_title": "Field", "value": "Value",
                             "count": "Count", "share": "Share %", "grid_squares": "Grid squares",
                             "reporters": "Reporters"})[["Event type", "Field", "Value", "Count", "Share %",
                                                         "Grid squares", "Reporters"]]  # fmt: skip


def event_level_table(events_t: gpd.GeoDataFrame, catalogue_t: pd.DataFrame) -> pd.DataFrame:
    """One row per event: time, location, type, reporter left out, every form field by title
    except personal ones (user names, attribution, contact details)."""
    titles = dict(zip(catalogue_t["field"], catalogue_t["title"]))
    choices = {r.field: json.loads(r.choices) for r in catalogue_t.itertuples()}
    rows = []
    for ev in events_t.itertuples():
        d = ev.event_details if isinstance(ev.event_details, dict) else {}
        row = {"Serial": ev.serial_number, "Time": ev.time.strftime("%Y-%m-%d %H:%M"), "Event type": ev.event_type_display,
               "Latitude": ev.geometry.y if ev.geometry is not None and not ev.geometry.is_empty else None,
               "Longitude": ev.geometry.x if ev.geometry is not None and not ev.geometry.is_empty else None}  # fmt: skip
        for k, v in d.items():
            if PERSONAL.search(k) or k == "updates":
                continue
            lab = choices.get(k, {})
            v = [lab.get(x, x) if isinstance(x, str) else json.dumps(x) for x in v] if isinstance(v, list) else lab.get(v, v) if isinstance(v, str) else v
            row[titles.get(k, k)] = "; ".join(map(str, v)) if isinstance(v, list) else v
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- page

CSS = """
:root { --ink:#0b0b0b; --muted:#52514e; --line:#e6e4de; --surface:#fcfcfb; --bg:#f4f3f0; }
* { box-sizing: border-box; }
body { margin:0; font-family: %s; color:var(--ink); background:var(--bg); }
header { background:#fff; border-bottom:1px solid var(--line); padding:16px 24px; position:sticky; top:0; z-index:5; }
header h1 { font-size:18px; margin:0 0 4px; }
.views { float:right; font-size:13px; color:var(--muted); } .views select { font:inherit; font-size:13px; padding:3px 6px; margin-left:6px; } header .meta { color:var(--muted); font-size:13px; }
nav a { font-size:13px; margin-right:14px; color:#256abf; text-decoration:none; }
main { padding:16px 24px 60px; max-width:1500px; margin:0 auto; }
section { margin:28px 0; } section > h2 { font-size:16px; margin:0 0 4px; } section > p.q { color:var(--muted); margin:0 0 12px; font-size:13px; }
.card { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:12px; margin-bottom:12px; }
.card h3 { font-size:14px; margin:0 0 8px; } .card h3 span { color:var(--muted); font-weight:400; }
.grid2 { display:grid; grid-template-columns: repeat(auto-fit, minmax(520px, 1fr)); gap:12px; }
.grid2 > * { min-width:0; } .card { overflow:hidden; }
.tiles { display:grid; grid-template-columns: 160px repeat(3, minmax(180px, 1fr)); gap:10px; align-items:stretch; margin-bottom:10px; }
.tiles .et { font-weight:600; font-size:13px; align-self:center; }
.tile { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:10px 12px; }
.tile .lbl { font-size:12px; color:var(--muted); } .tile .val { font-size:26px; font-weight:650; margin:2px 0 4px; }
.tile .sub { font-size:11px; color:var(--muted); } .tile .pair { display:flex; gap:16px; }
.maps { display:grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap:10px; }
.maps figure { margin:0; } .maps figcaption { font-size:12px; font-weight:600; margin:0 0 4px; }
iframe { width:100%%; border:1px solid var(--line); border-radius:8px; background:#fff; }
.note { font-size:12px; color:var(--muted); margin:4px 0 0; }
table.t { border-collapse:collapse; font-size:12px; width:100%%; } table.t th, table.t td { padding:4px 8px; border-bottom:1px solid var(--line); text-align:left; }
table.t td.n { text-align:right; font-variant-numeric: tabular-nums; } table.t th { position:sticky; top:0; background:var(--surface); }
.scroll { max-height:520px; overflow:auto; }
details summary { cursor:pointer; font-size:13px; color:#256abf; margin:6px 0; }
.toggle button { font:inherit; font-size:12px; border:1px solid var(--line); background:#fff; border-radius:6px; padding:3px 10px; cursor:pointer; }
.toggle button.on { background:#0b0b0b; color:#fff; border-color:#0b0b0b; }
""" % FONT


def iframe(path: str, h: int = 420) -> str:
    return f'<iframe src="{path}" style="height:{h}px" loading="lazy"></iframe>'


def table_html(df: pd.DataFrame, max_rows: int = 400) -> str:
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = []
    for r in df.head(max_rows).itertuples(index=False):
        tds = []
        for v in r:
            num = isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)
            txt = "" if (num and pd.isna(v)) else (f"{v:,.1f}" if isinstance(v, float) else f"{v:,}" if num else html.escape(str(v)))
            tds.append(f'<td class="{"n" if num else ""}">{txt}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f'<div class="scroll"><table class="t"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def run_context(events: gpd.GeoDataFrame, long: pd.DataFrame, catalogue: pd.DataFrame, cfg: dict) -> dict:
    """What every view of a run shares, so a grouper doesn't change it from view to view:
    value ranking (so a value keeps its colour, and Other holds the same values, in every view),
    natural order, and the grid square size."""
    located = events[events.geometry.notna() & ~events.geometry.is_empty]
    wide = sunburst_wide(events, long, {"event_types": {events["event_type"].iloc[0]: cfg}})
    return {
        "ranks": {f: rank_values(long[long["field"] == f]) for f in cfg["fields"]},
        "sun_rank": rank_column(wide["L0"].fillna(BLANK)) if "L0" in wide else None,
        "natural": natural_orders(catalogue, cfg),
        "cell_km": nice_cell_km(located.to_crs(located.estimate_utm_crs())) if len(located) else 1,
    }


def render(conn: str, settings: dict, events: gpd.GeoDataFrame, catalogue: pd.DataFrame, long: pd.DataFrame, out: Path,
           ctx: dict | None = None, nav: str = "", view: str = "") -> Path:
    """One dashboard page. ctx: from run_context() (whole run); nav: the view selector html;
    view: this view's label, shown in the title."""
    for d in ("maps", "tables"):
        (out / d).mkdir(parents=True, exist_ok=True)
    et0 = next(iter(settings["event_types"]))
    ctx = ctx or run_context(events, long, catalogue[catalogue["event_type"] == et0], settings["event_types"][et0])
    ranks, natural = ctx["ranks"], ctx["natural"]
    freq, period = time_period(settings["since"], settings["until"])
    cat = catalogue.set_index(["event_type", "field"])
    title = lambda et, f: cat.loc[(et, f), "title"]  # noqa: E731
    types = [et for et in settings["event_types"] if (events["event_type"] == et).any()]
    disp = events.drop_duplicates("event_type").set_index("event_type")["event_type_display"]

    # one grid for the whole run, so grid-square counts in the table match the grid maps
    located = events[events.geometry.notna() & ~events.geometry.is_empty]
    cell_km = ctx["cell_km"]
    if len(located):
        cells, _ = grid_index(located, cell_km)
        cells = pd.Series(cells.values, index=located["id"].values)
    else:
        cells = pd.Series(dtype=str)

    s1, s3, s4, s5, s6, s7 = [], [], [], [], [], []
    summary = summary_table(long, events, cells)
    summary.to_csv(out / "tables" / "summary.csv", index=False)
    for et in types:
        cfg = settings["event_types"][et]
        ev_t, long_t = events[events["event_type"] == et], long[long["event_type"] == et]
        main = cfg["main"]
        top_n = None if cfg.get("full_list") else TOP_BAR  # setting: bar charts / cross-tabs as the full list
        s1.append(f'<div class="tiles"><div class="et">{html.escape(disp[et])}</div>{tiles_for_type(ev_t, long_t, main, title(et, main))}</div>')
        bars = "".join(f'<div class="card">{draw_value_bars(long_t[long_t["field"] == f], len(ev_t), title(et, f), natural.get(f), top_n, ranks.get(f))}</div>' for f in cfg["fields"])
        s3.append(f'<h3 class="ett">{html.escape(disp[et])}</h3><div class="grid2">{bars}</div>')
        times = "".join(f'<div class="card">{draw_over_time(long_t[long_t["field"] == f], ev_t, freq, period, title(et, f), ranks.get(f), natural.get(f))}</div>' for f in cfg["fields"])
        s4.append(f'<h3 class="ett">{html.escape(disp[et])}</h3><div class="grid2">{times}</div>')
        for a, b in cfg["crosstabs"]:
            tab = crosstab(long_t, a, b, top_n, ranks, natural)
            tab.to_csv(out / "tables" / f"crosstab_{et}_{a}_x_{b}.csv")
            s5.append(f'<div class="card"><h3>{html.escape(disp[et])}</h3>{draw_crosstab(tab, title(et, a), title(et, b))}</div>')
        event_level_table(ev_t, catalogue[catalogue["event_type"] == et]).to_csv(out / "tables" / f"events_{et}.csv", index=False)

        g = located_main(ev_t, long_t, main)
        if g.empty:
            s6.append(f'<div class="card"><h3>{html.escape(disp[et])}</h3><p class="note">No located events.</p></div>')
            continue
        top = ranks.get(main) or rank_values(long_t[long_t["field"] == main])
        piv = long_t[long_t["kind"] != "multi"].drop_duplicates(["id", "field"]).pivot(index="id", columns="field", values="value")
        tip = [title(et, f) for f in cfg["fields"] if f in piv]
        for f in cfg["fields"]:
            if f in piv:
                g[title(et, f)] = g["id"].map(piv[f])
        multi_main = cat.loc[(et, main), "kind"] == "multi"
        blocks = []
        if not multi_main:
            (out / "maps" / f"{et}_points.html").write_text(draw_points_map(g, top, title(et, main), tip))
            blocks.append(f'<div class="card"><h3>Points map <span>· coloured by {html.escape(title(et, main))}, sized by events at the same spot</span></h3>{iframe(f"maps/{et}_points.html", 560)}</div>')
        grids, summary_grid = draw_grid_maps(g, top, cell_km, title(et, main))
        for i, (v, h) in enumerate(grids):
            (out / "maps" / f"{et}_grid_{i}.html").write_text(h)
        (out / "maps" / f"{et}_grid_summary.html").write_text(summary_grid)
        blocks.append(
            f'<div class="card"><h3>Grid map <span>· {cell_km:g} km squares, one grid per value; pale = fewer than {MIN_CELL_EVENTS} events</span></h3>'
            f'<div class="maps">{"".join(f"<figure><figcaption>{html.escape(v)}</figcaption>{iframe(f"maps/{et}_grid_{i}.html", 300)}</figure>" for i, (v, _) in enumerate(grids))}</div>'
            f'<details><summary>Option: one summary grid (most common value per square)</summary>{iframe(f"maps/{et}_grid_summary.html", 520)}</details></div>'
        )  # fmt: skip
        sm = draw_small_multiples(g, top)
        for i, (v, h) in enumerate(sm):
            (out / "maps" / f"{et}_small_{i}.html").write_text(h)
        blocks.append(
            f'<div class="card"><h3>Small multiples <span>· one map per {html.escape(title(et, main))}, others in grey</span></h3>'
            f'<div class="maps">{"".join(f"<figure><figcaption>{html.escape(v)}</figcaption>{iframe(f"maps/{et}_small_{i}.html", 300)}</figure>" for i, (v, _) in enumerate(sm))}</div></div>'
        )  # fmt: skip
        s6.append(f'<h3 class="ett">{html.escape(disp[et])}</h3>' + "".join(blocks))

    wide = sunburst_wide(events[events["event_type"].isin(types)], long, settings)
    sun_types = []
    for et in types:
        cfg = settings["event_types"][et]
        levels = [f"L{i}" for i in range(len(cfg["sunburst"]))]
        sun_types.append(f'<div class="card"><h3>{html.escape(disp[et])} <span>· {" → ".join(html.escape(title(et, f)) for f in cfg["sunburst"])}</span></h3>'
                         f'{draw_sunburst(wide[wide["event_type"] == et], levels, color_level=0, color_rank=ctx.get("sun_rank"))}</div>')  # fmt: skip

    xt_links = "".join(f'<li><a href="tables/{p.name}">{p.name}</a></li>' for p in sorted((out / "tables").glob("crosstab_*.csv")))
    ev_links = "".join(f'<li><a href="tables/{p.name}">{p.name}</a></li>' for p in sorted((out / "tables").glob("events_*.csv")))
    n_types = ", ".join(f"{html.escape(disp[et])} ({(events['event_type'] == et).sum():,})" for et in types)
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Categorical Event Fields · {html.escape(", ".join(disp[t] for t in types))}</title><script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script><style>{CSS}</style></head><body>
<header>{nav}<h1>Categorical event fields · {html.escape(", ".join(disp[t] for t in types))}{f" · {html.escape(view)}" if view else ""} <span style="font-weight:400;color:#52514e">· {html.escape(conn)}</span></h1>
<div class="meta">{settings["since"][:10]} → {settings["until"][:10]} · {n_types} · {len(events) - len(located):,} without a location (left off the maps) · trends per {period} · grid {cell_km:g} km</div>
<nav><a href="#o1">1 Summary</a><a href="#o2">2 Sunburst</a><a href="#o3">3 Bars</a><a href="#o4">4 Over time</a><a href="#o5">5 Cross-tabs</a><a href="#o6">6 Maps</a><a href="#o7">7 Tables</a></nav></header>
<main>
<section id="o1"><h2>1 · Summary values</h2><p class="q">How many events, how many different values, and how much is missing? (main field per event type)</p>{"".join(s1)}</section>
<section id="o2"><h2>2 · Sunburst</h2><p class="q">How do the events break down, level by level? Top {TOP_COLOR} per parent + Other (hover lists them). Click a slice to zoom.</p>
<div class="grid2">{"".join(sun_types)}</div></section>
<section id="o3"><h2>3 · Values per field</h2><p class="q">For each field, how many events have each value, and what share of all events is that? Top {TOP_BAR} + Other.</p>{"".join(s3)}</section>
<section id="o4"><h2>4 · Over time</h2><p class="q">How does the share of each value change from {period} to {period}? 100% stacked by default (counts on hover, or switch to Counts).</p>{"".join(s4)}</section>
<section id="o5"><h2>5 · Cross-tabs</h2><p class="q">How often does each value of one field occur with each value of another? Counts, or row %.</p><div class="grid2">{"".join(s5)}</div></section>
<section id="o6"><h2>6 · Maps</h2><p class="q">Where was each value recorded?</p>{"".join(s6)}</section>
<section id="o7"><h2>7 · Tables and CSV downloads</h2><p class="q">The exact numbers behind the charts. <a href="tables/summary.csv">summary.csv</a></p>
<div class="card">{table_html(summary)}</div>
<div class="card"><h3>Cross-tabs</h3><ul>{xt_links}</ul><h3>Event-level (personal fields left out)</h3><ul>{ev_links}</ul></div></section>
</main>
<script>/* charts drawn before their neighbours existed were laid out too wide: re-fit them */
document.addEventListener("DOMContentLoaded", () => document.querySelectorAll(".plotly-graph-div").forEach(d => Plotly.Plots.resize(d)));</script>
</body></html>"""
    (out / "index.html").write_text(page)
    return out / "index.html"


def render_views(conn: str, settings: dict, events: gpd.GeoDataFrame, catalogue: pd.DataFrame, long: pd.DataFrame,
                 out: Path, ctx: dict, groups: pd.Series, grouper: dict) -> Path:
    """Grouper: an "All events" page (index.html) plus one page per group (views/<slug>/), each
    with a selector to switch view, as the platform dashboard's view switcher does. Ranking,
    colours, Other and grid size come from the whole run (ctx), so the views compare."""
    kind = next(iter(grouper))
    noun = {"time": grouper.get("time", ""), "reported_by": "reporter", "area": "area"}[kind]
    labels = [lab for lab in groups.cat.categories if (groups == lab).any()]
    pages = [("All events", "index.html")] + [(lab, f"views/{slug(lab)}/index.html") for lab in labels]

    def nav(here: str, depth: int) -> str:
        up = "../" * depth
        opts = "".join(f'<option value="{up}{path}"{" selected" if lab == here else ""}>{html.escape(lab)} '
                       f'({len(events) if path == "index.html" else int((groups == lab).sum()):,})</option>'
                       for lab, path in pages)  # fmt: skip
        return f'<div class="views">View by {html.escape(noun)}<select onchange="location.href=this.value">{opts}</select></div>'

    index = render(conn, settings, events, catalogue, long, out, ctx, nav("All events", 0))
    for lab in labels:
        sel = events[(groups == lab).to_numpy()]
        sub = settings
        if kind == "time":  # trend period from the view's own range (a month view: weekly)
            sub = {**settings, "since": sel["time"].min().isoformat(), "until": sel["time"].max().isoformat()}
        render(conn, sub, sel, catalogue, long[long["id"].isin(sel["id"])], out / "views" / slug(lab), ctx,
               nav(lab, 2), f"{noun.capitalize()}: {lab}")
    return index


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--connection", default="wd")
    ap.add_argument("--event-type", help="one event type per run, as in the numeric Event Details workflow (default: each preset in SETTINGS, one run each)")
    ap.add_argument("--render-only", action="store_true", help="reuse data/ from the last run, no ER calls")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    presets = SETTINGS[a.connection]
    er = None if a.render_only else EarthRangerConnection.from_named_connection(a.connection).get_client()
    for et in [a.event_type] if a.event_type else list(presets["event_types"]):
        cfg = presets["event_types"][et]
        settings = {**presets, **{k: cfg[k] for k in ("since", "until") if k in cfg}, "event_types": {et: cfg}}
        out = OUT / a.connection / et
        data = out / "data"
        data.mkdir(parents=True, exist_ok=True)
        if a.render_only:
            events = pd.read_pickle(data / "events.pkl")
            catalogue = pd.read_csv(data / "catalogue.csv")
        else:
            events = get_events(er, [et], settings["since"], settings["until"])
            catalogue = get_field_catalogue(er, [et])
            events.to_pickle(data / "events.pkl")
            catalogue.to_csv(data / "catalogue.csv", index=False)
        events = clear_null_island(events)
        print(f"{et}: {len(events):,} events, {len(catalogue)} fields in the form")
        cfg = resolve_field_names(catalogue, et, settings["event_types"][et])  # "Water Status" -> water_status
        settings = {**settings, "event_types": {et: cfg}}
        validate_fields(catalogue, et, cfg["main"], cfg["fields"])
        long = categorical_long(events, catalogue, settings)
        long.to_csv(data / "values_long.csv", index=False)
        ctx = run_context(events, long, catalogue, cfg)
        grouper = cfg.get("grouper")
        if not grouper:
            index = render(a.connection, settings, events, catalogue, long, out, ctx)
        else:
            areas = None
            if "area" in grouper:
                if a.render_only:
                    areas = pd.read_pickle(data / "areas.pkl")
                else:
                    areas = get_areas(er, grouper["area"])
                    areas.to_pickle(data / "areas.pkl")
            index = render_views(a.connection, settings, events, catalogue, long, out, ctx,
                                 assign_groups(events, grouper, areas), grouper)
        print(f"wrote {index}")
        if not a.no_open:
            subprocess.run(["open", str(index)])


if __name__ == "__main__":
    main()
