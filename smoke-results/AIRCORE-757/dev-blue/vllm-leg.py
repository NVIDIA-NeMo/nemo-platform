#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""AIRCORE-757 vLLM/GPU reference leg (dev-blue).

Run inside the nemo-platform pod with NMP_BASE_URL pointing at the platform.
Uses direct HTTP for fileset creation because the generated files CLI currently
raises: 'FilesResource' object has no attribute 'filesets'.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ["NMP_BASE_URL"].rstrip("/")
WS = "default"

FILESET = "aircore757b-qwen3-1-7b"
MODEL = "aircore757b-qwen3-1-7b"
CONFIG = "aircore757b-qwen3-vllm-config"
DEPLOYMENT = "aircore757b-qwen3-vllm-deployment"


def request(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    url = f"{BASE}{path}"
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload


def create_or_get(path: str, body: dict) -> dict:
    code, payload = request("POST", path, body)
    if code in {200, 201}:
        print(f"POST {path} -> {code}")
        return payload if isinstance(payload, dict) else {"raw": payload}
    if code == 409:
        name = body["name"]
        code, payload = request("GET", f"{path}/{name}")
        print(f"GET existing {path}/{name} -> {code}")
        if code == 200 and isinstance(payload, dict):
            return payload
    raise RuntimeError(f"POST {path} failed: {code} {payload}")


def wait_deployment(timeout: int = 1800) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        code, payload = request("GET", f"/apis/models/v2/workspaces/{WS}/deployments/{DEPLOYMENT}")
        if code != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"deployment get failed: {code} {payload}")
        last = payload
        print(f"deployment status={payload.get('status')} message={payload.get('status_message')}")
        if payload.get("status") in {"READY", "FAILED", "LOST"}:
            return payload
        time.sleep(10)
    raise TimeoutError(f"timed out waiting for deployment; last={last}")


def main() -> int:
    fileset = create_or_get(
        f"/apis/files/v2/workspaces/{WS}/filesets",
        {
            "name": FILESET,
            "purpose": "model",
            "storage": {"type": "huggingface", "repo_id": "Qwen/Qwen3-1.7B", "repo_type": "model"},
        },
    )
    model = create_or_get(
        f"/apis/models/v2/workspaces/{WS}/models",
        {"name": MODEL, "fileset": f"{WS}/{FILESET}"},
    )
    config = create_or_get(
        f"/apis/models/v2/workspaces/{WS}/deployment-configs",
        {
            "name": CONFIG,
            "engine": "vllm",
            "model_spec": {"model_namespace": WS, "model_name": MODEL},
            "executor_config": {"gpu": 1},
        },
    )
    deployment = create_or_get(
        f"/apis/models/v2/workspaces/{WS}/deployments",
        {"name": DEPLOYMENT, "config": CONFIG},
    )

    deployment = wait_deployment()
    if deployment.get("status") != "READY":
        raise RuntimeError(f"vLLM deployment did not become READY: {deployment}")

    code, chat = request(
        "POST",
        f"/apis/inference-gateway/v2/workspaces/{WS}/provider/{DEPLOYMENT}/-/v1/chat/completions",
        {
            "model": f"{WS}/{MODEL}",
            "messages": [{"role": "user", "content": "Hello from AIRCORE-757 smoke. Reply in one short sentence."}],
            "max_tokens": 80,
        },
    )
    if code != 200:
        raise RuntimeError(f"chat failed: {code} {chat}")

    out = {
        "fileset": fileset,
        "model": model,
        "config": config,
        "deployment": deployment,
        "chat": chat,
    }
    out_path = "/work/smoke-results/AIRCORE-757/vllm-leg-api.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"PASS — wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
