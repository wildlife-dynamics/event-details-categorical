"""Find good example event types for the categorical workflow on one EarthRanger site.

For each v2 event type with >= MIN_EVENTS events since SINCE: its dropdown questions
(pick one, pick several, yes/no) and how often each is answered. A good example has
several dropdowns that are mostly filled in, with a few to a few dozen distinct answers.

  <compiled env python> .scripts/survey_examples.py <connection> [--since 2019-01-01]

Writes .scripts/outputs/examples/<connection>.csv (one row per event type x dropdown).
"""

import argparse
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

from ecoscope.platform.connections import EarthRangerConnection  # noqa: E402
from ecoscope_workflows_ext_wd.tasks import _categorical as cat  # noqa: E402

MIN_EVENTS = 100
TOP_TYPES = 15  # busiest event types checked per site
OUT = Path(__file__).parent / "outputs" / "examples"


def blank(v) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return True
    if isinstance(v, (list, dict, str)):
        return len(v) == 0 or (isinstance(v, str) and v.strip().lower() in cat.UNKNOWN_WORDS)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("connection")
    ap.add_argument("--since", default="2019-01-01")
    a = ap.parse_args()
    since = datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc).isoformat()
    until = datetime.now(timezone.utc).isoformat()
    client = EarthRangerConnection.from_named_connection(a.connection).get_client()
    types = client.get_event_types(include_inactive=True)
    display = dict(zip(types["value"], types["display"]))
    ids = dict(zip(types["value"], types["id"]))
    ev = client.get_events(since=since, until=until, include_details=False, drop_null_geometry=False)
    counts = ev["event_type"].value_counts()
    rows = []
    for et, n in counts[counts >= MIN_EVENTS].head(TOP_TYPES).items():
        try:
            with client._use_v2_api():
                props = client._get(f"activity/eventtypes/{et}/schema")["json"]["properties"]
        except Exception:
            continue  # v1 form
        drops = {k: cat._classify(p) for k, p in props.items() if cat._classify(p) in ("single", "multi", "yes_no")}
        if not drops:
            continue
        try:
            det = client.get_events(event_type=[ids[et]], since=since, until=until, include_details=True,
                                    drop_null_geometry=False)  # fmt: skip
        except Exception as e:
            print(f"{a.connection} {et}: {type(e).__name__}", file=sys.stderr)
            continue
        details = det["event_details"].apply(lambda d: d if isinstance(d, dict) else {})
        located = det.geometry.notna().mean() if "geometry" in det else float("nan")
        t = pd.to_datetime(det["time"], utc=True)
        for k, kind in drops.items():
            vals = details.apply(lambda d: d.get(k))
            filled = (~vals.apply(blank)).mean()
            flat = vals[~vals.apply(blank)].explode().astype(str)
            rows.append({
                "site": a.connection, "event_type": et, "display": display.get(et, et), "events": len(det),
                "from": f"{t.min():%Y-%m}", "to": f"{t.max():%Y-%m}", "located": round(located, 2),
                "field": k, "title": props[k].get("title", k), "kind": kind, "filled": round(filled, 2),
                "distinct": flat.nunique(), "top": "; ".join(f"{v} {c}" for v, c in flat.value_counts().head(4).items()),
            })  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / f"{a.connection}.csv", index=False)
    print(f"{a.connection}: {len(rows)} dropdowns in {len({r['event_type'] for r in rows})} event types")


if __name__ == "__main__":
    main()
