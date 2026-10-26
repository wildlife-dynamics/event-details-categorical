"""Survey EarthRanger sites for categorical event fields, and check what
EarthRangerEnumResolver (`event_type_schema_choice_prop`) would offer for each
event type.

Not part of any compiled workflow: exploration for the future
"Event Details - Categorical Field" workflow (see PLAN.md).

For each connection:
  1. events in [SINCE, UNTIL) without details -> counts per event type
  2. each event type's schema (v2 first, v1 fallback), via ecoscope's
     _fetch_v2_schema / _normalize_v1_schema (same as process_events_details)
  3. every field classified with classify_field() (single / multi / yes-no /
     text / numeric / other)
  4. what the resolver would return, replicating
     ecoscope-server er_enum_resolver.fetch_and_build_event_type_schema_enum:
       - the event type must have >= 1 numeric field, else "No schema found"
       - v2 only, top-level "anyOf" only (no multi-select, no v1, no booleans)

Outputs (.scripts/outputs/explore/):
  survey_fields.csv        one row per connection / event type / field
  survey_event_types.csv   one row per connection / event type, with counts

Run with download-attachments' compiled env:
  cd /Users/zak/Documents/w-dynamics/event-details_categorical_analysis
  ../download-attachments/ecoscope-workflows-event-photo-records-workflow/.pixi/envs/default/bin/python \\
    .scripts/explore_categorical.py [--connection wd ...] [--since 2025-10-01]
"""

import argparse
import json
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

from ecoscope.io.earthranger import ERClientNotFound  # noqa: E402
from ecoscope.platform.connections import EarthRangerConnection  # noqa: E402
from ecoscope.platform.tasks.io._earthranger import (  # noqa: E402
    _fetch_v2_schema,
    _normalize_v1_schema,
)

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / ".scripts" / "outputs" / "explore"

CONNECTIONS = ["wd", "mep", "naibungalower", "olokeri", "rubeho", "icf", "belize", "apn", "curacao", "galapagos"]
SINCE = "2025-10-01T00:00:00Z"
UNTIL = "2026-10-14T00:00:00Z"


def get_event_schema(er, slug: str) -> tuple[str, dict, dict]:
    """(api version, canonical schema with enumNames, raw schema)."""
    try:
        with er._use_v2_api():
            raw = er._get(f"activity/eventtypes/{slug}/schema")
        return "v2", _fetch_v2_schema(er, slug), raw
    except ERClientNotFound:
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
        if prop.get("format") in ("date-time", "date"):
            return "date"
        if prop.get("format") == "uri":
            return "url"
        return "text"
    if t == "object" or (t == "array" and items.get("type") == "object"):
        return "subform"
    if t == "array":
        return "multi"  # v1 checkboxes (fetch_event_type_schema_csv.apply_v1_widget_hints)
    return "other"


def resolver_choice_props(version: str, raw: dict) -> tuple[bool, list[str]]:
    """What EarthRangerEnumResolver's event_type_schema_choice_prop returns.

    Returns (resolves, field names). resolves=False means the resolver raises
    "No schema found" (event type has no numeric field) and the form shows
    "Failed to fetch ...".
    """
    props = (raw.get("json") if version == "v2" else raw.get("schema", {})).get("properties", {})
    has_numeric = any(p.get("type") == "number" for p in props.values())
    if not has_numeric:
        return False, []
    if version != "v2":
        return True, []
    return True, [k for k, p in props.items() if "anyOf" in p]


def survey_connection(name: str, since: str, until: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    er = EarthRangerConnection.from_named_connection(name).get_client()
    ev = er.get_events(since=since, until=until, include_details=True, drop_null_geometry=False)
    if ev.empty:
        return pd.DataFrame(), pd.DataFrame()
    counts = ev.groupby(["event_category", "event_type"]).size().rename("n_events").reset_index()

    field_rows, type_rows = [], []
    for _, r in counts.iterrows():
        slug = r["event_type"]
        try:
            version, schema, raw = get_event_schema(er, slug)
        except Exception as e:  # noqa: BLE001
            type_rows.append({**r, "connection": name, "error": str(e)[:200]})
            continue
        resolves, resolver_fields = resolver_choice_props(version, raw)
        details = ev.loc[ev["event_type"] == slug, "event_details"]
        kinds = {}
        for key, prop in schema["properties"].items():
            kind = classify_field(prop)
            kinds[kind] = kinds.get(kind, 0) + 1
            values = details.map(lambda d: d.get(key) if isinstance(d, dict) else None)
            filled = values.map(lambda v: v not in (None, "", []))
            flat = values[filled].explode() if kind == "multi" else values[filled]
            flat = flat.map(lambda v: json.dumps(v) if isinstance(v, (dict, list)) else v)
            field_rows.append({
                "connection": name, "event_category": r["event_category"], "event_type": slug,
                "api": version, "field": key, "title": prop.get("title", key), "kind": kind,
                "n_options": len(prop.get("enumNames") or (prop.get("items") or {}).get("enumNames") or {}),
                "n_events": len(details), "fill_rate": round(filled.mean(), 3) if len(details) else None,
                "n_distinct": flat.nunique(), "top_values": "; ".join(map(str, flat.value_counts().head(5).index)),
                "resolver_offers": slug if False else (key in resolver_fields),
            })
        type_rows.append({
            "connection": name, "event_category": r["event_category"], "event_type": slug, "api": version,
            "n_events": r["n_events"], **{f"n_{k}": v for k, v in kinds.items()},
            "resolver_resolves": resolves, "resolver_fields": ", ".join(resolver_fields),
        })
    return pd.DataFrame(type_rows), pd.DataFrame(field_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--connection", action="append")
    ap.add_argument("--since", default=SINCE)
    ap.add_argument("--until", default=UNTIL)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    types, fields = [], []
    for name in a.connection or CONNECTIONS:
        print(f"== {name}")
        try:
            t, f = survey_connection(name, a.since, a.until)
        except Exception as e:  # noqa: BLE001
            print(f"   failed: {e}")
            continue
        print(f"   {len(t)} event types, {len(f)} fields")
        types.append(t)
        fields.append(f)
    types = pd.concat(types, ignore_index=True)
    fields = pd.concat(fields, ignore_index=True)
    types.to_csv(OUT / "survey_event_types.csv", index=False)
    fields.to_csv(OUT / "survey_fields.csv", index=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
