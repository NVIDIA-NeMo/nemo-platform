# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Ground-truth capture: score the shared prompt set with the real NemoGuard NIM.

Hits the hosted NIM on build.nvidia.com (or any NIM URL) and prints the
jailbreak verdict + score per prompt. Use this to validate the locally-decomposed
recipe against the authoritative model.

Usage:
    export NVIDIA_API_KEY=nvapi-...
    cd services/jailbreak-detect
    uv run python scripts/nim_scores.py                 # hosted build.nvidia.com
    uv run python scripts/nim_scores.py --base-url http://localhost:8123  # local NIM

Compare the output against the local recipe (see the runbook's recipe
experiment, which reads the same scripts/prompts.json).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://ai.api.nvidia.com"
CLASSIFY_PATH = "/v1/security/nvidia/nemoguard-jailbreak-detect"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--path", default=CLASSIFY_PATH, help="Classification endpoint path.")
    parser.add_argument("--prompts", default=str(Path(__file__).with_name("prompts.json")))
    args = parser.parse_args()

    api_key = os.environ.get("NVIDIA_API_KEY", "")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = args.base_url.rstrip("/") + "/" + args.path.lstrip("/")
    prompts = json.loads(Path(args.prompts).read_text())

    print(f"NIM: {url}\n")
    print(f"{'expected':<11}{'jailbreak':<11}{'score':>10}  prompt")
    print("-" * 78)
    with httpx.Client(timeout=30) as client:
        for item in prompts:
            resp = client.post(url, headers=headers, json={"input": item["text"]})
            resp.raise_for_status()
            data = resp.json()
            jb = data.get("jailbreak")
            score = data.get("score")
            score_str = f"{score:.4f}" if isinstance(score, (int, float)) else str(score)
            print(f"{item['label']:<11}{str(jb):<11}{score_str:>10}  {item['text'][:44]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
