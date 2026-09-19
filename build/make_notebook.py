#!/usr/bin/env python3
"""Generate notebooks/eval.ipynb. Kept as a generator so the notebook is
diffable and never hand-edited into drift with eval/engine.py."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _lines(src: str) -> list[str]:
    """nbformat wants each source line to END with a newline (last one optional).
    Splitting on "\\n" drops them and the whole cell renders as one line."""
    return src.splitlines(keepends=True)


def md(src): return {"cell_type": "markdown", "metadata": {},
                     "source": _lines(src.strip())}


def code(src): return {"cell_type": "code", "execution_count": None, "metadata": {},
                       "outputs": [], "source": _lines(src.strip("\n"))}


CELLS = [
md("""
# Nigeria in the Prompt, America in the Answer — evaluation run

Measures **cosmetic localization**: whether stating the user's country changes the
institutional world a model's advice presupposes, or only its vocabulary.

Four conditions per item, three models, matched Nigeria/US pairs:

| | |
|---|---|
| **C1** bare | no locale signal — establishes the model's default world |
| **C2** localized | same question, country stated — does the *flag count* move, or only the words? |
| **C3** knowledge probe | the same fact asked directly — separates absent knowledge from inert knowledge |
| **C4-true / C4-false** | user pushes back with a correct, then an invented, claim about local practice |

C4-false is the load-bearing control. If a model capitulates to an invented claim about
Nigerian practice as readily as to a true one, then agreement carries no information, and
what a user experiences as the model learning is the model deferring.

**Runs on a single H200.** All three models are loaded one at a time; nothing here needs
more than ~12 GB at a time.
"""),

md("## 1 — Environment"),
code("""
# Pinned so a rerun reproduces. vLLM must be recent: two of the three checkpoints
# are 2026 architectures. If vLLM refuses a model, engine.py falls back to HF
# generate automatically -- slower, irrelevant on an H200.
!pip -q install -U "transformers>=4.57" "accelerate>=1.0" "vllm>=0.11" "huggingface_hub>=0.26" pandas
"""),
code("""
import subprocess, sys, pathlib, os, json
print(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv"],
                     capture_output=True, text=True).stdout)
import torch, transformers
print("torch", torch.__version__, "| cuda", torch.cuda.is_available(), "| transformers", transformers.__version__)
"""),
code("""
# Point this at the repo. Either clone it or mount it -- the notebook only needs
# the data/, build/, eval/ and score/ directories.
REPO = pathlib.Path(os.environ.get("COSLOC_REPO", "/workspace/cosmetic-localization"))
assert REPO.exists(), f"set COSLOC_REPO or clone the repo to {REPO}"
os.chdir(REPO)
sys.path[:0] = [str(REPO / "eval"), str(REPO / "score")]
print("repo:", REPO)
"""),

md("""
## 2 — Verify the instruments are the frozen ones

The scoring instruments are frozen with a committed hash. Tuning a scoring
instrument after seeing results is the one thing that would make this study
worthless, so the run refuses to start against an unrecorded version.
"""),
code("""
import hashlib
recorded = {}
for line in (REPO / "data/INSTRUMENT_HASHES.txt").read_text().splitlines():
    if line.startswith("#") or not line.strip():
        continue
    name, _, digest = line.split()[0], None, line.split("sha256=")[1]
    recorded[name] = digest

for name, digest in recorded.items():
    actual = hashlib.sha256((REPO / "data" / name).read_bytes()).hexdigest()
    status = "ok" if actual == digest else "MODIFIED"
    print(f"{status:9s} {name}")
    assert actual == digest, (
        f"{name} does not match the frozen hash. If the change is intended, record it in "
        f"data/CHECKLIST_CHANGELOG.md with a reason and regenerate INSTRUMENT_HASHES.txt.")

!python score/detect.py --self-test
"""),

md("""
## 3 — Build the run manifest

`PHASE = "gate"` runs the 24 machine-drafted probe pairs, whose only job is to decide
whether the effect is there before any authoring cost is paid. Their numbers never appear
in the paper and `validate_items.py --release` refuses to ship them.

`PHASE = "study"` runs the authored dataset.
"""),
code("""
PHASE = "gate"      # "gate" | "study"
SAMPLES = 3         # per cell; small models are noisy and one sample per cell is the
                    # easiest thing for a reviewer to distrust
SEED = 0

if PHASE == "gate":
    !python probe/make_drafts.py
    SRC, ITEMS, MANIFEST = "probe/draft_items.jsonl", "probe/draft_items_paired.jsonl", "probe/gate_manifest.jsonl"
