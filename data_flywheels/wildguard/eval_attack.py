#!/usr/bin/env python
"""Phase 4 — score a WildGuard model on the held-out "our-attack" split.

These 54 prompts (attack_split/attack_heldout.jsonl) are judge-confirmed harmful
adversarial rewrites that the BASE WildGuard missed, and were NEVER trained on.
So base recall on them is ~0 by construction; the metric of interest is how much
the LoRA adapter recovers (generalization to unseen attacks of the same style).

Run it twice and compare:
    base    : --model default/wildguard
    adapted : --model default/wildguard-flywheel-v2-lora   (adapter served via IGW)

All rows are gold=harmful, so we report recall (= fraction correctly flagged
"Harmful request: yes"). Use baseline_eval.py for the WildGuardTest P/R/F1 headline.

Usage:
    export NMP_BASE_URL=http://localhost:8080
    .venv/bin/python data_flywheels/wildguard/eval_attack.py --model default/wildguard
    .venv/bin/python data_flywheels/wildguard/eval_attack.py --model default/wildguard-flywheel-v2-lora
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(HERE))
from baseline_eval import igw_completions_url, predict  # noqa: E402


def load_split(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="default/wildguard")
    ap.add_argument("--split", default=str(HERE / "attack_split" / "attack_heldout.jsonl"))
    ap.add_argument("--workspace", default="default")
    ap.add_argument("--base-url", default=os.environ.get("NMP_BASE_URL", "http://localhost:8080"))
    ap.add_argument("--completions-url", default=None,
                    help="Override completions endpoint (direct vLLM for LoRA adapters)")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--out", default=str(HERE / "eval_out"))
    args = ap.parse_args()

    rows = load_split(Path(args.split))
    url = args.completions_url or igw_completions_url(args.base_url, args.workspace)
    from baseline_eval import render

    def work(idx_rec):
        i, rec = idx_rec
        try:
            pred = predict(url, args.model, render(str(rec["prompt"])))
        except Exception as e:  # noqa: BLE001
            pred = None
            rec["_err"] = str(e)[:120]
        return i, pred

    preds: dict[int, str | None] = {}
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for fut in as_completed(ex.submit(work, it) for it in enumerate(rows)):
            i, pred = fut.result()
            preds[i] = pred

    caught = sum(1 for p in preds.values() if p == "harmful")
    missed = sum(1 for p in preds.values() if p == "unharmful")
    unparsed = sum(1 for p in preds.values() if p is None)
    n = len(rows)
    scored = caught + missed
    recall = round(100 * caught / scored, 1) if scored else 0.0

    # per-tactic breakdown
    from collections import Counter, defaultdict
    by = defaultdict(lambda: [0, 0])  # tactic -> [caught, total]
    for i, rec in enumerate(rows):
        t = rec.get("tactic", "?")
        by[t][1] += 1
        if preds.get(i) == "harmful":
            by[t][0] += 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {"model": args.model, "split": Path(args.split).name, "n": n,
           "scored": scored, "caught": caught, "missed": missed,
           "unparsed": unparsed, "recall": recall,
           "per_tactic": {t: {"caught": c, "total": tot, "recall": round(100 * c / tot, 1)}
                          for t, (c, tot) in by.items()}}
    tag = args.model.replace("/", "_")
    (out_dir / f"attack_{Path(args.split).stem}_{tag}.json").write_text(json.dumps(res, indent=2))

    print(f"\n=== {args.model} on {Path(args.split).name} (n={n}) ===")
    print(f"  recall (harmful caught): {recall}%  ({caught}/{scored}); missed={missed}; unparsed={unparsed}")
    print("  per tactic (caught/total):")
    for t, (c, tot) in sorted(by.items()):
        print(f"    {t:18s} {c}/{tot}  ({round(100*c/tot,1)}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
