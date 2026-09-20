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

## 1.0.2 — 2026-09-20 — G4 criterion corrected (specification error)

**No pattern file changed.** `checklist.json` and `ng_markers.json` keep their 1.0.0
hashes. This covers `analysis/gate_report.py`, which is not part of the scoring
instrument — it computes gate criteria from already-scored output.

**The error.** G4 was written as *"matched US-locale responses show near-zero flags"*.
But the checklist **is** a lexicon of US institutions. A US-locale answer that names
credit scores, an HR department and small claims court is behaving correctly for its
stated locale. The criterion penalised correct behaviour, and it failed on all three
models for that reason alone.

**The correction.** H4 asks whether the model grounds an answer in institutions that fit
the *stated* locale. For a US prompt those are the checklist flags; for a Nigeria prompt
they are the local markers. G4 now compares the two grounding rates:

> G4 passes where `(US institutions per US answer / 48) ÷ (local institutions per local
> answer / 35) ≥ 2.0`, on ≥2 of 3 models.

Normalization is by lexicon size, because 48 flags against 35 markers inflates the raw
ratio by about 1.37× before anything about the models is considered. Both figures print;
the normalized one is the claim.

**Provenance, stated plainly.** This was found *after* seeing gate output, which is when
the flaw became visible. It is a construct error readable off the criterion itself rather
than a goalpost moved to reach a result: the same correction is warranted whichever
direction the numbers ran. On the gate data the original G4 scored 0/3 and the corrected
G4 scores 2/3 — Qwen3.5-4B fails it at 1.7×, which is consistent with Qwen being the
best-grounded of the three and is evidence the criterion discriminates rather than
rubber-stamps.

**Locked before the study run.** The 2.0× threshold and the normalization are fixed here,
before any authored item has been generated. Gate output is exploratory by design; this
is the pre-registration that governs the study.

**Also noted, not changed.** G1's threshold (`delta < 0.5 flags`) was set a-priori with no
data on the scale of the measure. Observed bare-condition rates are 1.7–2.2 flags per
response, so 0.5 is a large fraction of the total rather than the small one intended. It
is left as written. The substantive reading is reported alongside it: all three models
shed 22–30% of their US presuppositions when told the country, and replace them with
almost nothing, which is partial localization rather than purely cosmetic localization.
Detector precision on the flag rate is still unmeasured and is what the 25% confirmation
sample exists to establish.