else:
    SRC, ITEMS, MANIFEST = "data/items_src.jsonl", "data/items.jsonl", "results/manifest.jsonl"

!python build/render_prompts.py --items {SRC} --out-items {ITEMS} --out-manifest {MANIFEST} --samples {SAMPLES} --seed {SEED}
!python build/validate_items.py --items {ITEMS} {"" if PHASE == "gate" else "--release"}
"""),

md("""
## 4 — Smoke test

Two items, one model, one sample. Catches the things that silently ruin a full run:
a chat template that rejects a system turn, Qwen's thinking traces leaking into the
response text, truncation mid-sentence, a refusal.

Read the output. Do not skip this.
"""),
code("""
from engine import MODELS, RunConfig, run
for k, v in MODELS.items():
    print(f"{k:14s} {v['hf_id']:28s} {v['lab']:18s} {v['origin']}  {v['params']}")
"""),
code("""
smoke = RunConfig(models=["qwen3.5-4b"], manifest=REPO / MANIFEST,
                  out=REPO / "results/smoke.jsonl", samples=1, seed=SEED, limit=2)
run(smoke)

import itertools
for line in itertools.islice(open(REPO / "results/smoke.jsonl"), 4):
    r = json.loads(line)
    print(f"\\n--- {r['item_id']} {r['condition']} [{r['locale']}] " + "-" * 40)
    print(r["response"][:700])
"""),

md("""
## 5 — Full run

Three models, all conditions, three samples. Models load sequentially and the GPU is
released between them.
"""),
code("""
cfg = RunConfig(models=list(MODELS), manifest=REPO / MANIFEST,
                out=REPO / f"results/responses_{PHASE}.jsonl",
                samples=SAMPLES, seed=SEED, temperature=0.7,
                extra={"gpu_memory_utilization": 0.85})
run(cfg)
"""),

md("""
## 6 — Determinism check

"Fixed seed" should be a verified claim, not a stated one. Re-runs one cell at
temperature 0 and asserts the output is byte-identical.
"""),
code("""
det = RunConfig(models=["qwen3.5-4b"], manifest=REPO / MANIFEST,
                out=REPO / "results/_det_a.jsonl", samples=1, seed=SEED,
                temperature=0.0, limit=2)
run(det)
det.out = REPO / "results/_det_b.jsonl"
run(det)

a = [json.loads(l)["response"] for l in open(REPO / "results/_det_a.jsonl")]
b = [json.loads(l)["response"] for l in open(REPO / "results/_det_b.jsonl")]
same = sum(x == y for x, y in zip(a, b))
print(f"identical: {same}/{len(a)}")
if same != len(a):
    print("NOT deterministic at temperature 0 -- report this rather than claiming a fixed seed.")
"""),

md("""
## 7 — Stage-1 detection

Deterministic. The frozen lexicon emits every checklist hit with its span, its
sentence, and a polarity: `assumed` (the answer builds on the institution) versus
`contrasted` (the answer explicitly says it does not apply here). Only `assumed`
counts toward the flag rate — treating explicit non-transfer as a failure would be
the worst available scoring bug.

No model judges anything. A model scoring locale-appropriateness carries the blind
spot under test.
"""),
code("""
!python score/detect.py --in results/responses_{PHASE}.jsonl --out results/detected_{PHASE}.jsonl
"""),

md("""
## 8 — Preliminary gate read

**These numbers are not results.** They are detector-only, the items are machine-drafted,
and G2 and G3 need hand-coding before they mean anything. This cell answers one question:
is there enough signal to justify authoring 242 items?
"""),
code("""
!python analysis/gate_report.py --detected results/detected_{PHASE}.jsonl
"""),

md("""
## 9 — Export for human scoring

Writes the queues `score/confirm.py` works through: C4 correction codes and C3
correctness in full, C1/C2 flag confirmation on a stratified 25% sample.

Confirming a highlighted span takes about five seconds. Scoring a response cold takes
about forty. That difference is what makes ~12 hours of scoring finishable instead of ~50.
"""),
code("""
!python score/confirm.py --build-queues --detected results/detected_{PHASE}.jsonl --out score/queues
!ls -la score/queues
"""),
]

nb = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
    },
    "nbformat": 4, "nbformat_minor": 5,
}
out = ROOT / "notebooks" / "eval.ipynb"
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {out.relative_to(ROOT)}  ({len(CELLS)} cells)")
