#!/usr/bin/env python3
"""Data-integrity pass over a generation run.

Everything here is mechanical. None of it needs a judgement call, and all of it
is the kind of thing that quietly invalidates a result if nobody looks.

The headline check is the length confound. Flag counts are absolute, so if
localized answers are simply shorter than their US counterparts, a lower flag
rate is a length artifact rather than a locale effect. Every rate is therefore
also reported per 100 words.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics as st
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent

REFUSAL = re.compile(
    r"\b(I (?:cannot|can't|am unable to|won't)|I'm (?:not able|unable)|"
    r"As an AI|I do not have the ability|I'm sorry,? but I)\b", re.I)
THINKING = re.compile(r"<\|?/?(?:think|thinking|im_start|im_end|assistant|system)\|?>", re.I)
TEMPLATE = re.compile(r"<\|[a-z_]+\|>|<start_of_turn>|<end_of_turn>|\[INST\]|</s>")
TERMINAL = re.compile(r"[.!?\"')\]]\s*$|```\s*$")


def mean(xs): return st.mean(xs) if xs else 0.0
def words(t): return len(t.split())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detected", default="results/detected_gate.jsonl")
    ap.add_argument("--show", type=int, default=3, help="examples per problem")
    a = ap.parse_args()

    rows = [json.loads(l) for l in (ROOT / a.detected).read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(rows)} responses\n")

    # ---- generation hygiene -------------------------------------------------
    problems: dict[str, list] = defaultdict(list)
    for r in rows:
        t = r.get("response", "")
        tag = f"{r['item_id']} {r['model']} {r['condition']} s{r['sample']}"
        if not t.strip():
            problems["empty response"].append((tag, ""))
        elif words(t) < 15:
            problems["very short (<15 words)"].append((tag, t[:90]))
        if REFUSAL.search(t):
            problems["refusal language"].append((tag, REFUSAL.search(t).group(0)))
        if THINKING.search(t):
            problems["THINKING TRACE LEAK"].append((tag, THINKING.search(t).group(0)))
        if TEMPLATE.search(t):
            problems["chat-template artefact"].append((tag, TEMPLATE.search(t).group(0)))
        if t.strip() and not TERMINAL.search(t):
            problems["no terminal punctuation (likely truncated)"].append((tag, "..." + t[-70:]))
        for turn in r.get("prompt_turns", []):
            if "__C2_RESPONSE__" in turn.get("content", ""):
                problems["PLACEHOLDER LEAK in prompt"].append((tag, turn["role"]))

    print("=" * 74)
    print("GENERATION HYGIENE")
    if not problems:
        print("  clean")
    for k in sorted(problems, key=lambda k: -len(problems[k])):
        v = problems[k]
        print(f"  {len(v):4d}  {k}   ({len(v)/len(rows):.1%})")
        for tag, ex in v[:a.show]:
            print(f"          {tag}  {ex!r}"[:130])

    # ---- length confound ----------------------------------------------------
    print("\n" + "=" * 74)
    print("LENGTH CONFOUND  -- if localized answers are just shorter, a lower flag")
    print("count is an artefact. Rates per 100 words are the controlled measure.")
    for m in sorted({r["model"] for r in rows}):
        print(f"\n  {m}")
        print(f"    {'cell':22s} {'n':>4s} {'words':>7s} {'flags':>6s} {'/100w':>7s} "
              f"{'local':>6s} {'/100w':>7s}")
        for cond, sig, loc, lab in (
                ("C1", "explicit", None, "C1 bare"),
                ("C2", "explicit", "NG", "C2 Nigeria"),
                ("C2", "explicit", "US", "C2 United States"),
                ("C3", "explicit", "NG", "C3 knowledge NG"),
                ("C3", "explicit", "US", "C3 knowledge US")):
            xs = [r for r in rows if r["model"] == m and r["condition"] == cond
                  and (loc is None or r["locale"] == loc)
                  and (cond == "C1" or r.get("signal") == sig)]
            if not xs:
                continue
            w = mean([words(r["response"]) for r in xs])
            f = mean([r["detected"]["flag_count"] for r in xs])
            g = mean([r["detected"]["ng_marker_count"] for r in xs])
            print(f"    {lab:22s} {len(xs):4d} {w:7.0f} {f:6.2f} {f/w*100 if w else 0:7.2f} "
                  f"{g:6.2f} {g/w*100 if w else 0:7.2f}")

        c1 = [r for r in rows if r["model"] == m and r["condition"] == "C1"]
        c2 = [r for r in rows if r["model"] == m and r["condition"] == "C2"
              and r.get("signal") == "explicit" and r["locale"] != "US"]
        us = [r for r in rows if r["model"] == m and r["condition"] == "C2"
              and r.get("signal") == "explicit" and r["locale"] == "US"]
        if c1 and c2 and us:
            r1 = mean([r["detected"]["flag_count"] for r in c1]) / mean([words(r["response"]) for r in c1]) * 100
            r2 = mean([r["detected"]["flag_count"] for r in c2]) / mean([words(r["response"]) for r in c2]) * 100
            gu = mean([r["detected"]["flag_count"] for r in us]) / mean([words(r["response"]) for r in us]) * 100
            gl = mean([r["detected"]["ng_marker_count"] for r in c2]) / mean([words(r["response"]) for r in c2]) * 100
            print(f"    -> localization delta per 100w  {r1 - r2:+.2f}  "
                  f"({(r1 - r2) / r1:+.1%} of bare)" if r1 else "")
            print(f"    -> grounding gap per 100w       {gu / gl:.1f}x raw, "
                  f"{(gu/48)/(gl/35):.1f}x normalized" if gl else "    -> grounding gap: local rate is 0")

    # ---- detector sanity ----------------------------------------------------
    print("\n" + "=" * 74)
    print("DETECTOR SANITY  -- a trigger firing on nearly everything is usually")
    print("too broad, not a finding. These are candidates for the precision check.")
    fire: dict[str, int] = defaultdict(int)
    for r in rows:
        for fid in set(r["detected"]["flags_assumed"]):
            fire[fid] += 1
    print(f"\n  {'flag':34s} {'fires':>6s} {'rate':>7s}")
    for fid, n in sorted(fire.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {fid:34s} {n:6d} {n/len(rows):7.1%}")
    ck = json.loads((ROOT / "data/checklist.json").read_text())
    never = [f["id"] for f in ck["flags"] if f["id"] not in fire]
    print(f"\n  never fired: {len(never)}/{len(ck['flags'])} flags")
    if never:
        print("    " + ", ".join(never))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
