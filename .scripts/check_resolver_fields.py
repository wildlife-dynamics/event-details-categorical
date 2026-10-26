"""Which fields would the Event Details form let a user pick, per event type?

Replicates ecoscope-server EarthRangerEnumResolver.fetch_and_build_event_type_schema_enum
(compose/ecoscope-server/ecoscope_server/utils/er_enum_resolver.py:334-431), which fills
  analysis_field  <- event_type_schema_numeric_prop  (type == "number")
  category_field  <- event_type_schema_choice_prop   (v2 only, top-level "anyOf")
It first keeps only event types with >= 1 numeric field; any other type raises
"No schema found" and the form shows "Failed to fetch ...".

Compared with the fields this prototype treats as categorical (classify_field):
single, multi, yes_no (+ text, picked by hand).

Output: .scripts/outputs/explore/resolver_check_<connection>.csv

Run with download-attachments' compiled env:
  ../download-attachments/ecoscope-workflows-event-photo-records-workflow/.pixi/envs/default/bin/python \\
    .scripts/check_resolver_fields.py wd [mep ...]
"""

import json
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

from ecoscope.platform.connections import EarthRangerConnection  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from categorical_analysis import OUT, classify_field  # noqa: E402


def resolver_view(schema_str: str) -> tuple[str, bool, list[str], list[str]]:
    """(api, resolves, numeric fields, choice fields) exactly as the resolver sees it."""
    import re

    parsed = json.loads(re.sub(r"\{\{[^}]+\}\}", r'"\g<0>"', schema_str or "{}"))
    v2 = "json" in parsed
    props = (parsed.get("json") if v2 else parsed.get("schema", {})).get("properties", {}) or {}
    numeric = [k for k, p in props.items() if p.get("type") == "number"]
    choice = [k for k, p in props.items() if "anyOf" in p] if v2 else []
    return ("v2" if v2 else "v1"), bool(numeric), numeric, (choice if numeric else []), props


def main():
    for conn in sys.argv[1:] or ["wd"]:
        er = EarthRangerConnection.from_named_connection(conn).get_client()
        rows = []
        for api in ("v1.0", "v2.0"):
            # same call the resolver's datasource makes: event types with their schema
            ets = er.get_event_types(include_inactive=False, api_version="v2" if api == "v2.0" else "v1", include_schema=True) \
                if False else None  # noqa: E501
        ets = er._get("activity/events/eventtypes", params={"include_schema": True, "include_inactive": False})
        with er._use_v2_api():
            v2 = er._get("activity/eventtypes", params={"include_schema": True})
        v2 = v2.get("results", v2) if isinstance(v2, dict) else v2
        for et in ets + list(v2):
            schema = et.get("schema")
            if isinstance(schema, dict):
                schema = json.dumps(schema)
            if not schema:
                continue
            api, resolves, numeric, choice, props = resolver_view(schema)
            kinds = {k: classify_field(p) for k, p in props.items()}
            ours = [k for k, kd in kinds.items() if kd in ("single", "multi", "yes_no")]
            text = [k for k, kd in kinds.items() if kd == "text"]
            rows.append({
                "event_type": et.get("value"), "display": et.get("display"), "api": api,
                "resolver_ok": resolves, "numeric_fields": ", ".join(numeric),
                "resolver_category_fields": ", ".join(choice),
                "categorical_fields_schema": ", ".join(f"{k} ({kinds[k]})" for k in ours),
                "text_fields": ", ".join(text),
            })  # fmt: skip
        df = pd.DataFrame(rows).drop_duplicates(["event_type", "api"])
        (OUT / "explore").mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT / "explore" / f"resolver_check_{conn}.csv", index=False)
        has_cat = df[df["categorical_fields_schema"] != ""]
        print(f"== {conn}: {len(df)} event-type schemas, {len(has_cat)} with schema categorical fields, "
              f"{(has_cat['resolver_category_fields'] != '').sum()} where the resolver offers any")
        print(has_cat[["event_type", "api", "resolver_ok", "resolver_category_fields", "categorical_fields_schema"]].to_string(index=False, max_colwidth=70))


if __name__ == "__main__":
    main()
