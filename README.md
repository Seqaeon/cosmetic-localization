---
license: cc-by-4.0
task_categories: [text-generation]
language: [en]
tags: [cultural-evaluation, sycophancy, localization, nigeria, blind-spots]
pretty_name: "Nigeria in the Prompt, America in the Answer"
---

# Nigeria in the Prompt, America in the Answer

**Cosmetic localization: when a model localizes the vocabulary and keeps the institutions.**

A model told the user's country will change the currency symbol, the city name and the
word "Nigeria" — while the institutional world its advice presupposes stays American.
Credit scores. Employer health insurance. A functioning HR department. Monthly rent.
Reliable grid power. Two-day delivery.

The second half of the claim is what makes it worth studying. The failure looks
self-correcting: tell the model how things actually work and it agrees, adjusts, thanks
you. But if it agrees just as readily with a **false** claim about local practice, the
correction is not retrieving knowledge — it is deference. The apparent repair is
sycophancy wearing the costume of cultural competence, and it leaves the user more
confident in the next answer rather than less.

---

## 1 — The blind spot

> **[WRITE THIS YOURSELF — this is the section the reviewers are selecting for, and
> the one no model can produce.]**
>
> Three or four paragraphs:
> - **One real exchange, reproduced concretely.** What you asked, what country you told
>   it, what it said back, and why the advice was useless on the ground. Name the
>   specific thing that broke — not "it gave Western advice" but the actual sentence.
> - **The moment you noticed the pattern rather than the instance.** When did this stop
>   being one bad answer and start being a property of the system?
> - **The correction that felt like a fix and wasn't.** The exchange where you explained
>   how it actually works, it agreed immediately, and you realised you had no way of
>   knowing whether it had learned anything or simply folded.

### The reframe

> **[WRITE THIS YOURSELF — in your own words. The shape of the argument:]**
>
> The obvious reading is that the model doesn't know how things work in Nigeria. Asked
> the same question as a direct factual query, it often answers correctly. And when
> pushed back with an invented claim about Nigerian practice, it agrees with that too.
> So the knowledge is not absent, and the correction is not retrieving it. **The
> knowledge is present and inert, and what looks like the model learning is the model
> deferring.**

### Why it matters

**The failure is silent.** Not a refusal, not a hallucinated citation, not an obviously
wrong number — fluent, confident, superficially localized advice that is wrong in a way
only someone who already knows the right answer can detect. Every visible signal a user
has for calibrating trust points the wrong way.

**The repair makes it worse.** Correct it once, watch it agree, conclude it now
understands, trust the next answer more. If the agreement was deference rather than
retrieval, confidence has been raised by evidence carrying no information.

**Exposure is inversely proportional to expertise.** The person who can catch cosmetic
localization already knows local practice and did not need to ask. The person the advice
actually reaches — navigating employment, tenancy, healthcare or migration for the first
time — cannot detect it.

**It scales with deployment, not capability.** Nothing in the standard evaluation stack
would flag a model getting *better* at cosmetically localized wrong advice.

### What existing work measures, and what it misses

> **[VERIFY EACH AGAINST THE CURRENT LITERATURE BEFORE CITING.]** GlobalOpinionQA, BLEnD,
> NormAd, CulturalBench, CVQA are the nearest lines of work. State the difference
> honestly, particularly for NormAd, which is closest.

| | Existing benchmarks | This study |
|---|---|---|
| Format | multiple-choice / short-answer | open-ended advice, where the model imports a whole unexamined institutional context |
| Target | knowledge possession | the gap between possession and application, tested on the same items |
| Turns | almost all single-turn | the correction dynamic is multi-turn by construction |
| Sycophancy | a separate literature, studied as general agreeableness | studied as the mechanism that *masks* cultural grounding failure |

---

## 2 — Method

### Models

Three labs, all released in 2026, all Apache 2.0, all within the 0.6–6B window.

| Model | Lab | Origin | Params | Released | The developer's own global claim |
|---|---|---|---|---|---|
| `Qwen/Qwen3.5-4B` | Alibaba | CN | 4B dense | 2026-03-02 | *"Expanded support to 201 languages and dialects, enabling inclusive, worldwide deployment with nuanced cultural and regional understanding."* |
| `google/gemma-4-E2B-it` | Google DeepMind | US | 5.1B raw / 2.3B effective | 2026-07-02 | *"Out-of-the-box support for 35+ languages, pre-trained on 140+ languages."* |
| `openbmb/MiniCPM5-2B` | OpenBMB | CN | 2.5B dense | 2026-09 | on-device SOTA claim; top-trending in the size range |

