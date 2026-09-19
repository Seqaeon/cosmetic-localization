#!/usr/bin/env python3
"""CLI entry point. The notebook imports engine directly; this exists so the
identical code path is reproducible headless from a shell."""
import argparse
import pathlib

from engine import MODELS, RunConfig, run

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="probe/gate_manifest.jsonl")
    ap.add_argument("--out", default="results/responses.jsonl")
    ap.add_argument("--models", nargs="+", default=list(MODELS))
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--limit", type=int, default=None,
                    help="first N items only; use for a smoke test")
    ap.add_argument("--backend", choices=["auto", "vllm", "hf", "dryrun"], default="auto")
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.42,
                    help="per-model share; three resident models need to fit together")
    a = ap.parse_args()

    unknown = [m for m in a.models if m not in MODELS]
    if unknown:
        ap.error(f"unknown model(s) {unknown}; known: {list(MODELS)}")

    run(RunConfig(
        models=a.models, manifest=ROOT / a.manifest, out=ROOT / a.out,
        samples=a.samples, seed=a.seed, temperature=a.temperature,
        limit=a.limit, backend=a.backend,
        extra={"gpu_memory_utilization": a.gpu_memory_utilization},
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
