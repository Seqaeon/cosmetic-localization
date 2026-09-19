#!/usr/bin/env python3
"""Materialize matched pairs and expand them into the run manifest.

Authoring happens once per pair, in the local-locale voice. The US variant is
derived from `us_swap`, so the two halves of a pair cannot drift apart through
independent editing -- which is the whole point of a matched-pair design.

C1 (bare) carries no locale signal, so the two variants of a pair SHARE one C1
row. Anything else would double the cost of the condition and introduce a
spurious difference between two prompts that are meant to be identical.
"""
from __future__ import annotations

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

PROMPT_FIELDS = [
    "prompt_bare", "prompt_localized_explicit", "prompt_localized_implicit",
    "prompt_knowledge", "correction_true", "correction_false",
]
CARRIED = [
    "correction_false_rationale", "ground_truth", "gt_tier", "gt_source",
    "gt_date", "law_practice_divergence", "expected_flags",
    "expected_ng_markers", "notes", "in_signalling_substudy",
    "in_us_correction_subset", "in_frontier_spotcheck",
]


def apply_replace(text: str, table: dict[str, str]) -> str:
    # Longest key first, so "Lagos, Nigeria" wins over "Nigeria".
    for k in sorted(table, key=len, reverse=True):
        text = text.replace(k, table[k])
    return text


def materialize_us(src: dict) -> dict:
    swap = src["us_swap"]
    rep, over = swap["replace"], swap.get("overrides", {})
    us = {
        "id": src["id"] + "_us",
        "pair_id": src["pair_id"],
        "domain": src["domain"],
        "locale": "US",
        "derived_from": src["id"],
        "archetype": src["archetype"],
        "author": src["author"],
    }
    for f in PROMPT_FIELDS:
        if f in over:
            us[f] = over[f]
        elif f in src:
            us[f] = apply_replace(src[f], rep)
    if "prompt_localized_system" in src:
        blk = over.get("prompt_localized_system") or {
            k: apply_replace(v, rep) for k, v in src["prompt_localized_system"].items()
        }
        us["prompt_localized_system"] = blk
    for f in CARRIED:
        if f in over:
            us[f] = over[f]
        elif f in src:
            us[f] = src[f]
    # A US-locale answer that assumes US institutions is correct behaviour, so
    # unless the author says otherwise the US variant predicts no flags. H4 is
    # exactly the claim that this column stays near zero.
    us.setdefault("expected_flags", [])
    us["expected_ng_markers"] = over.get("expected_ng_markers", [])
    return us


def expand(items: list[dict], *, samples: int, seed: int) -> list[dict]:
    """items -> one row per (item, condition, signalling form). Samples are a
    generation-time parameter, carried here only so the manifest is self-describing."""
    rows, seen_bare = [], set()
    for it in items:
        base = {"item_id": it["id"], "pair_id": it["pair_id"], "domain": it["domain"],
                "locale": it["locale"]}

        if it["pair_id"] not in seen_bare:
            seen_bare.add(it["pair_id"])
            rows.append({**base, "condition": "C1", "signal": "none", "turns":
                         [{"role": "user", "content": it["prompt_bare"]}]})

        rows.append({**base, "condition": "C2", "signal": "explicit", "turns":
                     [{"role": "user", "content": it["prompt_localized_explicit"]}]})

        if it.get("in_signalling_substudy"):
            if "prompt_localized_system" in it:
                b = it["prompt_localized_system"]
                rows.append({**base, "condition": "C2", "signal": "system", "turns": [
                    {"role": "system", "content": b["system"]},
                    {"role": "user", "content": b["user"]}]})
            if "prompt_localized_implicit" in it:
                rows.append({**base, "condition": "C2", "signal": "implicit", "turns":
                             [{"role": "user", "content": it["prompt_localized_implicit"]}]})

        rows.append({**base, "condition": "C3", "signal": "explicit", "turns":
                     [{"role": "user", "content": it["prompt_knowledge"]}]})

        # C4 is a second turn on top of the C2 answer, so the assistant slot is
        # filled at run time from that model's own C2 response. Two separate
        # conversations, never one thread -- a model that has already seen the
        # true correction would answer the false one differently.
        wants_c4 = it["locale"] != "US" or it.get("in_us_correction_subset")
        if wants_c4:
            for arm, field in (("C4-true", "correction_true"), ("C4-false", "correction_false")):
                rows.append({**base, "condition": arm, "signal": "explicit",
                             "depends_on": {"condition": "C2", "signal": "explicit",
                                            "item_id": it["id"]},
                             "turns": [{"role": "user", "content": it["prompt_localized_explicit"]},
                                       {"role": "assistant", "content": "__C2_RESPONSE__"},
                                       {"role": "user", "content": it[field]}]})
    for i, r in enumerate(rows):
        r["row_id"] = f"r{i:05d}"
        r["samples"] = samples
        r["seed"] = seed
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default="data/items_src.jsonl")
    ap.add_argument("--out-items", default="data/items.jsonl")
    ap.add_argument("--out-manifest", default="results/manifest.jsonl")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    src = [json.loads(l) for l in (ROOT / a.items).read_text(encoding="utf-8").splitlines() if l.strip()]
    full: list[dict] = []
    for it in src:
        full.append(it)
        full.append(materialize_us(it))

    (ROOT / a.out_items).write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in full), encoding="utf-8")
    rows = expand(full, samples=a.samples, seed=a.seed)
    (ROOT / a.out_manifest).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / a.out_manifest).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    by_cond: dict[str, int] = {}
    for r in rows:
        by_cond[r["condition"]] = by_cond.get(r["condition"], 0) + 1
    print(f"{len(src)} authored -> {len(full)} items -> {len(rows)} contexts "
          f"({len(rows) * a.samples} generations per model)")
    for k in sorted(by_cond):
        print(f"  {k:10s} {by_cond[k]:5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
