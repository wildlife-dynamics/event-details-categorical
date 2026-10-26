# TODO

Open work for the Event Details - Categorical Field workflow. Background is in `PLAN.md`.

## Release

- [x] Merge wd-partner-tasks PRs #40, #42 (categorical) and #41 (incidents).
- [x] Tag `wd-v0.0.6` and publish it to prefix.dev (2026-10-26). One release covers both workflows.
- [x] Point `spec.yaml` at ext-wd 0.0.6 on `https://repo.prefix.dev/ecoscope-workflows-custom/` and remove the `/tmp` file channel from `pixi.toml`.
- [ ] Run `make recompile`, `make test` and `make run`, then commit and push this repo. Leave out `wt-compiler-env-overrides.toml`, the `make dev` output and `.scripts/outputs/`.

## Configuration page

- [ ] Simplify the form. One **Fields** list where the first field is the main one (closer to the PRD), with Cross-tabs moved to Advanced.
- [ ] Rewrite the field descriptions in plain words (proposed wording is in the chat of 2026-10-22).
- [ ] Field dropdowns instead of typed names, once Alex's ecoscope-server change lets EarthRangerEnumResolver list categorical fields (`PLAN.md` §3, phase 2).

## Repeating groups (e.g. WD Bird Point Count)

- [ ] Support questions inside a repeating group. On WD `bird_point_count`, **Detection** is a list of rows (one per bird) holding Species, Distance band, Time interval, Detection type, Flyover and Inside corridor (all dropdowns), plus Count and Other species.
  - One detection = one record, so "Species" counts detections, and cross-tabs like Species × Distance band work.
  - Field names like `Detection: Species`.
  - Also covers naibungalower `sighting_details` (species).
  - About a day plus tests.
- [ ] Until then, Bird Point Count only works on the survey fields: Station, Round, Cloud Cover, Wind (Beaufort) and Rain. Only 11 counts so far (1-21 Oct 2026).

## Example data

- [ ] Add mep-dev test cases:
  - `nest_check` (KBoPT Nest Check): 450 checks, 2017–2025. Main field Species (White-backed Vulture, Martial Eagle…); others Status, Condition, Check Method, Egg/s Chick/s.
  - `wrti_atco` (WRTI Aerial Total Count): 7,501 observations, 2017–2025. Main field Category (Livestock, Settlement, Wildlife, Water); others Type, Plane Registration.
- [ ] Treat "NA" as not applicable (like Unknown / blank). In `nest_check`, "NA" is the largest Species value (191 of 450).
- WD has no good example yet: most v2 forms have 0–3 events, Bird Point Count has 11 and `wd_patrol_info` has 51.
- mep-dev `hwc_rep`, `wildlife_sighting_rep`, `injured_animal_rep` and `fire_rep` have about 400 events each, but their dropdowns are 0–2% filled (test data).

## Known issues

- [ ] App-mode test (`app-sequential-mock-io`): `trends_main_widget` got a skipped title (`main_over_time_title` was skipped). `make test` only runs the CLI mode, so this isn't covered.
- [ ] `test_iframes` screenshots for maps and some charts differ between runs.
- [ ] `test_otel_traces_success` fails locally, as it does in the incidents workflow (tracing setup).
- [ ] Check in Ecoscope Desktop that unused per-field layout slots disappear and the widgets below move up. This is confirmed from the code (`WorkflowResultsGridLayout.tsx`), not yet seen in the app.

## Against the PRD (not done)

- [ ] Group by quarter. The platform's time grouper has no quarter.
- [ ] Summary grid labels show only "%". The PRD's "56%, n=16" is shown on hover.
- [ ] Parent and child fields (e.g. cause of death after "Poached") are untested, because no test site has one.
- [ ] Personal fields: only reporter names are left out of the events CSV.
- [ ] PRD "potential additions": encounter rates, seasonality, completeness by field, change between two periods, distinct subjects, report document.
