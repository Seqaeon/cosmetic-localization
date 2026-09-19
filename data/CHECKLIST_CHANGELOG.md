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

## 1.0.1 — 2026-09-19 — sentence splitter bug fix

**No pattern file changed.** `checklist.json` and `ng_markers.json` carry the same
hashes as 1.0.0. This entry covers `score/detect.py`, which is now hashed alongside
them, because the sentence splitter decides which contrast cues reach which triggers
and therefore changes flag counts as surely as the patterns do.

**What broke.** `split_sentences` masked non-terminal periods by substituting a whole
sentinel token for the matched abbreviation, padding with spaces to preserve length.
Where the token was longer than the text it replaced — `"U.S."` is 4 characters,
`"\x01USDOT\x01"` is 8 — the pad count went negative, `" " * -4` produced the empty
string, and every subsequent offset shifted. The guard assertion fired:
`AssertionError: masking must preserve offsets`.

It survived the 1.0.0 self-test because not one of the 74 content fixtures contained
an abbreviation. It surfaced on the first batch of real model responses.

**Fix.** Masking now swaps individual `.` characters in place, one character for one
character, so length preservation is structural rather than arithmetic. The
abbreviation list was widened (`U.K.`, `E.U.`, titles, months, `a.m./p.m.`, statute
references such as `s. 11` and `ss. 13-16`, numbered list markers) and one alternation
was corrected: each branch now stops before the terminal period, which `U.S.` had
been consuming.

**Known limitation, deliberately accepted.** An abbreviation at a genuine sentence end
is ambiguous without a parser — `"in the U.S. Americans pay..."` must not split,
`"in the U.S.A. Here it is..."` should. The splitter under-splits. Merging two
sentences lets a contrast cue in the first excuse a trigger in the second, resolving
`assumed` to `contrasted` and **under-counting** flags. That is the direction that
makes the headline claim harder to support, not easier. Stage-2 human confirmation
catches the residue.

**Scoring impact: none.** The crash occurred on the first detection pass over real
responses, so no response had been scored under the old splitter. No figure in the
study derives from it.

**Regression cover added.** 14 splitter fixtures, plus a randomized property check
asserting every returned span indexes back into the source string unchanged (3000
paragraphs, 0 mismatches). Self-test is now 88 checks.
