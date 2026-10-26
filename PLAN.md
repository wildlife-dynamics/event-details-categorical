# Event Details: Categorical Field Workflow: Plan

The categorical version of [event-details](https://github.com/ecoscope-platform-workflows-releases/event-details). Where that workflow sums one number field, this one counts the answers to dropdown questions (e.g. species, cause of death, vessel type): which values were recorded, how often, when and where. The scope comes from `PRD_Categorical_Event_Data_Analysis_GoogleDocs.docx`. The scripts follow the `.scripts/` convention used in `download-incidents`.

> Status (2026-10-20): **workflow built** (§6): `spec.yaml` + tasks in ext-wd, compiled and run on 3 naibungalower cases. Earlier: investigation done. The prototype `.scripts/categorical_analysis.py` draws PRD outputs 1-7 for one event type per run. It was tested on 3 naibungalower v2 forms (§4), and the outputs are waiting for review. The form plan is in §3: the event type comes from a dropdown now, and the field dropdowns come later.

---

## 1. Scope

| Decision | Value |
|---|---|
| Event types per run | **One**, same as the numeric workflow |
| Forms | **v2 forms only** |
| Fields | Any number of categorical fields from that form, plus one **main field** that drives the tiles, the map colours and the small multiples |
| Categorical | pick-one dropdown, pick-several dropdown, yes/no. **Never free text** (§4) |
| Unknown / blank | Kept as their own grey values, never dropped |

How a v2 form marks each kind of field:

| Kind | In the v2 form definition | Example |
|---|---|---|
| Pick one | `anyOf` at the top of the field | `trwg_snares_traps.status`: Caught / Set |
| Pick several | `type: array`, `anyOf` inside `items` | `trwg_snares_traps.type`: Cable snare / Wire snare / … |
| Yes/no | `type: boolean` | `ebird_observation.valid` |

## 2. What EarthRangerEnumResolver can do today

The resolver is the server code that fills a form's dropdowns with options from the selected EarthRanger site (`compose/ecoscope-server/ecoscope_server/utils/er_enum_resolver.py`).

| Dropdown | Resolver type | Works in our workflow today? |
|---|---|---|
| **Event type** | `event_type` | **✅ Yes.** It doesn't depend on the template name. `event-details-schema/spec.yaml` already uses it |
| Field dropdowns | `event_type_schema_choice_prop` | ❌ No, for the two reasons below |

**Why the field dropdowns don't work yet:**

1. **Only the numeric workflow gets a "Select event type" step.** The web app (`ecoscope-web/src/utils/constants.ts:59`) and the server (`ecoscope-server/utils/rjsf.py:30, 672`) both check for the exact template name "Event Details - Numeric Field Workflow". That's the name `event-details` is registered under in `compose`. For any other template, no event type reaches the resolver, so the field dropdowns stay empty.
2. **`choice_prop` only lists some categorical fields.**
   - It skips a form when the form has **no number field** (`er_enum_resolver.py:362-370`), e.g. `wildlife_sighting` with its species dropdown.
   - It lists **pick-one** dropdowns only (`er_enum_resolver.py:411`). It misses pick-several and yes/no fields.

What this misses on real v2 forms (`.scripts/check_resolver_fields.py`, `outputs/explore/resolver_check_<site>.csv`):

| Site | v2 forms with categorical fields | Forms with no number field (nothing listed) | Pick-one fields listed | Pick-several missed | Yes/no missed |
|---|---|---|---|---|---|
| wd | 41 | 12 | 73 of 106 | 45 | 13 |
| mep | 64 | 36 | 110 of 177 | 7 | 1 |
| naibungalower | 85 | 14 | 360 of 406 | 133 | 9 |
| icf | 270 | 49 | 1,082 of 1,284 | 114 | 0 |

## 3. Form plan

### Now (phase 1): event type from a dropdown, fields typed in by the user

```yaml
rjsf-overrides:
  properties:
    set_categorical_params.properties.event_type.ecoscope:transform:
      - transformer: EarthRangerEnumResolver
        transformer_kws:
          type: event_type
          depends_on: properties.er_client_name.properties.data_source.properties.name
```

- **Event type**: a dropdown filled by the resolver with the site's active event types. This works today.
- **Event type**: the user picks it by its display name in the dropdown (e.g. "Post Report"). The workflow receives the event type's key (`post_rep`).
- **Main field** and **fields to summarise**: **typed in by the user, as the field reads on the form** (e.g. "Water Status"). The field key (`water_status`) also works, and case, spaces and underscores don't matter. `resolve_field_names()` turns each name into its key. If two questions on a form share a label, the user is asked to type the key.
- The workflow checks the typed fields when it runs, and stops with a clear message if:
  - the event type isn't a v2 form;
  - a field isn't on the form ('"Water Level" is not a field on this form. Dropdown fields: "Post", "Water Status", …');
  - a field isn't pick-one, pick-several or yes/no.
- Downside: the event-type list shows every active type, v1 included, and the user has to type the field names correctly. The error message lists the form's dropdown fields, and the `event-details-schema` workflow exports every form's fields.

### Later (phase 2): field dropdowns, once the server change lands

Request to Alex (ecoscope-server + ecoscope-web):

1. Give our workflow the "Select event type" step as well. Ideally it should key off something the workflow declares (e.g. a flag in the spec) rather than the name "Event Details - Numeric Field Workflow". The fallback is adding our template's name to both checks.
2. Add a new resolver type, `event_type_schema_categorical_prop`:
   - it lists pick-one, pick-several and yes/no fields;
   - it doesn't require a number field;
   - each option shows its kind, e.g. "Type (pick several)";
   - `choice_prop` stays unchanged, so the numeric workflow isn't affected.

   Detection:
   ```python
   if "anyOf" in prop:                    -> pick one
   if "anyOf" in prop.get("items", {}):   -> pick several
   if prop.get("type") == "boolean":      -> yes/no
   ```

Then the typed fields become dropdowns:
```yaml
    set_categorical_params.properties.main_field.ecoscope:transform:
      - transformer: EarthRangerEnumResolver
        transformer_kws:
          type: event_type_schema_categorical_prop
          depends_on: properties.set_categorical_params.properties.event_type
    set_categorical_params.properties.fields.ecoscope:transform:
      - transformer: EarthRangerEnumResolver
        transformer_kws:
          type: event_type_schema_categorical_prop
          depends_on: properties.set_categorical_params.properties.event_type
```

The run-time checks from phase 1 stay in place as a safety net.

## 4. Prototype: `.scripts/categorical_analysis.py`

One event type per run (`--event-type`). The functions are written as future tasks:
- `get_events`
- `get_field_catalogue`: reads the form → each field's kind, choice labels, and parent field (from v2 `allOf` if/then)
- `categorical_long`: one row per event × field × value
- `crosstab`, `summary_table`, `event_level_table`
- one `draw_*` per output

Maps use ecoscope `draw_map` and charts use plotly. Outputs go to `.scripts/outputs/<connection>/<event_type>/index.html`.

| PRD output | Built as |
|---|---|
| 1 Tiles | Events (weekly line) · distinct values, shown with both a weekly line and a running total · % Unknown or blank |
| 2 Sunburst | The type's fields (e.g. vessel type → flag state). Top 8 per parent + "Other (k values)", which lists its values on hover. Click to zoom. Pick-several is left out |
| 3 Bars | One chart per field, top 10 + Other + grey Unknown/blank. Pick-one fields show count · %. Pick-several fields show counts and a note |
| 4 Over time | 100% stacked by default, with a Counts button. The period is set from the date range (≤2 months weekly, ≤3 years monthly, otherwise quarterly). Pick-several is drawn as lines |
| 5 Cross-tab | Heatmap with numbers, top 10 + Other on each axis, Counts / Row % buttons. Also saved as CSV |
| 6 Maps | Points map: coloured by the main field, sized by the number of events at the same spot, with a count label at 10 or more. Grid maps: one small grid per top-6 value, with squares under 5 events drawn pale, plus the optional summary grid. Small multiples: top 6 + Other, other events in grey |
| 7 Tables | `summary.csv` (field, value, count, share, grid squares, reporters), cross-tab CSVs, and an event-level CSV without personal fields |

### How "Other (k values)" is built (decided 2026-10-19)

`Ranked.head()` + `lump()` in `categorical_analysis.py`:
1. Count events per value. Unknown and (blank) are left out of the ranking; they always keep their own grey slot.
2. Sort by count, highest first.
3. Keep the top N. Every other value is merged into "Other (k values)", where k is the number of values merged.

| Output | N kept | Why |
|---|---|---|
| Bar charts, cross-tabs | 10 (`TOP_BAR`) | PRD: "top 10". One colour for all bars, so there is no colour limit. Setting `full_list: true` shows every value |
| Points map, sunburst, stacked bars | 8 (`TOP_COLOR`) | One colour per value, and there are 8 colours that are safe for colour-blind readers. The PRD allows 6-10 for the map and 6-8 for the sunburst. Stacked bars use 8, not the PRD's 10, for the same colour reason |
| Small multiples, small grids | 6 (`TOP_SMALL`) | PRD: "top 6 + Other" |

**Ties at the cut-off are never split alphabetically:**
- Tied values are **all kept** if the list stays within its limit: 8 colours for the colour outputs, 15 for bars and cross-tabs.
- Otherwise they **all go to Other**.
- If every value is tied, the first N are kept.

**Other's members are always shown:**
- Bar, sunburst and stacked-bar hovers list the values in Other, with their counts.
- Cross-tabs list them in a note under the heatmap.
- On the maps, each point's tooltip shows its real value.

Example: `wildlife_sighting`, 15 species.

| Output | Named | Other | Why |
|---|---|---|---|
| Bars | 10 | 5 values | no tie at the 10th place |
| Map, sunburst, stacked bars | 7 | 8 values | Thomson's Gazelle and Gerenuk are tied for the 8th colour, so both go to Other |
| Small multiples | 7 | 8 values | Eland, Spotted Hyena and Burchell's Zebra are tied for places 5-7, so all three are kept |

"Other" can still differ between bars (top 10) and the colour outputs (top 8). The hover list always shows what it holds.

### Free-text fields: not categorical (decided 2026-10-20)

Only **dropdown** fields count as categorical: pick one, pick several, yes/no. Free-text fields are rejected, **including standardised integration text** such as eBird `common_name` or iNaturalist `taxon_common_name`.

The form can't tell a consistently filled text field from one that rangers type by hand, and hand-typed values split on spelling ("Walking" vs "Walking "). The PRD's "standardised text fields from integrations" are therefore out of scope. eBird, iNaturalist and Skylight drop out until their forms use dropdowns. A text-field version was built and tried on eBird and iNat on 2026-10-20, then removed.

### Natural order and groupers (built 2026-10-19)

**Natural order:** setting `natural_order: [field, ...]`.
- Those fields keep the order of the choices on the form instead of sorting by count, e.g. Water status reads Full / 75% / 50% / 25% / Empty.
- Applies to the bar charts, the stacked bars over time and the cross-tab axes.
- Yes/no fields always read Yes, No.
- Colours stay categorical. An ordered colour ramp (light to dark) for these fields would read better; that's a follow-up.

**Groupers:** setting `grouper`, one per run:

| Grouper | Setting | Views |
|---|---|---|
| Time | `{"time": "month" \| "quarter" \| "year"}` | one per period, in time order. Each view picks its own trend period, e.g. a month view goes weekly |
| Reported by | `{"reported_by": true}` | one per reporter, plus "(not recorded)" |
| Area | `{"area": "<spatial feature group>"}` | one per feature of that ER spatial feature group, plus "(outside the areas)". An event that falls in several features goes to the first |

How the views work:
- The output is an "All events" page (`index.html`) plus one page per group (`views/<group>/index.html`). A "View by …" selector in each page's header switches between them, like the platform dashboard's view switcher.
- Every view uses the **whole run's** ranking, colours, "Other" membership and grid square size (`run_context()`). A value keeps its colour in every view, and the views can be compared.

Tested:
- `post_rep` with quarters (2025 Q1-Q4).
- `wildlife_sighting` with reporters (6 reporters + not recorded).
- The area grouper on WD's "ROIs" group. It runs, but WD's wildlife sightings are on the coast and the ROIs are around the Mara, so every event lands in "(outside the areas)". naibungalower has no spatial feature groups. The point-in-area assignment was checked with two test polygons. It still needs a site where events and areas overlap.

Also fixed: **a form option called "Other"** (WD `wildlife_species`: Elephant / Other) was mixed up with the merged "Other (k values)" group and crashed the stacked bars. The merged group is now recognised only by its exact label, "Other (k values)".

### Test run (2026-10-14): naibungalower, v2 forms

mep `arrest_rep` turned out to be test data: every answer is the same, and some fields hold test strings. So the test moved to **naibungalower**, whose v2 forms have real dropdowns. The prototype now applies the phase 1 rules: v2 only, field keys checked by `validate_fields()`.

| Event type | Range | Events | Fields (main first) | What it tests |
|---|---|---|---|---|
| `wildlife_sighting_rep_ranger` | 2025-01 → now | 1,971 | Location, Conservancy, Actions checklist (pick several) | Volume; 40% blank main field; monthly trends |
| `post_rep` | 2025-01 → now | 246 | Water status, Post, Morning/Evening call-up, Technical issues (pick several), Watch-keeper checklist (pick several) | Pick-several bars and lines; natural-order values (25% / 50% / Full) |
| `wildlife_sighting` | 2026-09-20 → now | 109 | Species, Sighting type | 15 species, so Other is used; weekly trends |

Outputs: `.scripts/outputs/naibungalower/<event_type>/index.html`.

Found while testing:
- **(0, 0) GPS points:** 14 events sit at or near (0, 0), off the coast of West Africa. The map zoomed out to all of Africa. Points within 1° of (0, 0) are now treated as unlocated, and the header shows how many events are left off the maps.
- **Repeating groups:** `wildlife_sighting_rep_ranger` keeps its species inside `sighting_details`, a list of sub-forms. Neither the resolver nor the prototype reads fields inside repeating groups yet.
- **Natural order:** Water status shows 25% / Full / Empty / 50% / 75% (sorted by count). This needs the natural-order setting.
- **WD:** the Skylight/eBird/iNat runs are now rejected, as intended. Messages: "entry_alert_rep is not a v2 form" and "'common_name' is a text field, not categorical".

Not built yet: fields inside repeating groups, more than one grouper at a time, and an ordered colour ramp for natural-order fields.

## 6. The workflow (built 2026-10-20)

- **Tasks:** `ecoscope-workflows-ext-wd` 0.0.6 (released 2026-10-26; wd-partner-tasks PRs #40 and #42, checked out at `../wd-partner-tasks-categorical`), `tasks/_categorical.py`. It has 20 tasks, a port of the prototype, plus 16 unit tests in `tests/tasks/test_categorical.py`, all passing.
- **Two IO tasks**, so mock-IO tests can replace both: `get_categorical_field_catalogue` (form → field keys, checks, labels) and `get_categorical_events`.
- **Ranking and grid size** are computed before `split_groups`, so colours and Other are the same in every view.
- **Groupers:** the platform's `set_groupers`. Time comes from the platform's list: year, month, year-month, day … (no quarter). Value grouper: Reported By. Spatial: spatial feature groups through EarthRangerEnumResolver, the same chain as event-details.
- **Configuration page:** see `README.md`. The important settings are shown, and the rest is under "advanced" (`AdvancedField`).
- **Run:** `make run` / `make open`. The three test cases ran without errors: post reports by month (11 views), wildlife sightings by reporter (7 views), ranger sightings with the summary grid.
- **Compiled tests:** `make test` runs the workflow with mock IO, and the dashboard snapshots are in `__results_snapshots__`. Two failures are not ours:
  - `test_otel_traces_success` fails the same way in the incidents workflow (local tracing setup).
  - The map `test_iframes` screenshot differs between runs (tiles and WebGL).

- **Look matched to the prototype (2026-10-20):**
  - bars, trends and cross-tabs are cards, two to a row;
  - the Summary tile shows events without a location, the trend period and the grid size;
  - the grid widget shows the small grids with the summary grid folded below (the 'Summary Grid Instead' setting is gone);
  - the trend period is its own form task (`set_categorical_trend_period`);
  - the tiles are taller.
- **Main field in its own widgets (2026-10-21):** widgets are fixed when the workflow is compiled, and the number of fields varies per run. So the main field gets its own full-size "values" and "over time" widgets, titled with the field's name (`categorical_widget_title`). The other fields share one full-width, tall widget per output (`which="main" | "others"` on the bar and trend tasks).
- **Each other field in its own widgets (2026-10-21), replacing the shared ones:**
  - `draw_categorical_field_widgets` returns, per other field, a values widget and an over-time widget (each with one view per group). They go **last** in the dashboard's widget list, because widget ids are positions in that list.
  - `layout.json` has slots for **8** other fields (`MAX_OTHER_FIELDS`; the form refuses more). The app draws only layout entries that have a widget (`WorkflowResultsGridLayout.tsx`) and compacts the grid vertically, so unused slots leave no gap. `dev/preview_dashboard.py` does the same.
  - A workflow can't write its own layout: Desktop reads a run-level `layout.json`, but that's where it saves the user's own edits, and the cloud takes the layout from the server.
- **PRD gaps closed (2026-10-21):** a Lines switch on the over-time charts; Show Every Value also covers the over-time charts (past 8 colours: grey); an Event type column in the values table. No caveats widget (decided 2026-10-21). Also: one tick per period on the time axis, and long answers shortened in legends (full text on hover).
- **Desktop look (2026-10-22):** checked against ecoscope-desktop (`WorkflowResults.tsx`): the dashboard is the right 4/5 of the page, so tiles are narrower than a full-width preview; `dev/preview_dashboard.py` now draws that page. Single-chart widgets fill their tile; long answers are shortened in bar labels and legends (full text on hover). No question lines in the widgets (as in the incidents workflow): a widget is its title and chart.
- **Headline tiles (2026-10-22):** the custom Summary widget (three mini-cards and a footnote in one tile) didn't fit its box. It is now three widgets, one number and sparkline each, filling their tile like QENP's `draw_sparkline_kpi` (`draw_categorical_kpi`, kpi = events / distinct / unknown). The footnote (events without a location, trend period, grid size) is gone.
- **Field settings (2026-10-26):** a one-list "Fields" form was tried (2026-10-25) and reverted. The form keeps Main Field, Other Fields, Cross-tabs, Sunburst Rings and Keep Form Order, with two changes: **Sunburst Rings left empty is automatic** (the main field, then the first other field that allows one choice per event), and blank entries are ignored. Titles and descriptions follow the platform's own wording (ecoscope-platform `_earthranger.py`: "choice field", "Select…", "Choose…"), e.g. "Main Field - Choice field to analyze".
- **Still open against the PRD:** group by quarter (the platform has none); summary grid labels show "%" only, with n on hover; parent and child fields untested (no test site has one); personal fields beyond reporter names.

Not done yet: a release repo, and field dropdowns once ecoscope-server supports them (§3 phase 2).

## 5. Open questions

1. Distinct-values tile: keep both trend lines, or only one?
2. Keep the summary grid as an option, or drop it?
3. Personal-field rule: is the name pattern enough, or do we want a per-site list?
4. Phase 1: is a typed field key acceptable to users, or should the form link to the event-details-schema export?
5. ~~"Other" rule~~: decided 2026-10-19 (§4): 10 for bars and cross-tabs, 8 for colour outputs, 6 for small multiples; ties kept together; members listed on hover.
