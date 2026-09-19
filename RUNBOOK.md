# Runbook

## Phase 0 — the thesis-validation gate

The point of this phase is to find out whether the effect is there **before** paying the
cost of authoring 242 items. The 24 probe pairs are machine-drafted, carry
`author: "draft"`, and are barred from the released dataset by
`build/validate_items.py --release`. None of their numbers go in the paper.

### Locally (no GPU) — verify the plumbing

```bash
PY=/home/seqaeon/Downloads/venv/bin/python

$PY score/detect.py --self-test                    # 74 fixtures, must pass
$PY probe/make_drafts.py
$PY build/render_prompts.py --items probe/draft_items.jsonl \
      --out-items probe/draft_items_paired.jsonl \
      --out-manifest probe/gate_manifest.jsonl --samples 3 --seed 0
$PY build/validate_items.py --items probe/draft_items_paired.jsonl
$PY build/validate_items.py --items probe/draft_items_paired.jsonl --release   # MUST fail

# exercise the full chain on canned text, no GPU
cd eval && $PY run.py --manifest probe/gate_manifest.jsonl \
      --out results/responses_dryrun.jsonl --backend dryrun --samples 1 && cd ..
$PY score/detect.py --in results/responses_dryrun.jsonl --out results/detected_dryrun.jsonl
$PY analysis/gate_report.py --detected results/detected_dryrun.jsonl
```

### On the H200

```bash
git clone <repo> /workspace/cosmetic-localization
cd /workspace/cosmetic-localization
pip install -U -r requirements.txt
export COSLOC_REPO=/workspace/cosmetic-localization
jupyter lab notebooks/eval.ipynb      # or run headless below
```

Headless equivalent:

```bash
python score/detect.py --self-test
python probe/make_drafts.py
python build/render_prompts.py --items probe/draft_items.jsonl \
      --out-items probe/draft_items_paired.jsonl \
      --out-manifest probe/gate_manifest.jsonl --samples 3 --seed 0

# smoke test FIRST -- read the output before launching the full run
cd eval && python run.py --manifest probe/gate_manifest.jsonl \
      --out results/smoke.jsonl --models qwen3.5-4b --samples 1 --limit 2 && cd ..
```

What to look for in the smoke output, in order of how badly it ruins a run:

1. **Qwen thinking traces in the response text.** `engine.py` sets
   `enable_thinking=False`; if traces appear anyway, the template ignored it and every
   flag count downstream is contaminated. Stop and fix before continuing.
2. **Gemma rejecting the system turn.** `supports_system=False` folds it into the first
   user turn. Confirm the system-signal rows actually carry the locale.
3. **Truncation mid-sentence.** Raise `MAX_TOKENS` in `engine.py`.
4. **Refusals or empty responses.** Note which items; they are a finding, not a bug.

Then the full run:

```bash
cd eval && python run.py --manifest probe/gate_manifest.jsonl \
      --out results/responses_gate.jsonl --samples 3 --seed 0 \
      --gpu-memory-utilization 0.85 && cd ..
python score/detect.py --in results/responses_gate.jsonl --out results/detected_gate.jsonl
python analysis/gate_report.py --detected results/detected_gate.jsonl
```

### Scoring the gate (~2 hours)

```bash
python score/confirm.py --build-queues --detected results/detected_gate.jsonl \
      --items probe/draft_items_paired.jsonl
python score/confirm.py --queue c4_codes      # the headline; do this one first
python score/confirm.py --queue c3_correct
python score/confirm.py --queue flags
python score/confirm.py --report
```

Resumable — decisions append to `score/decisions/` and finished rows are skipped.

### Gate decision

| | Criterion | Passes if |
|---|---|---|
| **G1** | cosmetic localization | surface localization on C2-local > 70% **and** localization delta < 0.5 flags, on ≥2 of 3 models |
| **G2** | knowledge/application gap | C3 correct − C2 grounded ≥ 25 points, on ≥2 of 3 models |
| **G3** | uninformative repair | C4-false capitulation ≥ 0.6 × C4-true, on ≥2 of 3 models |
| **G4** | region-conditional | matched C2-US responses near-clean |

**≥2 pass** → author all 130 pairs. **Only G1** → go, but narrow the paper to cosmetic
localization and drop the sycophancy framing. **Zero** → stop and rethink before writing
a single item.

The gate runs on machine-drafted prompts, which may themselves be US-inflected and could
bias the result either way. It is directional evidence about whether to proceed, not a
result.

## Phase 1 — the study

Only past the gate.

1. Rewrite the 24 gate drafts in your own voice; verify each ground truth against the
   cited source. Author the remaining 106 pairs into `data/items_src.jsonl`.
2. `python build/validate_items.py --items data/items.jsonl --release` must pass. It
   refuses while any row is `author: draft`, any `gt_tier` is missing, any pair lacks its
   US variant, any pair's prompts diverge past the locale swap, or any false correction
   is a near-restatement of its true counterpart.
3. Recalibrate the detector against the authored ground-truth text, record the change in
   `data/CHECKLIST_CHANGELOG.md`, regenerate `INSTRUMENT_HASHES.txt`, re-run
   `--self-test`.
4. Pilot 10 authored pairs end to end, then the full run.
5. Score per the budget in the README.
6. Tables, figures, transcripts, README.
