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

G1_SURFACE_MIN = 0.70     # the answer must LOOK localized ...
G1_DELTA_MAX = 0.50       # ... while the presupposition count barely moves
G4_US_FLAG_MAX = 0.75     # matched US answers should be near-clean


def mean(xs): return st.mean(xs) if xs else 0.0


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

        f1 = mean([r["detected"]["flag_count"] for r in c1])
        f2 = mean([r["detected"]["flag_count"] for r in c2_loc])
        fus = mean([r["detected"]["flag_count"] for r in c2_us])
        surf = mean([1.0 if r["detected"]["surface_localized"] else 0.0 for r in c2_loc])
        ngm = mean([r["detected"]["ng_marker_count"] for r in c2_loc])
        contr = mean([r["detected"]["contrast_count"] for r in c2_loc])
        cosm = mean([1.0 if r["detected"]["cosmetic"] else 0.0 for r in c2_loc])
        delta = f1 - f2

        g1 = surf > G1_SURFACE_MIN and delta < G1_DELTA_MAX
        g4 = fus <= G4_US_FLAG_MAX or fus <= f2
        g1_pass += g1
        g4_pass += g4

        print(f"--- {m} " + "-" * (58 - len(m)))
        print(f"  flag rate   C1 bare {f1:5.2f}   C2 local {f2:5.2f}   "
              f"localization delta {delta:+5.2f}")
        print(f"  flag rate   C2 US   {fus:5.2f}   (H4: matched US answers should be near-clean)")
        print(f"  surface localization on C2-local   {surf:5.1%}")
        print(f"  local institutions named per answer {ngm:5.2f}   "
              f"explicit non-transfer {contr:5.2f}")
        print(f"  COSMETIC CELL  {cosm:5.1%}  of localized answers are dressed local, "
              f"built US, naming nothing local")
        print(f"  G1 {'PASS' if g1 else 'fail'}   G4 {'PASS' if g4 else 'fail'}\n")

    by_dom: dict[str, list] = defaultdict(list)
    for r in rows:
        if r["condition"] == "C2" and r["signal"] == "explicit" and r["locale"] != "US":
            by_dom[r["domain"]].append(r["detected"]["flag_count"])
    print("flag rate on C2-local by domain")
    for d, xs in sorted(by_dom.items(), key=lambda kv: -mean(kv[1])):
        print(f"  {d:12s} {mean(xs):5.2f}  (n={len(xs)})")

    sigs = sorted({r["signal"] for r in rows if r["condition"] == "C2"})
    if len(sigs) > 1:
        print("\nlocale signalling form (C2, non-US)")
        for s in sigs:
            xs = [r for r in cell(rows, condition="C2", signal=s) if r["locale"] != "US"]
            if xs:
                print(f"  {s:9s} flags {mean([r['detected']['flag_count'] for r in xs]):5.2f}  "
                      f"surface {mean([1.0 if r['detected']['surface_localized'] else 0.0 for r in xs]):5.1%}  "
                      f"(n={len(xs)})")

    n = len(models)
    print(f"\n{'=' * 64}")
    print(f"G1 cosmetic localization   {g1_pass}/{n} models")
    print(f"G4 region-conditional      {g4_pass}/{n} models")
    print("G2 knowledge/application   PENDING - needs hand-coded C3 correctness")
    print("G3 uninformative repair    PENDING - needs hand-coded C4 capitulation")
    print("\nRun `python score/confirm.py` on the exported queues, then re-run this "
          "with --scored to close G2 and G3.")
    print("These are gate numbers on machine-drafted items. They decide whether to "
          "author the study. They are not results and do not go in the paper.")
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
