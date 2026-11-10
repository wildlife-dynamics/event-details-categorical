# Event Details – Categorical Field Workflow

An Ecoscope workflow that summarises **one dropdown field** of an EarthRanger event type, such as species, cause of death or water level. It shows which values were recorded, how often, when and where.

It complements the [Event Details](https://github.com/ecoscope-platform-workflows-releases/event-details) workflow, which sums a numeric field.

**What it works with**

- One event type per run, on forms built with the newer (v2) form builder.
- Dropdown fields that allow one choice: pick one, and yes/no. Pick-several and free-text fields aren't used (typed answers vary in spelling).
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
| | **Categorical Field** (required) | Picked from the event type's dropdown fields that allow one choice (pick one or yes/no), including fields in repeating lists and follow-up questions. See [Choosing the field](#choosing-the-field). Its follow-up questions are added to the breakdown chart automatically |
| | Count By *(advanced)* | **Events** (the default) counts each event once, or each row for a field in a list, e.g. each detection. **Numeric Field** adds up a number field picked from the event type's number fields (the **Field** dropdown) for each choice, e.g. `Count` or `Detection: Count` (birds counted rather than sightings) |
| | Show Typed "Other" Names *(advanced)* | Show each name typed for an "Other" answer as its own value, e.g. "Other: Flappet Lark", kept as typed. The typed name is taken from the text field the Other choice opens, or the one right after the field on the form |
| | Keep Form Order *(advanced)* | Tick when the choices have a natural order (age class, water level): shown in form order instead of by count |
| | Show Every Value *(advanced)* | Show every value instead of the top 10 plus "Other" |
| Group by | Time, or Category (Reported By) | Optional: one dashboard view per group |
| Base Maps *(advanced)* | | Map background layers |
| Time Period *(advanced)* | Time Period | Auto (weekly up to 2 months, monthly up to 3 years, otherwise quarterly), or fixed |
| Grid Map *(advanced)* | Grid Square Size (km) | Auto: about 25 squares across the events |

### Choosing the field

Once an event type is picked, **Categorical Field** and **Field** (under Count By: Numeric Field) list that form's fields by their titles, e.g. `Water Status`. The configuration stores the field key (`water_status`).

Fields inside repeating lists, follow-up questions and yes/no fields are listed on Ecoscope Web. Ecoscope Desktop 1.3.0 lists only the form's top-level fields.

- **Follow-up questions**, e.g. *Cause of Death (POACHED)*, asked only when *Type of Death* is "Poached": pick *Type of Death* and its follow-ups form the outer ring of the breakdown chart. A follow-up can also be picked itself; it is then counted only on the events where it was asked.
- **Repeating lists**, e.g. a Bird Point Count with one row per species seen: pick `Detection: Species` (list name, then field). Each row then counts as a record, so the dashboard counts detections rather than events. Count By: Numeric Field with a field from the same list (`Detection: Count`) adds it up per row.

## Dashboard

| Widget | Shows |
|---|---|
| Events (or Total *Field*) · Distinct values · Unassigned *field* | Headline tiles, each with a trend line over the whole period. Distinct values counts Unknown (a choice on the form); Unassigned is the number of records where the field was left blank |
| *Field* | Bar chart: the top 10 values plus "Other", with count and share, each value in its own colour |
| Breakdown | Sunburst chart with the field's name in the middle, then its values, then their follow-up answers (e.g. type of death, then cause). Click a slice to zoom, the middle to zoom out. "Other" opens onto the next 10 values and its own "Other", so clicking down reaches every value |
| *Field* over time | Share of each value per period (100% stacked bars); switch to Counts or Lines. Double-click a value in the legend to show only it |
| *Field* by location | Map of events coloured by value, sized by how many were recorded at the same spot (with Count By: Numeric Field, sized and labelled by its total, the tooltip shows both). Buttons: All, then the top 10 values, then an **Others** list with every other value; a value's events in colour, the other events as grey dots. The legend follows the selected tab |
| *Field* density (*n* km squares) | Grid map with the same buttons and Others list: darker squares hold more events (with Count By: Numeric Field, a larger total); squares with fewer than 5 records are pale |
| Values table | Every value of the field and its follow-ups: count, share, grid squares and reporters. A follow-up's share is out of the events where it was asked, not all events |

**Files** (Files tab): `values_summary.csv` (the values table) and `events.csv` (one row per event with the field and its follow-ups; no reporter names).

### How values are counted

- **Other:** less common values are grouped as "Other (k values)", shown in magenta; hover to see what it holds. Values tied at the cut-off are kept together.
- **Records or totals:** with Count By: Events, every chart counts records (events, or rows of a list) (events, or rows of a repeating list). With Numeric Field, tiles, bars, the breakdown and charts over time total that field; the values table shows both (Count and Total), and the maps size and shade by it. Unassigned and Distinct values always count records.
- **Typed "Other" names:** with Show Typed "Other" Names, each name typed for "Other" is its own value ("Other: …"), kept as typed, so spelling variants stay separate.
- **Unknown** is a choice like any other: it has its own colour and counts as a distinct value. Answers such as "Unknown – please describe in notes" count as Unknown.
- **Blank** (unanswered) is shown in grey, never dropped. Light grey dots on a map tab are the other events.
- **Removed choices:** an answer whose choice was later taken off the form keeps its label, marked "(inactive)".
- **Labels** are kept exactly as on the form; near-duplicates (e.g. "Elephant" and "Elephants") stay separate.
- **Colours** are fixed for the whole run, so a value has the same colour in the bars, breakdown, charts over time and maps, in every view. The top 10 values get their own colour. With Show Every Value, the values past the top 10 get slate blue-grey shades, lighter to darker by rank.
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
| `naibungalower-post-report` | A pick-one field in form order, one view per month |
| `naibungalower-post-report-no-events` | A period with no events |
| `naibungalower-wildlife-sighting` | Many values, "Other" and ties, one view per reporter |
| `naibungalower-ranger-sightings` | Many blank answers, no grouping |
| `wd-bird-point-count` | A repeating list (detections), Count By: Numeric Field |
| `naibungalower-carcass-invented` | Follow-up questions, one view per year (invented data on the real form) |
