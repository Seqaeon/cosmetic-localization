#!/usr/bin/env python3
"""Dump responses for one cell with detector hits annotated inline.

At some point the numbers stop telling you things and you have to read what the
model actually said. This prints a cell's responses with every flag, marker and
contrast marked in place, which is also how the qualitative appendix in
transcripts/ gets built.

    python analysis/show.py --model qwen3.5-4b --condition C2 --locale NG -n 5
    python analysis/show.py --condition C4-false --locale NG -n 8
    python analysis/show.py --item ten_001 --all-conditions
"""
from __future__ import annotations

import argparse
import json
import pathlib
import textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent


def annotate(text: str, hits: list[dict]) -> str:
    """Insert markers at hit spans, right to left so offsets stay valid."""
    tag = {"assumed": "[US:{}]", "contrasted": "[NOT-US:{}]", "present": "[LOCAL:{}]"}
    out = text
    for h in sorted(hits, key=lambda h: -h["start"]):
        if h["kind"] == "surface":
            continue
        label = tag["present" if h["kind"] == "marker" else h["polarity"]].format(h["id"])
        out = out[:h["end"]] + label + out[h["end"]:]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detected", default="results/detected_gate.jsonl")
    ap.add_argument("--model")
    ap.add_argument("--condition")
    ap.add_argument("--locale")
    ap.add_argument("--domain")
    ap.add_argument("--item")
    ap.add_argument("--signal", default="explicit")
    ap.add_argument("--all-conditions", action="store_true")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--raw", action="store_true", help="no inline annotation")
    a = ap.parse_args()

    path = ROOT / a.detected
    if not path.exists():
        print(f"no such file: {path}")
        return 2
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    sel = [r for r in rows if r["sample"] == a.sample]
    for key, val in (("model", a.model), ("locale", a.locale),
                     ("domain", a.domain), ("item_id", a.item)):
        if val:
            sel = [r for r in sel if r[key] == val]
    if a.condition:
        sel = [r for r in sel if r["condition"] == a.condition]
    elif not a.all_conditions:
        sel = [r for r in sel if r["condition"] == "C2"]
    if not a.all_conditions and a.signal:
        sel = [r for r in sel if r.get("signal") in (a.signal, None)]

    if not sel:
        print("no responses match that selection")
        return 1

    for r in sel[:a.n]:
        d = r["detected"]
        print("=" * 78)
        print(f"{r['item_id']}  {r['model']}  {r['condition']}/{r.get('signal')}  "
              f"[{r['locale']}]  {r['domain']}  s{r['sample']}")
        print(f"flags {d['flag_count']} assumed, {d['contrast_count']} contrasted | "
              f"local institutions {d['ng_marker_count']} | "
              f"surface {'yes' if d['surface_localized'] else 'no'} | "
              f"COSMETIC {'YES' if d['cosmetic'] else 'no'}")
        prompt = r["prompt_turns"][-1]["content"]
        print("\nPROMPT: " + textwrap.fill(prompt, 76, subsequent_indent="        "))
        body = r["response"] if a.raw else annotate(r["response"], r["hits"])
        print("\n" + textwrap.fill(body, 78, replace_whitespace=False))
        print()
    print(f"({len(sel)} matched, showing {min(a.n, len(sel))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
