#!/usr/bin/env python3
"""Merge response files, later files winning.

Re-running one model or one condition produces a partial file. This folds it
into the main one on (model, row_id, sample) so a targeted re-run does not mean
regenerating everything -- which matters once responses have been hand-scored,
because new generations invalidate the codes attached to the old ones.

    python build/merge_responses.py results/responses_gate.jsonl \\
        results/responses_minicpm.jsonl results/responses_c3.jsonl \\
        --out results/responses_gate_v2.jsonl
"""
import argparse
import json
import pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent


def key(r): return (r["model"], r["row_id"], r["sample"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    merged: dict[tuple, dict] = {}
    for f in a.files:
        path = ROOT / f
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        new = sum(1 for r in rows if key(r) not in merged)
        for r in rows:
            merged[key(r)] = r
        print(f"  {path.name:34s} {len(rows):5d} rows  ({new} new, {len(rows)-new} replaced)")

    out = ROOT / a.out
    ordered = sorted(merged.values(), key=lambda r: (r["model"], r["sample"], r["row_id"]))
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ordered),
                   encoding="utf-8")
    print(f"\n{len(ordered)} responses -> {a.out}")
    bym = Counter(r["model"] for r in ordered)
    for m, n in sorted(bym.items()):
        reasoning = Counter(r.get("reasoning", "unknown") for r in ordered if r["model"] == m)
        print(f"  {m:14s} {n:5d}   reasoning: {dict(reasoning)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
