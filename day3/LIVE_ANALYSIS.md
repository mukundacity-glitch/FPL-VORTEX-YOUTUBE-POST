# Day 3 live analysis

Each existing Day 3 execution collects fresh official FPL player identities,
selection eligibility, availability, prices, fixtures and per-player match history.
It reads FPL-linked club updates, follows relevant primary-source news links,
and searches recent credible press reports for every current club. Coverage,
source URLs, timestamps and failures are saved in `DATA/live_analysis_evidence.json`.

News prose is a report to reconcile, never automatic medical clearance. A fresh
report about a player's availability or role makes that player conditional until
the evidence is resolved. Failed research is recorded as unknown. The collector
uses current FPL identities and unique name matches; there are no player or club
exception lists. Trusted press domains identify source provenance only.

Current-club official starts replace stale Core league lineups in the minutes
forecast. Historical statistics remain descriptive. Active recommendations need
verified availability, a target fixture, sufficient starting/minutes evidence,
matching current identity and position, and complete valid fixture projections.
Transferred players cannot borrow starting evidence from their previous club.

The official scoring table supplies the positional DC thresholds and awards.
DEFCON targets rank by projected DC points and observed threshold-hit rate;
season totals are a later comparison. Five analysis cards may include clearly
labeled historical watchlist entries when fewer than five targets qualify.
`DAY3_DEFCON_RECOMMENDATIONS` contains only the eligible subset. Unknown forecasts
display as an em dash and are never narrated as zero. Team totals describe
workload, not defensive quality or guaranteed individual awards.

`day3.run_validated` runs the existing notebook and rechecks evidence afterward.
A material change regenerates recommendations, narration and graphics, with a
bounded retry. The uploader performs another check before its existing private
upload. Changed rendered files or unresolved evidence changes prevent upload.
The artifact manifest ties the check to the actual generated files. Continuously
changing transfer counts alone do not invalidate a render; changed market ranks,
availability, identity, prices, fixtures, statistics or relevant reports do.

No schedules, workflow triggers, manual transfer inputs, Ryan settings or render
settings are changed. Drive notebooks remain read-only runtime inputs.
