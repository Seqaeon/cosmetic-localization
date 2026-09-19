#!/usr/bin/env python3
"""Gate on the dataset. Non-zero exit means it does not ship.

The release check is the mechanism that keeps the authorship promise honest.
The Fatima application requires the items be the author's own work, so rather
than relying on intent, `--release` refuses to build while any row is
`author: draft`. Phase-0 gate items are drafts by construction and are barred
from the release by the same rule that documents them.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODO = re.compile(r"\b(TODO|TBD|FIXME|XXX|\.\.\.\s*$|<[a-z_]+>)", re.I)
# A local token surviving into the US variant means the swap table missed it,
# which quietly breaks the control: the "US" answer was prompted about Nigeria.
LOCAL_TOKENS = re.compile(
    r"Nigeri|Lagos|Abuja|\u20a6|\bnaira\b|\bNYSC\b|\bCBN\b|\bFCCPC\b|\bCAC\b|\bFIRS\b|"
    r"\bNIBSS\b|\bNIP\b|\bBVN\b|\bNIN\b|\bPFA\b|\bHMO\b|\bNHIA\b|\bNHIS\b|\bDisCo\b|"
    r"\bLASRERA\b|\btokunbo\b|\bFRSC\b|\bPENCOM\b|\bNSITF\b|Kenya|India|Philippin|M-Pesa|"
    r"\bUPI\b|Aadhaar|GCash|PhilHealth", re.I)

# Two prompts in a matched pair should differ only by the locale swap. Past this
# share of differing content words they are different questions, and the whole
# "same question, different country" argument collapses.
MAX_PAIR_DIVERGENCE = 0.35


def words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", s.lower()))


def divergence(a: str, b: str) -> float:
    wa, wb = words(a), words(b)
    return 0.0 if not (wa | wb) else len(wa ^ wb) / len(wa | wb)


def check(items: list[dict], flags: set[str], markers: set[str],
          *, release: bool) -> list[str]:
    schema = json.loads((ROOT / "data" / "schema.json").read_text(encoding="utf-8"))
    val = jsonschema.Draft202012Validator(schema)
    errs: list[str] = []
    by_pair: dict[str, list[dict]] = {}
    seen_ids: set[str] = set()

    for it in items:
        iid = it.get("id", "<no id>")
        for e in sorted(val.iter_errors(it), key=lambda e: e.path):
            errs.append(f"{iid}: schema: {'.'.join(map(str, e.path)) or '<root>'}: {e.message}")
        if iid in seen_ids:
            errs.append(f"{iid}: duplicate id")
        seen_ids.add(iid)
        by_pair.setdefault(it.get("pair_id", "?"), []).append(it)

        for f in it.get("expected_flags", []):
            if f not in flags:
                errs.append(f"{iid}: expected_flags references unknown flag {f!r}")
        for m in it.get("expected_ng_markers", []):
            if m not in markers:
                errs.append(f"{iid}: expected_ng_markers references unknown marker {m!r}")

        for k, v in it.items():
            if isinstance(v, str) and TODO.search(v):
                errs.append(f"{iid}: unresolved placeholder in {k!r}")

        if it.get("gt_tier") == 3 and not it.get("gt_date"):
            errs.append(f"{iid}: gt_tier 3 is market data and needs gt_date; prices move")

        # The false correction must contradict in a DIFFERENT direction from the
        # true one. Near-identical text means the arms are not independent and
        # H3 measures nothing.
        ct, cf = it.get("correction_true"), it.get("correction_false")
        if ct and cf and divergence(ct, cf) < 0.25:
            errs.append(f"{iid}: correction_true and correction_false are near-identical "
                        f"(divergence {divergence(ct, cf):.2f}); the false arm must push "
                        f"in a different direction, not restate the true one")

        if it.get("locale") == "US":
            for k, v in it.items():
                if k in ("id", "pair_id", "derived_from") or not isinstance(v, str):
                    continue
                m = LOCAL_TOKENS.search(v)
                if m:
                    errs.append(f"{iid}: US variant still contains the local token "
                                f"{m.group(0)!r} in {k!r}; the us_swap table missed it, "
                                f"so this control item was prompted about the wrong country")

        if release and it.get("author") != "human":
            errs.append(f"{iid}: author={it.get('author')!r}; the released dataset must be "
                        f"human-authored (see data/CHECKLIST_CHANGELOG.md and the README)")

    for pid, group in by_pair.items():
        locales = {g["locale"] for g in group if "locale" in g}
        if "US" not in locales:
            errs.append(f"pair {pid}: no US variant; the matched-pair control is what rules "
                        f"out 'the question is just hard'")
        if len(group) != 2:
            errs.append(f"pair {pid}: expected exactly 2 items, found {len(group)}")
        if len(group) == 2:
            a, b = group
            for field in ("prompt_localized_explicit", "prompt_bare"):
                if field in a and field in b:
                    d = divergence(a[field], b[field])
                    if d > MAX_PAIR_DIVERGENCE:
                        errs.append(f"pair {pid}: {field} diverges {d:.2f} > "
                                    f"{MAX_PAIR_DIVERGENCE}; these read as different questions")
            if a.get("prompt_bare") != b.get("prompt_bare"):
                errs.append(f"pair {pid}: prompt_bare differs between variants; C1 carries no "
                            f"locale signal and must be byte-identical across the pair")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default="data/items.jsonl")
    ap.add_argument("--release", action="store_true",
                    help="enforce human authorship and full ground-truth provenance")
    a = ap.parse_args()

    path = ROOT / a.items
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    items = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    flags = {f["id"] for f in json.loads((ROOT / "data" / "checklist.json").read_text())["flags"]}
    markers = {m["id"] for m in json.loads((ROOT / "data" / "ng_markers.json").read_text())["markers"]}

    errs = check(items, flags, markers, release=a.release)
    mode = "release" if a.release else "draft"
    if errs:
        print(f"FAIL  {len(errs)} problem(s) in {len(items)} items [{mode}]\n", file=sys.stderr)
        for e in errs:
            print("  " + e, file=sys.stderr)
        return 1

    tiers: dict[int, int] = {}
    for it in items:
        tiers[it.get("gt_tier", 0)] = tiers.get(it.get("gt_tier", 0), 0) + 1
    div = sum(1 for it in items if it.get("law_practice_divergence"))
    print(f"ok    {len(items)} items, {len(set(i['pair_id'] for i in items))} pairs [{mode}]")
    print(f"      gt tiers: " + ", ".join(f"t{k}={v}" for k, v in sorted(tiers.items())))
    print(f"      law/practice divergence: {div}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
