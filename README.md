# Event Details - Categorical Field Workflow

An EarthRanger workflow that summarises the **dropdown fields** of one event type (species, sex, cause of death, tank level …): which values were recorded, how often, when and where. It is the categorical counterpart of [event-details](https://github.com/ecoscope-platform-workflows-releases/event-details), which sums a numeric field.

One event type per run, **v2 forms only**. Categorical means a dropdown on the form: pick one, pick several, or yes/no. Free text is never used.

## Configuration page

| Section | Setting | Shown | Notes |
|---|---|---|---|
| Workflow Details | Name, description | always | |
| Data Source | EarthRanger connection | always | |
| Time Range | Since, until, timezone | always | Events dated in the period |
| **Event Type and Fields** | **Event Type** | always, required | Dropdown of the site's event types (EarthRangerEnumResolver) |
| | **Main Field** - Choice field to analyze | always, required | Drives the summary tiles, main charts and map colours. Must allow one choice per event |
| | **Other Fields** - More choice fields to summarize | always | Up to 8; each gets its own widgets |
| | **Cross-tabs** | always | Pairs of fields (rows × columns) |
| | Sunburst Rings | advanced | Rings from the center out; **empty = the main field, then its follow-up fields (one shared ring), or else the first other field that allows one choice per event** |
| | Keep Form Order | advanced | Fields whose choices keep the form's order instead of count order (age class, tank level) |
| | Show Every Value | advanced | Bars, cross-tabs and charts over time list every value instead of top 10 (8 over time) + Other; values past the 8 colours are grey |
| Group by | Time / Reported By / Quarter / area | always | Optional: one dashboard view per group. Quarter ("2026 Q1") comes from `add_categorical_quarter`; the platform's time grouper has none |
| Base Maps | | advanced | Standard ecoscope base maps |
| Over Time | Time Period | advanced | Auto (weekly ≤ 2 months, monthly ≤ 3 years, else quarterly), or fixed |
| Grid Map | Grid Square Size (km) | advanced | Auto: about 25 squares across the events |

**Follow-up fields** (an answer opens a question, e.g. Type of Death "Poached" opens Cause of Death (POACHED)) are typed like any other field. They count only the events where they were asked ("34 of 260 events · asked when Type of Death is Poached"). Follow-ups of one parent share one sunburst ring.

**Repeating groups** (a list of rows in one event, e.g. Bird Point Count's Detection rows): type `Detection: Species`, or just `Species`. Using a group field makes each row a record, so the dashboard counts detections, not events. Fields from two groups can't be mixed.

Fields are **typed as they read on the form** ("Water Status"); the field key (`water_status`) also works, and case, spaces and underscores don't matter. A name that isn't a dropdown on the form stops the run with a message listing the form's dropdown fields. They become dropdowns once EarthRangerEnumResolver can list categorical fields for this workflow (see `PLAN.md` §2-3).

## Dashboard

Like the other Ecoscope workflows, a widget is its title and its chart (no question line). The main field and **each other field get their own widgets**. Widgets are fixed when the workflow is compiled, so the per-field widgets go last in the widget list and `layout.json` has slots for 8 other fields: the app shows only slots that have a widget, and the widgets below move up (react-grid-layout, vertical compaction). `make open` lays the preview out the same way.

| Widget | Shows |
|---|---|
| Events · Distinct *main field* values · *Main field*: % unknown or blank | Three headline tiles (as QENP), each a number with a sparkline: events per period, running total of distinct values (Unknown and blank left out), % unknown or blank per period |
| *Main field* (e.g. "Water Status") | Bar chart, top 10 + Other + grey Unknown / blank, count and share |
| Breakdown | Sunburst of the Sunburst Rings (empty: the main field, then the first other field with one choice per event); top 8 per parent + "Other (k values)", listed on hover; click to zoom |
| *Main field* over time | 100% stacked bars per period; switch to Counts or Lines |
| *Each other field*, then *its* over time | One row per field: its bar chart (pick several: counts + note) and its chart over time (pick several: one line per value) |
| Cross-tabs | Heatmap per pair, counts or row %, top 10 + Other per axis |
| Where each value was recorded | Points coloured by the main field, sized by events at the same spot; the view fits the middle 98% of events |
| Where each value is concentrated | One grid map, a button per top-6 value: events per square (darker = more, pale under 5) |
| One map per value | One map, a button per top-6 value + Other: that value's events in colour, other events in grey |
| Values table | Every value of every field: event type, count, share, grid squares, reporters |

Files: `values_summary.csv`, `events.csv` (one row per event, no reporter names), `crosstabs.csv`.

A value keeps its colour, and "Other" holds the same values, in every view: ranking and colours are computed once, before grouping. Values tied at the top-N cut are kept together, never split alphabetically.

## Develop

Tasks: `ecoscope-workflows-ext-wd` 0.0.7 on prefix.dev (wd-partner-tasks, checked out at `../wd-partner-tasks-categorical`): `tasks/_categorical.py`, tests in `tests/tasks/test_categorical.py`.

```console
make build     # build unreleased ext-wd into /tmp/ecoscope-workflows-custom/categorical/artifacts
make dev       # fast compile with the editable ext-wd (wt-compiler-env-overrides.toml)
make run       # run param.yaml on real data -> /tmp/event-details-categorical/output
make open      # preview the dashboard (layout.json, view selector)
make test      # compiled tests, mock IO from mock-io/ (CASE=naibungalower-post-report)
```

Test cases (`test-cases.yaml`): naibungalower post reports by month, wildlife sightings by reporter, ranger sightings with the summary grid.

The two button maps are one WebGL map each, with buttons that show or hide layers: Chromium (so Ecoscope Desktop) keeps about 16 WebGL canvases per page and drops the oldest, so a map per value blanked the points map.
