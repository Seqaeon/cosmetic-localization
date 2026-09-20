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
    ap.add_argument("--conditions", nargs="+",
                    choices=["C1", "C2", "C3", "C4-true", "C4-false"],
                    help="re-run only these conditions; C2 is pulled in automatically "
                         "when a C4 arm is requested, since C4 builds on it")
    ap.add_argument("--max-tokens", type=int,
                    help="override the C1/C2/C3 cap. A partial re-run merged into an "
                         "existing run must use that run's caps, or conditions become "
                         "incomparable within a model.")
    ap.add_argument("--max-tokens-c4", type=int, help="override the C4 cap")
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
        conditions=set(a.conditions) if a.conditions else None,
        max_tokens=a.max_tokens, max_tokens_c4=a.max_tokens_c4,
        extra={"gpu_memory_utilization": a.gpu_memory_utilization},
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
