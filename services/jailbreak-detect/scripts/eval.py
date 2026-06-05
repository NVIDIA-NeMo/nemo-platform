# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Black-box evaluation of a jailbreak `/v1/classify` endpoint on JailbreakHub.

Treats the model server as an opaque HTTP endpoint (contract:
``POST {"input": prompt}`` -> ``{"jailbreak": bool, "score": float}``), so the
SAME script and SAME frozen subset can score your local server or a hosted
reference service, then compare.

Two steps:

  1) sample  — draw a reproducible, stratified subset of walledai/JailbreakHub
               and freeze it to a JSONL (prompts inlined, so it's stable even if
               the upstream dataset changes). Needs the `datasets` library.

  2) run     — POST each prompt in the frozen subset to a `/v1/classify`
               endpoint, write per-row results, and print metrics vs the labels.
               Needs only `httpx`.

Reproducibility: `sample` materializes the exact prompts+labels to `--out`; reuse
that one file for every `run`. The subset is also deterministic given `--seed`.

Examples
--------
    cd services/jailbreak-detect

    # 1) Freeze a balanced 200+200 subset (deterministic, seeded):
    uv run --with datasets python scripts/eval.py sample \\
        --out scripts/eval_subset.jsonl --n-pos 200 --n-neg 200 --seed 0

    # 2a) Score your local server (the default target; start it first:
    #     `uv run python model/server.py start`):
    uv run python scripts/eval.py run \\
        --subset scripts/eval_subset.jsonl --out results_local.jsonl

    # 2b) Score a hosted reference service (needs an API key):
    NVIDIA_API_KEY=nvapi-... uv run python scripts/eval.py run \\
        --subset scripts/eval_subset.jsonl \\
        --base-url https://ai.api.nvidia.com \\
        --endpoint /v1/security/nvidia/nemoguard-jailbreak-detect \\
        --api-key-env NVIDIA_API_KEY --out results_hosted.jsonl

Note on sampling: a *balanced* subset gives tight estimates of both FPR and FNR
(the prevalence-independent rates the model card reports: FPR 0.0042, FNR 0.0435).
Precision/F1/accuracy depend on prevalence, so they are NOT directly comparable to
the model card at balanced sampling — set --n-pos/--n-neg to the natural ~1:9.8
ratio if you want comparable F1.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

import httpx

DATASET = "walledai/JailbreakHub"

# Default target is the local server; override --base-url/--endpoint (and supply an
# API key via --api-key-env) to score a hosted service instead.
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_ENDPOINT = "/v1/classify"

# Published NemoGuard-JailbreakDetect model-card numbers on JailbreakHub, for reference.
CARD_F1, CARD_FPR, CARD_FNR = 0.9601, 0.0042, 0.0435


def cmd_sample(args: argparse.Namespace) -> int:
    from datasets import load_dataset

    ds = load_dataset(DATASET, split="train")
    pos = [r["prompt"] for r in ds if r["jailbreak"]]
    neg = [r["prompt"] for r in ds if not r["jailbreak"]]
    print(f"Dataset: {len(pos)} jailbreak / {len(neg)} benign", file=sys.stderr)

    rng = random.Random(args.seed)
    rng.shuffle(pos)
    rng.shuffle(neg)
    chosen = [(1, p) for p in pos[: args.n_pos]] + [(0, p) for p in neg[: args.n_neg]]
    rng.shuffle(chosen)

    out = Path(args.out)
    with out.open("w") as f:
        for i, (label, prompt) in enumerate(chosen):
            f.write(json.dumps({"id": i, "label": label, "prompt": prompt}) + "\n")
    n_pos = sum(lbl for lbl, _ in chosen)
    print(f"Wrote {len(chosen)} rows ({n_pos} jailbreak / {len(chosen) - n_pos} benign) to {out} [seed={args.seed}]")
    return 0


def _roc_auc(labels: list[int], scores: list[float]) -> float:
    """Threshold-free ranking quality (Mann-Whitney U; handles ties). O(n_pos*n_neg)."""
    pos = [s for s, lbl in zip(scores, labels) if lbl == 1]
    neg = [s for s, lbl in zip(scores, labels) if lbl == 0]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def cmd_run(args: argparse.Namespace) -> int:
    rows = [json.loads(line) for line in Path(args.subset).read_text().splitlines() if line.strip()]

    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = args.base_url.rstrip("/") + "/" + args.endpoint.lstrip("/")

    print(f"Scoring {len(rows)} prompts against {url}", file=sys.stderr)
    results: list[dict] = []
    errors = 0
    with httpx.Client(timeout=args.timeout) as client:
        for i, row in enumerate(rows):
            try:
                resp = client.post(url, headers=headers, json={"input": row["prompt"]})
                resp.raise_for_status()
                data = resp.json()
                results.append({**row, "jailbreak": bool(data["jailbreak"]), "score": data.get("score")})
            except Exception as exc:  # noqa: BLE001 — record and continue
                errors += 1
                results.append({**row, "error": str(exc)[:200]})
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(rows)} ({errors} errors)", file=sys.stderr)

    if args.out:
        Path(args.out).write_text("\n".join(json.dumps(r) for r in results) + "\n")

    _report(results, errors, url)
    return 0


