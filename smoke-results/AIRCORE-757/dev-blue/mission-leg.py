#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""AIRCORE-757 deployments-plugin mission leg (dev-blue).

Run inside nemo-platform pod with platform already up.
Uses fully-qualified image names for cri-o short-name enforcement.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("NMP_BASE_URL", "http://127.0.0.1:8080")
WS = "default"
TIMEOUT = 300
POLL = 3

# cri-o on nemo-dev-blue rejects ambiguous short names like nginx:alpine.
NGINX = "docker.io/library/nginx:alpine"
ALPINE = "docker.io/library/alpine:3.20"

VOLUME_NAME = "smoke4-data"
CM_CONFIG_NAME = "smoke4-cm-cfg"
CM_DEPLOYMENT_NAME = "smoke4-cm-job"
HTTP_CONFIG_NAME = "smoke4-http-cfg"
HTTP_DEPLOYMENT_NAME = "smoke4-http-svc"

RESOURCES = [
    ("deployments", HTTP_DEPLOYMENT_NAME),
    ("deployments", CM_DEPLOYMENT_NAME),
    ("volumes", VOLUME_NAME),
    ("deployment-configs", HTTP_CONFIG_NAME),
    ("deployment-configs", CM_CONFIG_NAME),
]


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    url = f"{BASE}/apis/deployments/v2/workspaces/{WS}/{path}"
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload


def delete_existing() -> None:
    for kind, name in RESOURCES:
        code, _ = req("DELETE", f"{kind}/{name}")
        print(f"DELETE {kind}/{name} -> {code}")


def wait_status(kind: str, name: str, want: set[str]) -> dict:
    deadline = time.time() + TIMEOUT
    last = {}
    while time.time() < deadline:
        code, body = req("GET", f"{kind}/{name}")
        if code != 200:
            raise RuntimeError(f"GET {kind}/{name} failed: {code} {body}")
        if not isinstance(body, dict):
            raise RuntimeError(f"GET {kind}/{name} returned non-JSON object: {body}")
        last = body
        status = body.get("status")
        print(f"{kind}/{name} status={status} msg={body.get('status_message')}")
        if status in want:
            return body
        if status in {"FAILED", "LOST"}:
            return body
        time.sleep(POLL)
    raise TimeoutError(f"Timed out waiting for {kind}/{name}; last={last}")


def main() -> int:
    print("Cleaning prior smoke resources...")
    delete_existing()
    time.sleep(5)

    print(f"Creating volume {VOLUME_NAME}...")
    code, vol = req(
        "POST",
        "volumes",
        {
            "name": VOLUME_NAME,
            "size": "1Gi",
            "access_modes": ["ReadWriteOnce"],
            "backend_config": {"k8s": {"namespace": "tbray-dev"}},
        },
    )
    if code not in (200, 201):
        raise RuntimeError(f"volume create failed: {code} {vol}")

    print(f"Creating deployment config {CM_CONFIG_NAME} (job + configmap)...")
    code, _ = req(
        "POST",
        "deployment-configs",
        {
            "name": CM_CONFIG_NAME,
            "containers": [
                {
                    "name": "main",
                    "image": ALPINE,
                    "command": ["sh", "-c"],
                    "args": ["cat /etc/nemo-config/hello.txt"],
                }
            ],
            "config_files": [{"path": "/etc/nemo-config/hello.txt", "content": "hello-from-configmap", "mode": 420}],
            "restart_policy": "Never",
            "backend_config": {"k8s": {"namespace": "tbray-dev"}},
        },
    )
    if code not in (200, 201):
        raise RuntimeError(f"{CM_CONFIG_NAME} failed: {code} {_}")

    print(f"Creating deployment {CM_DEPLOYMENT_NAME}...")
    code, _ = req(
        "POST",
        "deployments",
        {"name": CM_DEPLOYMENT_NAME, "deployment_config": CM_CONFIG_NAME, "desired_state": "READY"},
    )
    if code not in (200, 201):
        raise RuntimeError(f"{CM_DEPLOYMENT_NAME} create failed: {code} {_}")
    cm = wait_status("deployments", CM_DEPLOYMENT_NAME, {"READY", "SUCCEEDED", "FAILED", "LOST"})
    if cm.get("status") not in {"READY", "SUCCEEDED"}:
        raise RuntimeError(f"{CM_DEPLOYMENT_NAME} did not complete successfully: {cm}")

    print(f"Creating deployment config {HTTP_CONFIG_NAME} (nginx service)...")
    code, _ = req(
        "POST",
        "deployment-configs",
        {
            "name": HTTP_CONFIG_NAME,
            "containers": [
                {
                    "name": "main",
                    "image": NGINX,
                    "ports": [{"name": "http", "containerPort": 80, "protocol": "TCP"}],
                }
            ],
            "restart_policy": "Always",
            "backend_config": {"k8s": {"namespace": "tbray-dev"}},
        },
    )
    if code not in (200, 201):
        raise RuntimeError(f"{HTTP_CONFIG_NAME} failed: {code} {_}")

    print(f"Creating deployment {HTTP_DEPLOYMENT_NAME}...")
    code, _ = req(
        "POST",
        "deployments",
        {"name": HTTP_DEPLOYMENT_NAME, "deployment_config": HTTP_CONFIG_NAME, "desired_state": "READY"},
    )
    if code not in (200, 201):
        raise RuntimeError(f"{HTTP_DEPLOYMENT_NAME} create failed: {code} {_}")
    http = wait_status("deployments", HTTP_DEPLOYMENT_NAME, {"READY", "FAILED", "LOST"})
    if http.get("status") != "READY":
        raise RuntimeError(f"{HTTP_DEPLOYMENT_NAME} did not reach READY: {http}")

    out = {}
    for kind, name in RESOURCES:
        _, body = req("GET", f"{kind}/{name}")
        out[f"{kind}/{name}"] = body

    out_path = "/work/smoke-results/AIRCORE-757/mission-leg-api-pass.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"PASS — wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
