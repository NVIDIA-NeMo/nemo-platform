<!--
  SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
  SPDX-License-Identifier: Apache-2.0
-->

# NeMo Jailbreak Detect Plugin

Self-hosted deployment of the **NemoGuard JailbreakDetect** model, decoupled from
the NVIDIA NIM. The plugin owns the model's deployment lifecycle and exposes a
**NIM-compatible** HTTP contract, so the `nemoguardrails` library needs no
changes — you point it at your deployment instead of `build.nvidia.com` or the
NIM container.

## What it is

The NemoGuard JailbreakDetect "model" is a two-stage pipeline:

1. **Embedder** — `Snowflake/snowflake-arctic-embed-m-long` transformer (CLS pooling), used as a frozen feature extractor.
2. **Classifier** — a scikit-learn **random forest** exported to ONNX (`snowflake.onnx` from `nvidia/NemoGuard-JailbreakDetect`), run on CPU via `onnxruntime`.

`src/nemo_jailbreak_detect/model/` lifts that pipeline out of the library and
wraps it in a small FastAPI server (`model/server.py` + `model/Dockerfile`).

## Surfaces

| Surface | Entry point | Purpose |
|---|---|---|
| Service | `nemo.services` → `jailbreak-detect` | Deployment CRUD + `classify` proxy at `/apis/jailbreak-detect` |
| Controller | `nemo.controllers` → `jailbreak-detect` | Reconciles deployments against a backend (Docker now; Jobs/k8s extension point) |
| CLI | `nemo.cli` → `jailbreak-detect` | `nemo jailbreak-detect deploy \| status \| teardown` |

The **entity** `JailbreakDetectorDeployment` is the source of truth: the service
writes desired state, the controller drives `pending → starting → running` and
writes back `endpoint_url`/`status`.

## Model server HTTP contract (NIM-compatible)

- `POST /v1/classify` — body `{"input": "<prompt>"}` → `{"jailbreak": <bool>, "score": <float>}`
- `GET  /v1/health/ready` → `{"object": "health-response", "message": "ready"}`

## Install

Self-contained (not a workspace member), like `example-plugin`:

```bash
uv sync
uv pip install -e plugins/nemo-jailbreak-detect/
```

To install by default with the platform, add `nemo-jailbreak-detect-plugin` to
the root `pyproject.toml` `enabled-plugins` group and register it as a workspace
member.

## Build the model image

```bash
cd plugins/nemo-jailbreak-detect/src/nemo_jailbreak_detect/model
docker build -t nemo/jailbreak-detect:0.1.0 .
```

> `nvidia/NemoGuard-JailbreakDetect` is a gated Hugging Face repo — ensure your
> build environment is authenticated.

## Use it

1. Deploy: `nemo jailbreak-detect deploy --workspace default --name jbd --device cpu`
2. Wait for `status` to report `running`, then read `endpoint_url`.
3. Point guardrails at it (no library change):

```yaml
rails:
  input:
    flows:
      - jailbreak detection model
  config:
    jailbreak_detection:
      # endpoint_url already includes the scheme, e.g. http://localhost:8000
      nim_base_url: "<endpoint_url>"
      nim_server_endpoint: "/v1/classify"
```

## Backends

- **`docker`** (default): the controller manages a local container via the `docker` CLI. The endpoint is resolved as `http://localhost:<port>`, so this backend assumes the controller and container share a host (local/dev). Each deployment needs a **distinct host port**; a collision surfaces as a `docker run` bind error that marks the deployment `failed`.
- **`jobs`**: not yet implemented; an extension point in `deployment/backend.py` for running on the platform Jobs/Executor system (k8s/slurm). Entities and the controller are already backend-agnostic.

Deleting a deployment marks it `stopping`; the controller stops the backend and removes the entity on its next cycle. If the controller is not running, the entity stays in `stopping` until it is.

## Tests

```bash
cd plugins/nemo-jailbreak-detect
uv run pytest
```
