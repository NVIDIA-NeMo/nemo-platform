#!/usr/bin/env python
"""Phase 2 — assemble the WildGuard fine-tuning dataset (automodel SFT format).

The whole point (per plan.md "balance is load-bearing"): training ONLY on the
harvested recall-misses would teach WildGuard that adversarial *framing* == harmful
and wreck precision (over-refusal). So the train mix is deliberately balanced:

    positives   = 218 held-in COMPOSE keepers       -> Harmful request: yes   (the gap)
    contrast    = WildGuardMix adversarial-benign    -> Harmful request: no    (framing != harm)
    replay      = WildGuardMix vanilla +/- , adv-harmful   (preserve general behavior)

Every row is rendered to WildGuard's exact prompt-only template (empty response =>
"Response refusal: N/A / Harmful response: N/A", confirmed against the live model
and the paper's Table 12). Output is automodel SFT JSONL: {"prompt","completion"}.

Eval hygiene: replay/contrast are sampled from wildguard_TRAIN.parquet only;
WildGuardTest stays 100% held-out. The 54 held-out attack prompts are adversarial
rewrites that do not appear in WildGuardMix.

Usage:
    .venv/bin/python data_flywheels/wildguard/build_dataset.py
    .venv/bin/python data_flywheels/wildguard/build_dataset.py --adv-benign 300 --val-frac 0.08
"""

from __future__ import annotations

import argparse
import glob
import json
import random
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(HERE))
from baseline_eval import render  # noqa: E402  (exact WildGuard input template)

TRAIN_GLOB = (
    "/home/albcui/.cache/huggingface/hub/"
    "datasets--allenai--wildguardmix/snapshots/*/train/wildguard_train.parquet"
)
KEEPERS_TRAIN = HERE / "attack_split" / "attack_train.jsonl"
OUT_DIR = HERE / "train_data"

COMPLETION = "Harmful request: {v}\nResponse refusal: N/A\nHarmful response: N/A"


def completion_for(harmful: bool) -> str:
    return COMPLETION.format(v="yes" if harmful else "no")


def record(prompt: str, harmful: bool, meta: dict) -> dict:
    return {
        "prompt": render(prompt),
        "completion": completion_for(harmful),
        "meta": meta,
    }


def load_keepers() -> list[dict]:
    rows = [json.loads(l) for l in KEEPERS_TRAIN.read_text().splitlines() if l.strip()]
    out = []
    for r in rows:
        out.append(record(r["prompt"], harmful=True,
                          meta={"bucket": "keeper", "tactic": r.get("tactic"),
                                "subcategory": r.get("subcategory"), "source": "compose"}))
    return out


def sample_bucket(df: pd.DataFrame, adversarial: bool, harmful: bool, n: int,
                  rng: random.Random) -> list[dict]:
    label = "harmful" if harmful else "unharmful"
    sub = df[(df["adversarial"] == adversarial) & (df["prompt_harm_label"] == label)]
    idx = list(sub.index)
    rng.shuffle(idx)
    idx = idx[:n]
    bucket = f"{'adv' if adversarial else 'van'}_{'harm' if harmful else 'benign'}"
    out = []
    for i in idx:
        row = df.loc[i]
        out.append(record(str(row["prompt"]), harmful=harmful,
                          meta={"bucket": bucket, "adversarial": bool(adversarial),
                                "subcategory": row.get("subcategory"), "source": "wildguardmix"}))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adv-benign", type=int, default=300, help="matched adversarial-benign contrast")
    ap.add_argument("--adv-harm", type=int, default=150, help="in-distribution adversarial-harmful replay")
    ap.add_argument("--van-harm", type=int, default=200, help="vanilla-harmful replay")
    ap.add_argument("--van-benign", type=int, default=250, help="vanilla-benign replay")
    ap.add_argument("--val-frac", type=float, default=0.08)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)

    rng = random.Random(args.seed)
    df = pd.read_parquet(glob.glob(TRAIN_GLOB)[-1])
    # prompt-only subset only (keeps every example in the same N/A template)
    df = df[df["response"].isna() | (df["response"].astype(str).str.strip() == "")].copy()
    df = df[df["prompt_harm_label"].isin(["harmful", "unharmful"])]
    df = df.reset_index(drop=True)

    keepers = load_keepers()
    contrast = sample_bucket(df, adversarial=True, harmful=False, n=args.adv_benign, rng=rng)
    adv_harm = sample_bucket(df, adversarial=True, harmful=True, n=args.adv_harm, rng=rng)
    van_harm = sample_bucket(df, adversarial=False, harmful=True, n=args.van_harm, rng=rng)
    van_benign = sample_bucket(df, adversarial=False, harmful=False, n=args.van_benign, rng=rng)

    all_rows = keepers + contrast + adv_harm + van_harm + van_benign
    # dedup by exact prompt text
    seen: set[str] = set()
    deduped = []
    for r in all_rows:
        if r["prompt"] not in seen:
            seen.add(r["prompt"])
            deduped.append(r)
    rng.shuffle(deduped)

    n_val = round(len(deduped) * args.val_frac)
    val = deduped[:n_val]
    train = deduped[n_val:]

    out_dir.mkdir(parents=True, exist_ok=True)

    def dump(path: Path, rows: list[dict]) -> None:
        with path.open("w") as fh:
            for r in rows:
                fh.write(json.dumps({"prompt": r["prompt"], "completion": r["completion"]}) + "\n")

    dump(out_dir / "train.jsonl", train)
    dump(out_dir / "validation.jsonl", val)

    # audit trail (with meta) so we can inspect composition later
    with (out_dir / "train_full.jsonl").open("w") as fh:
        for r in deduped:
            fh.write(json.dumps(r) + "\n")

    def counts(rows):
        from collections import Counter
        c = Counter(r["meta"]["bucket"] for r in rows)
        harmful = sum(1 for r in rows if r["completion"].startswith("Harmful request: yes"))
        return dict(c), harmful, len(rows) - harmful

    bc, h, b = counts(deduped)
    summary = {
        "total": len(deduped), "train": len(train), "validation": len(val),
        "harmful": h, "benign": b, "buckets": bc, "seed": args.seed,
    }
    (out_dir / "dataset_summary.json").write_text(json.dumps(summary, indent=2))

    print("=" * 60)
    print("WildGuard fine-tune dataset (automodel SFT)")
    print("=" * 60)
    print(f"  total {len(deduped)}  (train {len(train)} / val {len(val)})")
    print(f"  harmful {h}  /  benign {b}")
    print("  buckets:")
    for k, v in sorted(bc.items()):
        print(f"    {k:14s} {v}")
    print(f"\n  wrote -> {out_dir}/train.jsonl, validation.jsonl, train_full.jsonl")


if __name__ == "__main__":
    main()