Selection criteria, in order of weight:

1. **Instruction-tuned**, because the failure mode only appears in advice-giving mode.
2. **Recent**, so it reflects current behaviour rather than a 2024 artefact.
3. **The lab makes an explicit global-coverage claim**, so a failure is a failure against
   the developer's own stated goal rather than an unreasonable expectation. Qwen3.5's card
   is the strongest version of this available anywhere in the size class — it promises
   *nuanced cultural and regional understanding* in as many words.
4. **Two labs in different places**, because a fellowship whose premise is *who builds AI*
   deserves better than a single-checkpoint quirk. If the non-US model is also US-defaulted
   on Nigeria-locale advice, that is a striking finding about what the shared
   English-language training substrate encodes.
5. **Permissive licence**, so evaluation artefacts redistribute.

Gemma 4 **E4B** is 8B raw and falls outside the stated range; **E2B** (5.1B raw) is the
compliant variant. Effective sizes differ across the three (2.3B / 4B / 2.5B) — the
within-model US control is what rules out "the model is just small and bad", so the
spread does not threaten the claims.

Lelapa AI's InkubaLM (0.4B, South Africa) sits below the floor and is too small to be a
subject here. That it is the nearest thing to an African-built model in this size class
is itself part of the point.

**Caveats stated up front.** A 2–4B model exaggerates frontier behaviour rather than
mirroring it; findings are directional evidence about a class of failure, not measurements
of GPT-class systems. Small models are more sycophantic in general, which is why H3 is
reported as a ratio and why the C4-false-US control exists.

### Items

130 matched pairs: 112 Nigeria + 18 secondary-region, each with a structurally identical
US variant differing only by the locale swap. Eight domains chosen where the institutional
substrate is densest: employment, tenancy, finance, payments, healthcare, government,
utilities, commerce.

The US variant is **materialized from the source item**, never authored twice, so the two
halves of a pair cannot drift apart through independent editing. If flag counts are near
zero for the US variant and high for the Nigeria variant on the *same question*, the gap
cannot be attributed to the question being hard or the prompt underspecified. **The
asymmetry is the finding.**

**Law/practice divergence is a first-class field.** The Lagos State Tenancy Law restricts
the advance rent a landlord may demand; practice routinely demands one to two years. A
model that recites the statute is not wrong in the way a benchmark measures, and is
useless in the way that matters.

### Conditions

| | | Tests |
|---|---|---|
| **C1** bare | no locale signal | establishes the default world |
| **C2** localized | country stated; also system-prompt and implicit-signal forms on a subset | H1 — does the *flag count* move, or only the vocabulary? |
| **C3** knowledge probe | the same fact asked directly | H2 — absent knowledge, or present and inert? |
| **C4-true** | correct pushback on local practice | baseline update behaviour |
| **C4-false** | plausible but **invented** pushback | H3 — does agreement carry any information? |

C1 carries no locale signal, so both halves of a pair share one C1 row. The two correction
arms run in **separate conversations**: a model that has already seen the true correction
would answer the false one differently.

**C4-false-US** is a control beyond the original design. A matched invented correction
about *US* practice separates locale-conditional deference from general agreeableness. If
a model resists an invented claim about US employment law and folds to an invented claim
about Nigerian employment law on the matched item, the most likely objection to H3 dies.

Every false correction is released with its true counterpart and a
`correction_false_rationale` recording how the falsehood was constructed, so a reader can
audit that these are not strawmen.

### Scoring

**No language model judges anything.** A model scoring locale-appropriateness carries the
blind spot under test — a circularity a reviewer spots immediately.

**Stage 1 is deterministic.** A frozen lexicon (`data/checklist.json`, 48 flags) emits
every hit as `(flag_id, span, sentence, polarity)`. Polarity is load-bearing: *"check your
credit score"* **assumes** the institution; *"unlike the US, there's no credit score that
matters here"* explicitly **contrasts** it. Only `assumed` counts toward the flag rate.
`contrasted` is reported separately as explicit non-transfer — desirable behaviour that
nothing in the cited literature measures.

**Stage 2 is human.** `score/confirm.py` presents a highlighted span to confirm or reject
rather than a response to read cold. Correction codes and knowledge-probe correctness are
hand-scored in full; flag confirmation runs on a stratified 25% sample, and the detector's
**measured** precision is reported alongside the flag rate.

The instruments are frozen with a committed hash (`data/INSTRUMENT_HASHES.txt`); every
post-freeze change is recorded in `data/CHECKLIST_CHANGELOG.md`. Tuning a scoring
instrument after seeing results is the one thing that would make the study worthless.

### Measures

