# Instrument changelog

The scoring instruments (`checklist.json`, `ng_markers.json`) are frozen. Tuning a
scoring instrument after seeing results would make the study worthless, so every
change after the freeze point is recorded here with a reason, and hashes in
`INSTRUMENT_HASHES.txt` are regenerated.

## 1.0.0 — 2026-09-19 — FROZEN

48 presupposition flags across 8 categories; 35 Nigerian institutional markers;
surface-localization patterns for country mention and currency.

Calibration before freeze: patterns were written from the research plan's
checklist table plus domain knowledge, then validated against 74 hand-labelled
fixtures in `score/detect.py` (30 `assumed`, 12 `contrasted`, 5 must-not-fire,
25 marker, 2 cosmetic-cell). One pre-freeze correction: `house.monthly_rent`
did not fire on the predicative form ("rent is rarely paid monthly"), only the
attributive ("monthly rent"); proximity triggers were added. No result had been
observed at that point — no model had been run.

Post-freeze changes: none.
