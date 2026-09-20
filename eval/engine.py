#!/usr/bin/env python3
"""Batched multi-model inference for the four-condition design.

Two passes, because C4 is a second turn on top of the model's OWN C2 answer:

  pass 1  C1, C2 (all signalling forms), C3      -> independent, one big batch
  pass 2  C4-true, C4-false                      -> each seeded with that model's
                                                    C2 response at the SAME sample
                                                    index, in two separate
                                                    conversations

The two correction arms never share a conversation. A model that has already
seen the true correction would answer the false one differently, and the whole
point of the C4-false arm is that it is independent evidence.

Backends: vLLM when importable (fast, batched), HF generate otherwise. The
fallback exists because two of the three checkpoints are recent enough that
vLLM support is worth not depending on.
"""
from __future__ import annotations

import gc
import json
import os
import pathlib
import re
import time
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Selection rationale lives in the README; the operational facts live here.
MODELS: dict[str, dict] = {
    "qwen3.5-4b": dict(
        hf_id="Qwen/Qwen3.5-4B", lab="Alibaba", origin="CN", params="4B",
        # Qwen ships a thinking mode. Left on, reasoning traces land in the
        # response text and every flag count is contaminated by them.
        template_kwargs={"enable_thinking": False},
        supports_system=True,
    ),
    "gemma4-e2b": dict(
        hf_id="google/gemma-4-E2B-it", lab="Google DeepMind", origin="US",
        params="5.1B raw / 2.3B effective",
        template_kwargs={}, supports_system=False,   # Gemma templates historically reject a system turn
    ),
    "minicpm5-2b": dict(
        hf_id="openbmb/MiniCPM5-2B", lab="OpenBMB", origin="CN", params="2.5B",
        # MiniCPM5 reasons by default. Left on, it spends the whole budget inside
        # <think> and the response scored is the model's internal monologue, not
        # its advice. The kwarg is applied best-effort and the leak guard below
        # is what actually catches failure.
        template_kwargs={"enable_thinking": False}, supports_system=True,
        trust_remote_code=True,
    ),
}

# Responses were hitting these caps: word counts clustered hard against the
# limit and 87% of a 512-token run ended without terminal punctuation. Uniform
# truncation does not bias the between-condition comparisons, but it floors the
# absolute rates and makes the transcripts useless as a qualitative appendix.
MAX_TOKENS = {"C1": 1024, "C2": 1024, "C3": 1024, "C4-true": 384, "C4-false": 384}

_THINK = re.compile(r"<think>.*?</think>\s*", re.S | re.I)
_THINK_OPEN = re.compile(r"<think>", re.I)


def strip_reasoning(text: str) -> tuple[str, str]:
    """Remove a closed reasoning block. Returns (clean_text, status).

    status is 'clean' (nothing there), 'stripped' (a closed block removed), or
    'unclosed' (the generation never left the reasoning block, so there is no
    answer at all and the record must not be scored)."""
    if not _THINK_OPEN.search(text):
        return text, "clean"
    out = _THINK.sub("", text).strip()
    if _THINK_OPEN.search(out) or not out:
        return out, "unclosed"
    return out, "stripped"
TEMPERATURE = 0.7
TOP_P = 0.9
C2_PLACEHOLDER = "__C2_RESPONSE__"


@dataclass
class RunConfig:
    models: list[str]
    manifest: pathlib.Path
    out: pathlib.Path
    samples: int = 3
    seed: int = 0
    temperature: float = TEMPERATURE
    top_p: float = TOP_P
    limit: int | None = None
    conditions: set[str] | None = None   # re-run one condition without disturbing others
    max_tokens: int | None = None        # override; a partial re-run MUST match the
    max_tokens_c4: int | None = None     # caps of the run it is being merged into
    backend: str = "auto"
    extra: dict = field(default_factory=dict)


def load_manifest(path: pathlib.Path, limit: int | None = None) -> list[dict]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if limit:
        keep = {r["item_id"] for r in rows[:limit]}
        rows = [r for r in rows if r["item_id"] in keep]
    return rows


def _flatten_system(turns: list[dict]) -> list[dict]:
    """Fold a system turn into the first user turn, for templates that reject one."""
    if not turns or turns[0]["role"] != "system":
        return turns
    sys_txt, rest = turns[0]["content"], turns[1:]
    if rest and rest[0]["role"] == "user":
        merged = dict(rest[0])
        merged["content"] = f"{sys_txt}\n\n{rest[0]['content']}"
        return [merged] + rest[1:]
    return rest


class Backend:
    name = "base"

    def generate(self, convs: list[list[dict]], max_tokens: int, seed: int,
                 cfg: RunConfig) -> list[str]:
        raise NotImplementedError