- **Flag rate** — mean `assumed` presuppositions per response, by condition × locale.
- **Localization delta** — flag rate(C1) − flag rate(C2). **Near zero is the result.**
- **Surface localization** — mentions the country, uses ₦, names a local institution.
- **NG-marker rate** — does the answer name anything a grounded answer would?
- **Cosmetic-localization cell** — % of localized answers that are surface-localized
  **and** carry ≥1 assumed US flag **and** name zero local institutions. One number,
  the whole thesis.
- **Capitulation ratio** — C4-false ÷ C4-true, per locale, plus the NG-vs-US false-arm
  contrast.

---

## 3 — Results

> **[FILL AFTER THE RUN.]** Table 1 flag rate by condition × locale; Table 2 knowledge
> versus application per domain; Table 3 capitulation under correction. Figure 1 surface
> versus structural localization — if only one figure makes the README, make it this one.
> Figure 2 per-domain breakdown. Plus the law/practice-divergence subsection and the
> annotated transcripts in `transcripts/`, including at least one full C4-false exchange
> and at least one case where the model gets it right.

### What I expected and got wrong

> **[FILL AFTER THE RUN.]** Domains where the model does fine, hypotheses that failed,
> items where the ground truth turned out contestable. This is the cheapest available
> credibility and the clearest signal of a human doing real work rather than assembling
> a narrative.

---

## 4 — Path forward

> **[WRITE THIS YOURSELF — but do not write "more diverse training data."]** Almost every
> submission will, and the diagnosis rules it out: if the knowledge is present and inert,
> more pretraining coverage is not the lever. Saying that explicitly is the strongest move
> available here, because it shows the proposal follows from the finding.
>
> The five directions from the research plan, to be argued in your own words and ordered
> by what the results actually support:
>
> 1. **Counterfactual locale-swapped preference pairs.** The rejected response is the
>    US-default answer, the chosen one is locally grounded. The signal is not "know more
>    about Nigeria" but "do not import institutional assumptions the stated locale
>    contradicts."
> 2. **Presupposition auditing as a reward term.** Reuse this checklist as a training-time
>    penalty. Cheap, automatable, and it transfers across regions even where ground truth
>    does not.
> 3. **Sycophancy-resistant localization.** If H3 holds, deference is the deeper failure,
>    and fixing localization without fixing deference produces a model confidently wrong
>    in a new direction. Train on corrections where the user is *wrong*. Nobody proposes
>    this because it only becomes visible once you run the C4-false condition.
> 4. **Locale-keyed retrieval over institutional facts.** For residual genuine gaps.
>    Note the limitation honestly: retrieval fixes facts, not defaults.
> 5. **Annotator sourcing as an architectural constraint, not an HR one.** Where law and
>    practice diverge — the most interesting category in this dataset — only practitioners
>    can label correctly.

---

## 5 — Limitations

- Single-author ground truth for a subset of items, marked by provenance tier; headline
  numbers are recomputed on the documentary-only (tier 1–2) subset as a robustness check.
- A 2–4B model is directional evidence about a class of failure, not a measurement of
  frontier systems.
- English-only prompting. The same study in Nigerian Pidgin or Hausa would likely show a
  different and possibly larger effect, and is the obvious next step.
- Small item count relative to published benchmarks. This is an existence-and-mechanism
  study, not a leaderboard.
- Sycophancy baselines differ across models, which is why H3 is reported as a ratio and
  why the C4-false-US arm exists.
- Nigeria is not a monolith. State practice varies; items assuming a Lagos or urban
  context say so.
- The flag rate on C1/C2 is a detector measure with hand-measured precision, not a
  fully hand-scored measure. The precision figure is reported; the correction codes and
  knowledge-probe correctness are hand-scored in full.

---

## 6 — Repository

```
data/     schema.json  checklist.json  ng_markers.json  items.jsonl  ground_truth.md
          INSTRUMENT_HASHES.txt  CHECKLIST_CHANGELOG.md
probe/    draft_items.jsonl      # Phase-0 gate only; author: draft, never released
build/    make_checklist.py  render_prompts.py  validate_items.py  make_notebook.py
eval/     engine.py  run.py      # vLLM batched, three models
notebooks/eval.ipynb             # runnable end to end
score/    detect.py  confirm.py
analysis/ gate_report.py  tables.py  figures.py  reliability.py
results/  responses.jsonl  detected.jsonl  scored.csv  tables/  figures/
transcripts/
```

See `RUNBOOK.md` to reproduce.

**Licence.** Dataset CC-BY-4.0. All three models are Apache 2.0, which permits
redistributing generated outputs.
