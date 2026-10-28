# Event Details – Categorical Field Workflow

An Ecoscope workflow that summarises the **dropdown fields** of one EarthRanger event type, such as species, sex, cause of death or water level. It shows which values were recorded, how often, when and where.

It complements the [Event Details](https://github.com/ecoscope-platform-workflows-releases/event-details) workflow, which sums a numeric field.

**What it works with**

- One event type per run, on forms built with the newer (v2) form builder.
- Dropdown fields only: pick one, pick several, and yes/no. Free-text fields aren't used, because typed answers vary in spelling.
- Follow-up questions (a question that appears after a certain answer) and repeating lists (several rows in one event) are supported. See [Field names](#field-names).

## Installing

In Ecoscope Desktop, choose **Add Workflow Template** and give it this repository, or a local folder holding the compiled workflow (`ecoscope-workflows-categorical-workflow`).

### Windows: turn on long paths

On Windows, installing can fail with an error like:

```
Failed to persist file C:\Users\…\ecoscope-desktop\data\templates\…\conda-meta\….json:
failed to persist temporary file: The system cannot find the path specified. (os error 3)
```

Windows limits file paths to about 260 characters by default, and some files in this workflow's environment go past that. To lift the limit (this needs administrator rights):

1. Open the Start menu, type **PowerShell**, right-click it and choose **Run as administrator**.
2. Run:
   ```powershell
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
   ```
3. Close Ecoscope Desktop completely and open it again. If the error still appears, restart the computer.
4. Remove the template in Ecoscope Desktop and add it again.

The same setting is also available in Group Policy: *Computer Configuration → Administrative Templates → System → Filesystem → Enable Win32 long paths*.

## Configuration

| Section | Setting | Notes |
|---|---|---|
| Workflow Details | Name, description | |
| Data Source | EarthRanger connection | |
| Time Range | Since, until, time zone | Events recorded in the period |
| **Event Type and Fields** | **Event Type** (required) | Picked from the site's event types |
| | **Main Field** (required) | The field the headline tiles, main charts and maps are about. Must allow one choice per event (pick one or yes/no) |
| | **Other Fields** | Up to 8 more fields; each gets its own charts. Optional |
| | **Cross-tabs** | Pairs of fields to compare (rows × columns). Optional |
| | Sunburst Rings *(advanced)* | The fields in the breakdown chart, from the centre out. Empty: the main field, then its follow-up fields or the first other field |
| | Keep Form Order *(advanced)* | Fields whose choices have a natural order (age class, water level); shown in form order instead of by count |
| | Show Every Value *(advanced)* | Show every value instead of the top 10 plus "Other" |
| Group by | Time, Reported By, Quarter, area | Optional: one dashboard view per group |
| Base Maps *(advanced)* | | Map background layers |
| Over Time *(advanced)* | Time Period | Auto (weekly up to 2 months, monthly up to 3 years, otherwise quarterly), or fixed |
| Grid Map *(advanced)* | Grid Square Size (km) | Auto: about 25 squares across the events |

### Field names

Type each field **as it reads on the form**, e.g. `Water Status`. Case, spaces and underscores don't matter, and the field key (`water_status`) also works. If a name isn't a dropdown on the form, the run stops with a message listing the form's dropdown fields.

- **Follow-up questions**, e.g. *Cause of Death (POACHED)*, asked only when *Type of Death* is "Poached": type them like any other field. They are counted only on the events where they were asked ("34 of 260 events · asked when Type of Death is Poached"), and follow-ups of the same question share one ring in the breakdown chart.
- **Repeating lists**, e.g. a Bird Point Count with one row per species seen: type `Detection: Species` (list name, then field), or just `Species`. Each row then counts as a record, so the dashboard counts detections rather than events. Fields from two different lists can't be combined.

## Dashboard

| Widget | Shows |
|---|---|
| Events · Distinct values · % blank | Headline tiles for the main field, each with a trend line over the whole period. Distinct values counts Unknown (a choice on the form); % blank counts unanswered events |
| *Main field* | Bar chart: the top 10 values plus "Other", with count and share, each value in its own colour |
| Breakdown | Sunburst chart, ring by ring (e.g. type of death, then cause). Click a slice to zoom |
| *Main field* over time | Share of each value per period (100% stacked bars); switch to Counts or Lines |
| Cross-tabs | A heatmap per chosen pair; switch between counts and row % |
| *Main field* by location | Map of events coloured by the main field, sized by how many were recorded at the same spot. Buttons: All, then each value, then Other; a value's events in colour, the other events as grey dots |
| *Main field* density (*n* km squares) | Grid map with the same buttons (All, each value, Other): darker squares hold more events; squares with fewer than 5 are pale |
| Values table | Every value of every field: count, share, what the share is out of (all events, or for a follow-up the events where it was asked), grid squares and reporters |
| *Each other field*, *… over time* | The same bar chart and chart over time for each other field |

**Files** (Files tab): `values_summary.csv` (the values table), `crosstabs.csv` (every cross-tab cell) and `events.csv` (one row per event with the selected fields; no reporter names).

### How values are counted

- **Other:** less common values are grouped as "Other (k values)"; hover to see what it holds. Values tied at the cut-off are kept together.
- **Unknown** is a choice like any other: it has its own colour and counts as a distinct value. Answers such as "Unknown – please describe in notes" count as Unknown.
- **Blank** (unanswered) is shown in grey, never dropped. Grey otherwise means "Other", or the other events on a map tab.
- **Removed choices:** an answer whose choice was later taken off the form keeps its label, marked "(inactive)".
- **Labels** are kept exactly as on the form; near-duplicates (e.g. "Elephant" and "Elephants") stay separate.
- **Colours** are fixed for the whole run, so a value has the same colour in the bars, breakdown, charts over time and maps, in every view.
- **Pick-several fields** can have several answers per event, so their bars can add up to more than the number of events (a note says so).
- **No events in the period:** the dashboard opens with every widget showing "no data".

## Development

The analysis tasks live in [`ecoscope-workflows-ext-wd`](https://github.com/wildlife-dynamics/wd-partner_tasks) (`tasks/_categorical.py`, released to prefix.dev); this repository holds the workflow spec, layout, tests and the compiled workflow.

```console
make recompile   # release build: keeps the lock file and bumps the workflow version
make compile     # build from scratch (re-solves the lock; version starts at 0.0.0)
make dev         # fast build against a local, editable ext-wd checkout
make build       # build an unreleased ext-wd into a local channel
make run         # run param.yaml on real data
make open        # preview the dashboard in the browser
make test        # run a test case: make test CASE=naibungalower-post-report
```

**Releasing:** release ext-wd (tag `wd-v0.0.x` in wd-partner-tasks), set that version in `spec.yaml` and the `Makefile`, run `make recompile`, then run the test cases and `make run` before committing.

**Test cases** (`test-cases.yaml`, mock data in `mock-io/` or `mock-io/<case>/`):

| Case | Covers |
|---|---|
| `naibungalower-post-report` | Pick-one, pick-several and yes/no fields, form order, a cross-tab, one view per month |
| `naibungalower-post-report-main-only` | Main field only: no other fields, no cross-tabs |
| `naibungalower-post-report-no-events` | A period with no events |
| `naibungalower-wildlife-sighting` | Many values, "Other" and ties, one view per reporter |
| `naibungalower-ranger-sightings` | Many blank answers, no grouping |
| `wd-bird-point-count` | A repeating list (detections) |
| `naibungalower-carcass-invented` | Follow-up questions, grouped by quarter (invented data on the real form) |
