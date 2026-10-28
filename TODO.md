# TODO

Open work for the Event Details - Categorical Field workflow. Background is in `PLAN.md`.

## India's feedback (issue #6, 2026-10-28)

Released in ext-wd 0.0.11 (PR #50); workflow 0.4.0.

- [x] **Distinct values counts Unknown** (a choice on the form); only blank is left out, so the tile matches the bar chart.
- [x] **"% unknown or blank" → "% blank"**, counting blank answers only (spec: `kpi: blank`, title "{main}: % blank", ids `kpi_unknown*` → `kpi_blank*`).
- [x] **Sparklines span the run's whole time range** (tiles get `time_range`).
- [x] **Same colour for a value everywhere**: bars use each value's colour (as the breakdown, charts over time and maps); values past the 8 colours are slate.
- [x] **Whole-number count axes** (bars, Counts, pick-several lines): no 0.5 ticks.
- [x] **Points map tabs**: All, then each value, Other, Unknown and (blank); the selected value in colour, the rest in grey. "One map per value" removed from the spec and layout.json (widget ids after it shifted down by one; the grid map is now full width).
- [x] **Grid maps also show Unknown and (blank)**.
- [x] **Map titles**: "{main} by location" and "{main} density ({km} km squares)".
- [x] **Values table "Share of" column**: "all 260 events", or for a follow-up "34 events where Type of Death is Poached".
- Pie chart breakdown: no change (India likes it).

Next:
- [x] Checked on a dev build with India's example (Naibunga animal carcasses, Sep–Oct 2026): distinct 3, % blank 0%, sparklines 31 Aug–26 Oct, bars coloured like the pie, axis 0-1-2-3, map tabs All/Natural/Conflict/Unknown, new titles, Share of.
- [x] ext-wd #50 merged and released as **0.0.11**; workflow rebuilt with `make recompile` (0.4.0).
- [x] Snapshots updated (new titles, one widget fewer); all 7 test cases and `make run` pass.
- [ ] Reply on issue #6, item by item, and ask India to confirm the choices:
  - value tabs show the other events in grey (like the old "One map per value");
  - (blank) gets a tab on both maps, next to Unknown;
  - % blank lines leave gaps in weeks with no events (the axis covers the whole period).
- [x] README updated (tiles, map titles and tabs, no "One map per value", values table "Share of", colours).

## Release

- [x] Merge wd-partner-tasks PRs #40, #42 (categorical) and #41 (incidents).
- [x] Tag `wd-v0.0.6` and publish it to prefix.dev (2026-10-26). One release covers both workflows.
- [x] Point `spec.yaml` at ext-wd 0.0.6 on `https://repo.prefix.dev/ecoscope-workflows-custom/` and remove the `/tmp` file channel from `pixi.toml`.
- [ ] Run `make recompile`, `make test` and `make run`, then commit and push this repo. Leave out `wt-compiler-env-overrides.toml`, the `make dev` output and `.scripts/outputs/`.

## Configuration page

- [ ] Simplify the form. One **Fields** list where the first field is the main one (closer to the PRD), with Cross-tabs moved to Advanced.
- [ ] Rewrite the field descriptions in plain words (proposed wording is in the chat of 2026-10-22).
- [ ] Field dropdowns instead of typed names, once Alex's ecoscope-server change lets EarthRangerEnumResolver list categorical fields (`PLAN.md` §3, phase 2).

## Repeating groups, follow-up fields, quarter (built 2026-10-26, wd-partner-tasks PR #43)

- [x] Merge PR #43 and release ext-wd 0.0.7 (tag `wd-v0.0.7`, 2026-10-26); the workflow uses it.
- [x] Test cases `wd-bird-point-count` (repeating group; real WD data, reporter names replaced) and `naibungalower-carcass-invented` (follow-up fields, by quarter), each with its own mock data in `mock-io/<case>/`.
- Points map: dots stay where they were recorded (PRD), even when different values share a spot (e.g. species at a bird station). Spreading them was tried (ext-wd #44) and reverted (#46); "One map per value" shows each value on its own.
- [ ] Naibunga `sighting_details` (species) is also a repeating group; not tried yet.

## Example data

- [ ] Add mep-dev test cases:
  - `nest_check` (KBoPT Nest Check): 450 checks, 2017–2025. Main field Species (White-backed Vulture, Martial Eagle…); others Status, Condition, Check Method, Egg/s Chick/s.
  - `wrti_atco` (WRTI Aerial Total Count): 7,501 observations, 2017–2025. Main field Category (Livestock, Settlement, Wildlife, Water); others Type, Plane Registration.
- [ ] Treat "NA" as not applicable (like Unknown / blank). In `nest_check`, "NA" is the largest Species value (191 of 450).
- WD has no good example yet: most v2 forms have 0–3 events, Bird Point Count has 11 and `wd_patrol_info` has 51.
- mep-dev `hwc_rep`, `wildlife_sighting_rep`, `injured_animal_rep` and `fire_rep` have about 400 events each, but their dropdowns are 0–2% filled (test data).

## Known issues

- [x] No events in the period failed the run (`SkipSentinel`); fixed in ext-wd 0.0.10 and the spec (test case `naibungalower-post-report-no-events`). The test suite's "nodata" run only empties data in app mode; `make test` runs CLI mode, so it never caught this.
- [ ] `test_iframes` screenshots for maps and some charts differ between runs, and can hang on WebGL; `make test` leaves them out.
- [ ] `test_otel_traces_success` fails locally, as it does in the incidents workflow (tracing setup).
- [ ] Check in Ecoscope Desktop that unused per-field layout slots disappear and the widgets below move up. This is confirmed from the code (`WorkflowResultsGridLayout.tsx`), not yet seen in the app.

## Against the PRD (not done)

- [ ] Summary grid labels show only "%". The PRD's "56%, n=16" is shown on hover.
- [ ] Follow-up fields are tested on invented data on Naibunga's real Animal Carcass form (4 real carcasses so far).
- Personal fields: only the selected choice fields are read (no notes or free text), and reporter names are left out of the events CSV.
- [ ] PRD "potential additions": encounter rates, seasonality, completeness by field, change between two periods, distinct subjects, report document.