class VLLMBackend(Backend):
    name = "vllm"

    def __init__(self, spec: dict, cfg: RunConfig):
        from vllm import LLM
        from transformers import AutoTokenizer
        self.spec = spec
        self.tok = AutoTokenizer.from_pretrained(
            spec["hf_id"], trust_remote_code=spec.get("trust_remote_code", False))
        self.llm = LLM(
            model=spec["hf_id"], dtype="bfloat16",
            trust_remote_code=spec.get("trust_remote_code", False),
            gpu_memory_utilization=cfg.extra.get("gpu_memory_utilization", 0.42),
            max_model_len=cfg.extra.get("max_model_len", 4096),
            seed=cfg.seed,
        )

    def _render(self, conv: list[dict]) -> str:
        if not self.spec.get("supports_system", True):
            conv = _flatten_system(conv)
        return self.tok.apply_chat_template(
            conv, tokenize=False, add_generation_prompt=True,
            **self.spec.get("template_kwargs", {}))

    def generate(self, convs, max_tokens, seed, cfg):
        from vllm import SamplingParams
        sp = SamplingParams(temperature=cfg.temperature, top_p=cfg.top_p,
                            max_tokens=max_tokens, seed=seed)
        outs = self.llm.generate([self._render(c) for c in convs], sp)
        return [o.outputs[0].text.strip() for o in outs]


class HFBackend(Backend):
    name = "hf"

    def __init__(self, spec: dict, cfg: RunConfig):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.spec = spec
        tck = spec.get("trust_remote_code", False)
        self.tok = AutoTokenizer.from_pretrained(spec["hf_id"], trust_remote_code=tck,
                                                 padding_side="left")
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            spec["hf_id"], dtype=torch.bfloat16, device_map="auto", trust_remote_code=tck).eval()
        self.bs = cfg.extra.get("hf_batch_size", 16)

    def _render(self, conv):
        if not self.spec.get("supports_system", True):
            conv = _flatten_system(conv)
        return self.tok.apply_chat_template(
            conv, tokenize=False, add_generation_prompt=True,
            **self.spec.get("template_kwargs", {}))

    def generate(self, convs, max_tokens, seed, cfg):
        self.torch.manual_seed(seed)
        prompts = [self._render(c) for c in convs]
        out: list[str] = []
        for i in range(0, len(prompts), self.bs):
            chunk = prompts[i:i + self.bs]
            enc = self.tok(chunk, return_tensors="pt", padding=True,
                           add_special_tokens=False).to(self.model.device)
            with self.torch.no_grad():
                gen = self.model.generate(
                    **enc, max_new_tokens=max_tokens, do_sample=cfg.temperature > 0,
                    temperature=cfg.temperature, top_p=cfg.top_p,
                    pad_token_id=self.tok.pad_token_id)
            for j in range(len(chunk)):
                new = gen[j][enc["input_ids"].shape[1]:]
                out.append(self.tok.decode(new, skip_special_tokens=True).strip())
        return out


class DryRunBackend(Backend):
    """Plumbing test only. Emits canned text so the manifest -> generate ->
    detect -> score chain can be exercised without a GPU. Every response is
    prefixed so dry-run output can never be mistaken for a model's."""
    name = "dryrun"

    US_DEFAULT = (
        "Here's what I'd suggest. First, check your credit score, since it affects "
        "almost everything else. Give two weeks' notice and let HR know in writing. "
        "Make sure your final paycheck and any accrued PTO are settled. Budget around "
        "30% of your income for monthly rent, and expect a security deposit of one to "
        "two months. Keep an emergency fund covering three months of expenses in a "
        "high-yield savings account, and set up direct deposit so it builds "
        "automatically. If the landlord refuses, small claims court is inexpensive."
    )
    LOCALIZED_COSMETIC = (
        "Here's what I'd suggest for Nigeria. First, check your credit score, since it "
        "affects almost everything else. Give two weeks' notice and let HR know in "
        "writing. Budget around 30% of your income for monthly rent in naira, and "
        "expect a security deposit of one to two months. Keep an emergency fund "
        "covering three months of expenses. If the landlord refuses, small claims "
        "court is inexpensive."
    )
    GROUNDED = (
        "In Nigeria this works differently. Most landlords will ask for a year or two "
        "years' rent upfront in one payment, plus an agency fee and a legal fee, so "
        "there is no monthly rent to budget against. There is no credit score that "
        "gates this. Your pension sits with a PFA, and under the Labour Act notice "
        "depends on your length of service."
    )
    CAPITULATE = (
        "You're absolutely right, and I apologise for the error. Thank you for the "
        "correction -- that is indeed how it works, and I should have said so."
    )

    def __init__(self, spec, cfg):
        self.spec, self.cfg = spec, cfg

    def generate(self, convs, max_tokens, seed, cfg):
        out = []
        for c in convs:
            last = c[-1]["content"].lower()
            n = len(c)
            if n >= 3:
                body = self.CAPITULATE
            elif "nigeria" in last or "lagos" in last or "\u20a6" in c[-1]["content"]:
                body = self.GROUNDED if (seed + len(last)) % 3 == 0 else self.LOCALIZED_COSMETIC
            else:
                body = self.US_DEFAULT
            out.append("[DRY RUN - not a model output] " + body)
        return out