def _confusion(data: list[dict], predict) -> tuple[int, int, int, int]:
    """Count (tp, fp, tn, fn) using ``predict(row) -> 0/1`` against ``row['label']``."""
    tp = fp = tn = fn = 0
    for r in data:
        pred, label = int(predict(r)), int(r["label"])
        if pred and label:
            tp += 1
        elif pred and not label:
            fp += 1
        elif (not pred) and label:
            fn += 1
        else:
            tn += 1
    return tp, fp, tn, fn


def _rates(tp: int, fp: int, tn: int, fn: int) -> dict:
    """Derive precision/recall/F1/FPR/FNR from a confusion matrix."""
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": tp / (tp + fp) if (tp + fp) else float("nan"),
        "recall": tp / (tp + fn) if (tp + fn) else float("nan"),  # = 1 - FNR
        "f1": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else float("nan"),
        "fpr": fp / (fp + tn) if (fp + tn) else float("nan"),
        "fnr": fn / (fn + tp) if (fn + tp) else float("nan"),
    }


def _load_scored(path: str) -> list[dict]:
    """Load a results JSONL, keeping only rows that have a prediction (drop errors)."""
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return [r for r in rows if "jailbreak" in r]


def _auc_of(data: list[dict]) -> float:
    have = [r for r in data if isinstance(r.get("score"), (int, float))]
    if len(have) != len(data) or not have:
        return float("nan")
    return _roc_auc([int(r["label"]) for r in have], [float(r["score"]) for r in have])


def _report(results: list[dict], errors: int, url: str) -> None:
    scored = [r for r in results if "jailbreak" in r]
    m = _rates(*_confusion(scored, lambda r: r["jailbreak"]))
    auc = _auc_of(scored)

    print(f"\n=== {url} ===")
    print(f"scored={len(scored)}  errors={errors}")
    print(f"confusion: TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}")
    print(f"precision = {m['precision']:.4f}")
    print(f"recall    = {m['recall']:.4f}")
    print(f"F1        = {m['f1']:.4f}   (model card: {CARD_F1})")
    print(f"FPR       = {m['fpr']:.4f}   (model card: {CARD_FPR})")
    print(f"FNR       = {m['fnr']:.4f}   (model card: {CARD_FNR})")
    print(f"ROC-AUC   = {auc:.4f}   (threshold-free; from returned scores)")
    print("\nNote: precision/F1 depend on the subset's prevalence; FPR/FNR/ROC-AUC do not.")


