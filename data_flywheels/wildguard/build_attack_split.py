#!/usr/bin/env python
"""Phase 1 merge — consolidate harvested recall-misses and carve a held-out
"our-attack" eval split that is NEVER trained on (Phase 4 signal).

Input  : harvest_out/keepers.jsonl   (COMPOSE keepers; judge-confirmed harmful,
                                       base WildGuard missed)
         [--include-auditor]         optionally fold in harvest_out_auditor keepers
Output : attack_split/attack_all.jsonl       deduped union
         attack_split/attack_train.jsonl     held-in (-> Phase 2 train mix)
         attack_split/attack_heldout.jsonl   held-out eval (never trained)
         attack_split/split_summary.json     counts + stratification audit

The split is stratified by tactic and deterministic (fixed seed) so it is
reproducible. The held-out fraction defaults to 20%.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPOSE_KEEPERS = HERE / "harvest_out" / "keepers.jsonl"
AUDITOR_KEEPERS = HERE / "harvest_out_auditor" / "keepers.jsonl"
OUT_DIR = HERE / "attack_split"


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower()


def load_keepers(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heldout-frac", type=float, default=0.20)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--include-auditor", action="store_true",
                    help="fold in the (quarantined) auditor static-probe keepers")
    args = ap.parse_args()

    records: list[dict] = []
    for r in load_keepers(COMPOSE_KEEPERS):
        records.append({
            "prompt": r["prompt"],
            "label": r.get("label", "harmful"),
            "tactic": r.get("tactic", "unknown"),
            "subcategory": r.get("subcategory", "others"),
            "seed": r.get("seed", ""),
            "source": r.get("source", "compose"),
            "judge_reason": r.get("judge_reason", ""),
        })
    if args.include_auditor:
        for r in load_keepers(AUDITOR_KEEPERS):
            records.append({
                "prompt": r["prompt"],
                "label": r.get("label", "harmful"),
                "tactic": "auditor_static",
                "subcategory": "others",
                "seed": "",
                "source": r.get("source", "auditor"),
                "judge_reason": r.get("judge_reason", ""),
            })

    # Dedup by normalized prompt.
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in records:
        k = _norm(r["prompt"])
        if k and k not in seen:
            seen.add(k)
            deduped.append(r)
    n_dupes = len(records) - len(deduped)

    # Deterministic, tactic-stratified held-out split.
    rng = random.Random(args.seed)
    by_tactic: dict[str, list[dict]] = defaultdict(list)
    for r in deduped:
        by_tactic[r["tactic"]].append(r)

    train: list[dict] = []
    heldout: list[dict] = []
    for tactic, rows in sorted(by_tactic.items()):
        rows = rows[:]
        rng.shuffle(rows)
        n_hold = max(1, round(len(rows) * args.heldout_frac)) if len(rows) > 1 else 0
        heldout.extend(rows[:n_hold])
        train.extend(rows[n_hold:])

    rng.shuffle(train)
    rng.shuffle(heldout)

    OUT_DIR.mkdir(exist_ok=True)

    def dump(path: Path, rows: list[dict]) -> None:
        with path.open("w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    dump(OUT_DIR / "attack_all.jsonl", deduped)
    dump(OUT_DIR / "attack_train.jsonl", train)
    dump(OUT_DIR / "attack_heldout.jsonl", heldout)

    summary = {
        "total_raw": len(records),
        "duplicates_dropped": n_dupes,
        "total_deduped": len(deduped),
        "heldout_frac": args.heldout_frac,
        "seed": args.seed,
        "train": len(train),
        "heldout": len(heldout),
        "by_tactic": {
            t: {"total": len(rows),
                "train": sum(1 for x in train if x["tactic"] == t),
                "heldout": sum(1 for x in heldout if x["tactic"] == t)}
            for t, rows in sorted(by_tactic.items())
        },
        "subcategory_all": dict(Counter(r["subcategory"] for r in deduped).most_common()),
    }
    (OUT_DIR / "split_summary.json").write_text(json.dumps(summary, indent=2))

    print("=" * 64)
    print("attack split")
    print("=" * 64)
    print(f"  raw records         {len(records)}")
    print(f"  duplicates dropped  {n_dupes}")
    print(f"  deduped             {len(deduped)}")
    print(f"  -> train (held-in)  {len(train)}")
    print(f"  -> heldout (eval)   {len(heldout)}")
    print()
    print("  per tactic (total / train / heldout):")
    for t, s in summary["by_tactic"].items():
        print(f"    {t:18s} {s['total']:4d} / {s['train']:4d} / {s['heldout']:4d}")
    print()
    print(f"  wrote -> {OUT_DIR}")


if __name__ == "__main__":
    main()