def make_backend(spec: dict, cfg: RunConfig) -> Backend:
    if cfg.backend == "dryrun":
        return DryRunBackend(spec, cfg)
    if cfg.backend in ("auto", "vllm"):
        try:
            return VLLMBackend(spec, cfg)
        except Exception as e:                       # noqa: BLE001
            if cfg.backend == "vllm":
                raise
            print(f"    vllm unavailable ({type(e).__name__}: {e}); falling back to HF generate")
    return HFBackend(spec, cfg)


def run_model(key: str, rows: list[dict], cfg: RunConfig) -> list[dict]:
    spec = MODELS[key]
    print(f"\n=== {key}  ({spec['hf_id']}, {spec['lab']}, {spec['origin']}) ===")
    be = make_backend(spec, cfg)
    print(f"    backend={be.name}")

    pass1 = [r for r in rows if "depends_on" not in r]
    pass2 = [r for r in rows if "depends_on" in r]
    results: list[dict] = []
    # (item_id, sample) -> that model's own C2-explicit answer, which is what
    # the correction turns must be layered onto.
    c2_by: dict[tuple[str, int], str] = {}

    for s in range(cfg.samples):
        seed = cfg.seed + s
        for cond in ("C1", "C2", "C3"):
            batch = [r for r in pass1 if r["condition"] == cond]
            if not batch:
                continue
            t0 = time.time()
            texts = be.generate([r["turns"] for r in batch],
                                cfg.max_tokens or MAX_TOKENS[cond], seed, cfg)
            print(f"    s{s} {cond:8s} {len(batch):4d} rows  {time.time() - t0:6.1f}s")
            for r, txt in zip(batch, texts):
                clean, status = strip_reasoning(txt)
                results.append({**{k: v for k, v in r.items() if k != "turns"},
                                "model": key, "sample": s, "seed": seed,
                                "prompt_turns": r["turns"], "response": clean,
                                "raw_response": txt if status != "clean" else None,
                                "reasoning": status})
                if cond == "C2" and r["signal"] == "explicit":
                    c2_by[(r["item_id"], s)] = clean

        for cond in ("C4-true", "C4-false"):
            batch = [r for r in pass2 if r["condition"] == cond]
            if not batch:
                continue
            convs, kept = [], []
            for r in batch:
                prior = c2_by.get((r["item_id"], s))
                if prior is None:            # C2 missing for this item: skip rather than fabricate
                    continue
                convs.append([t if t["content"] != C2_PLACEHOLDER
                              else {**t, "content": prior} for t in r["turns"]])
                kept.append(r)
            if not convs:
                continue
            t0 = time.time()
            texts = be.generate(convs, cfg.max_tokens_c4 or MAX_TOKENS[cond], seed, cfg)
            print(f"    s{s} {cond:8s} {len(convs):4d} rows  {time.time() - t0:6.1f}s")
            for r, conv, txt in zip(kept, convs, texts):
                clean, status = strip_reasoning(txt)
                results.append({**{k: v for k, v in r.items() if k != "turns"},
                                "model": key, "sample": s, "seed": seed,
                                "prompt_turns": conv, "response": clean,
                                "raw_response": txt if status != "clean" else None,
                                "reasoning": status})

    bad = [r for r in results if r["reasoning"] == "unclosed"]
    strip = [r for r in results if r["reasoning"] == "stripped"]
    if strip:
        print(f"    reasoning blocks stripped from {len(strip)}/{len(results)} responses")
    if bad:
        frac = len(bad) / len(results)
        print(f"\n    *** {len(bad)}/{len(results)} ({frac:.1%}) responses never left the "
              f"reasoning block: no answer was produced. ***")
        print(f"    *** {key}: disable thinking for this checkpoint or raise MAX_TOKENS "
              f"before scoring anything. ***\n")
        if frac > 0.05:
            raise RuntimeError(
                f"{key}: {frac:.1%} of responses are reasoning-only. Scoring these would "
                f"measure the model's internal monologue rather than its advice. Fix the "
                f"chat template kwargs or the token budget and re-run this model.")

    del be
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:                                # noqa: BLE001
        pass
    return results


def run(cfg: RunConfig) -> pathlib.Path:
    rows = load_manifest(cfg.manifest, cfg.limit)
    if cfg.conditions:
        # C4 is layered on the model's own C2 answer, so asking for C4 alone
        # would have nothing to build on. Pull C2 in silently when needed.
        want = set(cfg.conditions)
        if any(c.startswith("C4") for c in want):
            want.add("C2")
        rows = [r for r in rows if r["condition"] in want]
        print(f"condition filter {sorted(cfg.conditions)}: {len(rows)} contexts")
    print(f"manifest: {len(rows)} contexts x {cfg.samples} samples x {len(cfg.models)} models "
          f"= {len(rows) * cfg.samples * len(cfg.models)} generations")
    cfg.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(cfg.out, "w", encoding="utf-8") as f:
        for key in cfg.models:
            for rec in run_model(key, rows, cfg):
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    print(f"\nwrote {n} responses -> {cfg.out}")
    return cfg.out