def cmd_sweep(args: argparse.Namespace) -> int:
    """Threshold sweep on a results JSONL's returned scores (no endpoint calls)."""
    data = _load_scored(args.results)
    scored = [r for r in data if isinstance(r.get("score"), (int, float))]
    if len(scored) < len(data):
        print(f"warning: {len(data) - len(scored)} rows lack scores; excluded", file=sys.stderr)
    if not scored:
        print("No scored rows to sweep.", file=sys.stderr)
        return 1

    auc = _auc_of(scored)
    default = _rates(*_confusion(scored, lambda r: r["jailbreak"]))  # endpoint's own verdict

    best_t, best = None, None
    for t in sorted({float(r["score"]) for r in scored}):
        m = _rates(*_confusion(scored, lambda r, t=t: float(r["score"]) >= t))
        if best is None or m["f1"] > best["f1"]:
            best_t, best = t, m

    assert best is not None and best_t is not None

    print(f"\n=== sweep: {args.results}  (n={len(scored)}, ROC-AUC={auc:.4f}) ===")
    print(f"{'operating point':<22}{'F1':>8}{'recall':>9}{'precision':>11}{'FPR':>8}{'FNR':>8}")
    print("-" * 66)
    print(
        f"{'default (endpoint)':<22}{default['f1']:>8.3f}{default['recall']:>9.3f}"
        f"{default['precision']:>11.3f}{default['fpr']:>8.3f}{default['fnr']:>8.3f}"
    )
    print(
        f"{'best-F1 @ ' + format(best_t, '+.3f'):<22}{best['f1']:>8.3f}{best['recall']:>9.3f}"
        f"{best['precision']:>11.3f}{best['fpr']:>8.3f}{best['fnr']:>8.3f}"
    )
    if args.threshold is not None:
        at = _rates(*_confusion(scored, lambda r: float(r["score"]) >= args.threshold))
        label = f"@ {args.threshold:+.3f}"
        print(
            f"{label:<22}{at['f1']:>8.3f}{at['recall']:>9.3f}{at['precision']:>11.3f}{at['fpr']:>8.3f}{at['fnr']:>8.3f}"
        )
    print(
        "\nNote: 'best-F1' overfits this subset and (on a balanced subset) its FPR is not at "
        "natural prevalence — calibrate a production threshold on a larger held-out set."
    )
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Side-by-side metrics for two or more results files + per-prompt agreement."""
    paths: list[str] = args.results
    if len(paths) < 2:
        print("compare needs at least two results files.", file=sys.stderr)
        return 2

    datas = [_load_scored(p) for p in paths]

    print(f"{'results':<28}{'F1':>8}{'recall':>9}{'precision':>11}{'FPR':>8}{'FNR':>8}{'ROC-AUC':>9}")
    print("-" * 81)
    for path, data in zip(paths, datas):
        m = _rates(*_confusion(data, lambda r: r["jailbreak"]))
        auc = _auc_of(data)
        name = path if len(path) <= 27 else "…" + path[-26:]
        print(
            f"{name:<28}{m['f1']:>8.3f}{m['recall']:>9.3f}{m['precision']:>11.3f}"
            f"{m['fpr']:>8.3f}{m['fnr']:>8.3f}{auc:>9.3f}"
        )

    # Agreement is computed on the prompt ids shared by *all* files, so every
    # number below is over the same set of prompts.
    maps = [{r["id"]: int(r["jailbreak"]) for r in data} for data in datas]
    common = sorted(set.intersection(*(set(m) for m in maps)))
    if not common:
        print("\nNo prompt ids shared by all files (were they run on the same subset?).")
        return 0

    if len(paths) == 2:
        agree = sum(maps[0][i] == maps[1][i] for i in common)
        print(f"\nVerdict agreement on {len(common)} shared prompts: {agree}/{len(common)} = {agree / len(common):.3f}")
        return 0

    # N > 2: unanimous agreement + a pairwise agreement matrix.
    unanimous = sum(len({m[i] for m in maps}) == 1 for i in common)
    print(
        f"\nUnanimous verdict agreement on {len(common)} shared prompts: "
        f"{unanimous}/{len(common)} = {unanimous / len(common):.3f}"
    )
    print("\nPairwise verdict agreement:")
    for idx, path in enumerate(paths, start=1):
        print(f"  [{idx}] {path}")
    print("      " + "".join(f"{idx:>7}" for idx in range(1, len(paths) + 1)))
    for i in range(len(paths)):
        cells = []
        for j in range(len(paths)):
            if i == j:
                cells.append(f"{'—':>7}")
            else:
                agree = sum(maps[i][k] == maps[j][k] for k in common)
                cells.append(f"{agree / len(common):>7.3f}")
        print(f"  [{i + 1}] " + "".join(cells))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sample", help="Freeze a reproducible stratified subset to JSONL.")
    s.add_argument("--out", required=True, help="Output JSONL path (the frozen subset).")
    s.add_argument("--n-pos", type=int, default=200, help="Number of jailbreak prompts.")
    s.add_argument("--n-neg", type=int, default=200, help="Number of benign prompts.")
    s.add_argument("--seed", type=int, default=0, help="RNG seed (determinism).")
    s.set_defaults(func=cmd_sample)

    r = sub.add_parser("run", help="Score a frozen subset against a /v1/classify endpoint.")
    r.add_argument("--subset", required=True, help="Frozen subset JSONL from `sample`.")
    r.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Server base URL. Default: %(default)s")
    r.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Classification path. Default: %(default)s")
    r.add_argument(
        "--api-key-env",
        default="",
        help="Optional env var holding a bearer token. Default: none (the local server needs no auth); "
        "set e.g. NVIDIA_API_KEY to score a hosted service.",
    )
    r.add_argument("--timeout", type=float, default=60.0)
    r.add_argument("--out", default=None, help="Optional results JSONL path.")
    r.set_defaults(func=cmd_run)

    sw = sub.add_parser("sweep", help="Threshold sweep on a results JSONL's scores (no endpoint calls).")
    sw.add_argument("--results", required=True, help="Results JSONL written by `run`.")
    sw.add_argument("--threshold", type=float, default=None, help="Also report metrics at this score threshold.")
    sw.set_defaults(func=cmd_sweep)

    c = sub.add_parser("compare", help="Side-by-side metrics + agreement for two or more results files.")
    c.add_argument(
        "results",
        nargs="+",
        help="Two or more results JSONL files (e.g. results_local.jsonl results_hosted.jsonl).",
    )
    c.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
