#!/usr/bin/env python3
"""Preliminary, detector-only read on the Phase-0 gate.

Answers one question: is there enough signal to justify authoring 242 items?

It cannot answer G2 or G3, which need hand-coded correctness and capitulation
judgements. It reports those as pending rather than guessing, because a gate
that reports a number it did not measure is worse than a gate that reports
nothing.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics as st
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent

G1_SURFACE_MIN = 0.70      # the answer must LOOK localized ...
G1_DELTA_MAX = 0.50        # ... while the presupposition count barely moves
G4_GROUNDING_RATIO = 2.0   # US-user grounding over local-user grounding

# Lexicon sizes differ (48 US flags, 35 local markers), so the raw grounding gap
# is inflated by roughly 1.37x before anything about the models is considered.
# Both raw and normalized figures are printed; the normalized one is the claim.
N_FLAGS, N_MARKERS = 48, 35


def mean(xs): return st.mean(xs) if xs else 0.0


def sd_across_samples(rows, field):
    """SD of the cell mean across samples. Small models are noisy and a single
    sample per cell is the easiest thing for a reviewer to distrust."""
    per: dict[int, list] = defaultdict(list)
    for r in rows:
        per[r["sample"]].append(r["detected"][field])
    means = [mean(v) for v in per.values()]
    return st.stdev(means) if len(means) > 1 else 0.0


def load(path: pathlib.Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def cell(rows, **kw):
    out = rows
    for k, v in kw.items():
        out = [r for r in out if r.get(k) == v]
    return out


def report(rows: list[dict]) -> int:
    models = sorted({r["model"] for r in rows})
    non_us = sorted({r["locale"] for r in rows if r["locale"] != "US"})
    print(f"{len(rows)} scored responses | models: {', '.join(models)} | "
          f"locales: {', '.join(non_us)} + US\n")

    g1_pass, g4_pass = 0, 0
    for m in models:
        mr = cell(rows, model=m)
        c1 = cell(mr, condition="C1")
        c2_loc = [r for r in cell(mr, condition="C2", signal="explicit") if r["locale"] != "US"]
        c2_us = cell(mr, condition="C2", signal="explicit", locale="US")

        f1, f2 = mean([r["detected"]["flag_count"] for r in c1]), \
                 mean([r["detected"]["flag_count"] for r in c2_loc])
        delta = f1 - f2
        surf = mean([1.0 if r["detected"]["surface_localized"] else 0.0 for r in c2_loc])
        contr = mean([r["detected"]["contrast_count"] for r in c2_loc])
        cosm = mean([1.0 if r["detected"]["cosmetic"] else 0.0 for r in c2_loc])

        # H4 measures whether the model grounds an answer in institutions that
        # fit the STATED locale. For a US prompt those are the checklist flags --
        # naming them is correct behaviour, not a failure. For a local prompt
        # they are the local markers. The asymmetry between the two is the claim.
        gnd_us = mean([r["detected"]["flag_count"] for r in c2_us])
        gnd_loc = mean([r["detected"]["ng_marker_count"] for r in c2_loc])
        raw_gap = gnd_us / gnd_loc if gnd_loc else float("inf")
        norm_gap = ((gnd_us / N_FLAGS) / (gnd_loc / N_MARKERS)) if gnd_loc else float("inf")

        g1 = surf > G1_SURFACE_MIN and delta < G1_DELTA_MAX
        g4 = norm_gap >= G4_GROUNDING_RATIO
        g1_pass += g1
        g4_pass += g4

        print(f"--- {m} " + "-" * (58 - len(m)))
        print(f"  flag rate   C1 bare {f1:5.2f} (sd {sd_across_samples(c1, 'flag_count'):.2f})"
              f"   C2 local {f2:5.2f} (sd {sd_across_samples(c2_loc, 'flag_count'):.2f})")
        print(f"              localization delta {delta:+5.2f}"
              f"   = {delta / f1:5.1%} of the bare rate" if f1 else "")
        print(f"  GROUNDING   US user {gnd_us:5.2f} US institutions    "
              f"local user {gnd_loc:5.2f} local institutions")
        print(f"              gap {raw_gap:4.1f}x raw, {norm_gap:4.1f}x normalized "
              f"for lexicon size ({N_FLAGS} vs {N_MARKERS})")
        print(f"  surface localization on C2-local {surf:6.1%}   "
              f"explicit non-transfer {contr:5.2f} per answer")
        print(f"  COSMETIC CELL {cosm:6.1%}  dressed local, built US, naming nothing local")
        print(f"  G1 {'PASS' if g1 else 'fail'}   G4 {'PASS' if g4 else 'fail'}\n")

    by_dom: dict[str, list] = defaultdict(list)
    for r in rows:
        if r["condition"] == "C2" and r["signal"] == "explicit" and r["locale"] != "US":
            by_dom[r["domain"]].append(r["detected"]["flag_count"])
    print("flag rate on C2-local by domain "
          "(the plan predicted employment and finance worst -- check it)")
    for d, xs in sorted(by_dom.items(), key=lambda kv: -mean(kv[1])):
        print(f"  {d:12s} {mean(xs):5.2f}  (n={len(xs)})")

    sigs = sorted({r["signal"] for r in rows if r["condition"] == "C2"})
    if len(sigs) > 1:
        print("\nlocale signalling form (C2, non-US) -- if these agree, the failure "
              "is not a prompting artefact")
        for s in sigs:
            xs = [r for r in cell(rows, condition="C2", signal=s) if r["locale"] != "US"]
            if xs:
                print(f"  {s:9s} flags {mean([r['detected']['flag_count'] for r in xs]):5.2f}  "
                      f"surface {mean([1.0 if r['detected']['surface_localized'] else 0.0 for r in xs]):6.1%}  "
                      f"local institutions {mean([r['detected']['ng_marker_count'] for r in xs]):5.2f}  "
                      f"(n={len(xs)})")

    n = len(models)
    print(f"\n{'=' * 68}")
    print(f"G1 cosmetic localization   {g1_pass}/{n} models   "
          f"(surface > {G1_SURFACE_MIN:.0%} and delta < {G1_DELTA_MAX})")
    print(f"G4 grounding asymmetry     {g4_pass}/{n} models   "
          f"(normalized gap >= {G4_GROUNDING_RATIO}x)")
    print("G2 knowledge/application   PENDING - needs hand-coded C3 correctness")
    print("G3 uninformative repair    PENDING - needs hand-coded C4 capitulation")
    print("\nG3 is the headline hypothesis and the most novel part of the design. "
          "The gate cannot be decided without it.")
    print("  python score/confirm.py --queue c4_codes")
    print("  python score/confirm.py --queue c3_correct")
    print("  python score/confirm.py --report")
    print("\nGate numbers on machine-drafted items. They decide whether to author "
          "the study. They are not results and do not go in the paper.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detected", default="results/detected_gate.jsonl")
    a = ap.parse_args()
    path = ROOT / a.detected
    if not path.exists():
        print(f"no such file: {path}")
        return 2
    return report(load(path))


if __name__ == "__main__":
    raise SystemExit(main())
