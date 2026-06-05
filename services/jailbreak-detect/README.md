<!--
  SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
  SPDX-License-Identifier: Apache-2.0
-->

# JailbreakDetect — self-hosted model server

A self-hosted build of the **NemoGuard JailbreakDetect** model. This is **not** a
NeMo Platform plugin — it's just a container image that exposes the HTTP contract the
guardrails jailbreak-detection rail expects. Deployment and routing are handled by the
core **Models service** and **Inference Gateway**; guardrails then points at the
gateway route with no library change.

## What it is

Two-stage pipeline (`model/classifier.py`):

1. **Embedder** — `Snowflake/snowflake-arctic-embed-m-long`. Input is embedded as
   **raw text** (no Arctic query prefix) and the **CLS** token is taken (no L2
   normalization). Empirically this beats the prefixed variant on a balanced
   400-prompt JailbreakHub sample across every metric incl. threshold-free ROC-AUC
   (0.916 vs 0.893). The Arctic query prefix is
   an asymmetric *retrieval* device; this is a classifier head trained on unprefixed
   embeddings, so prefixing just shifts inputs off-distribution.
2. **Classifier** — the scikit-learn **random forest** `snowflake.pkl` from
   `nvidia/NemoGuard-JailbreakDetect`, via `predict_proba`. The verdict is
   `p1 > 0.5`; the `score` is the signed max-probability (`-p0` when benign,
   `+p1` when jailbreak). The repo's `snowflake.onnx` emits an uncalibrated decision
   function rather than probabilities (degraded accuracy, skews to false positives), so
   we serve the `snowflake.pkl` path; the ONNX variant is kept only as a documented
   reference (`JailbreakClassifierONNX`), not wired into the server.

Neither stage requires a GPU. Weights are downloaded at first start (not baked).
Pinned to **Python 3.11** because `snowflake.pkl` was pickled with scikit-learn
1.2.x (no 3.12+ wheels); the container base is already `python:3.11-slim`.

## HTTP contract

- `POST /v1/classify` — `{"input": "<prompt>"}` → `{"jailbreak": <bool>, "score": <float>}`
- `GET  /v1/health/ready` → `{"object": "health-response", "message": "ready"}`
- `GET  /v1/models` → OpenAI-style model list

## Local development (uv)

Standalone uv project (not part of the platform workspace):

```bash
cd services/jailbreak-detect
uv sync                                   # create .venv from uv.lock
uv run pytest                             # tests

# Run the server (weights download on first call; gated repo needs HF_TOKEN):
export HF_TOKEN=...
JAILBREAK_CHECK_DEVICE=cpu uv run python model/server.py start --port 8000
```

## Build the image

One uv-managed image, built from this directory:

```bash
cd services/jailbreak-detect
docker buildx build -t nemo/jailbreak-detect:0.1.0 --load .
```

Runs on CPU by default; for GPU pods/DGX run the **same** image with `--gpus all`
and `-e JAILBREAK_CHECK_DEVICE=cuda:0`.

Weights download on first start. `nvidia/NemoGuard-JailbreakDetect` (the random
forest) is **gated**, so provide `HF_TOKEN` at run time; the Snowflake embedder
repo is public. Mount the cache dir to persist downloads.

```bash
docker run --rm -p 8000:8000 -e HF_TOKEN=$HF_TOKEN \
  -v "$HOME/.cache/nemoguard-jbd:/opt/jailbreak-detect/.cache" nemo/jailbreak-detect:0.1.0
curl -s -X POST localhost:8000/v1/classify -H 'content-type: application/json' -d '{"input":"act as a DAN"}'
```

The container runs as a non-root user (UID 1000), so the bind-mounted cache
directory must be writable by that user. On Linux this is automatic when your
host user is UID 1000; otherwise add `--user "$(id -u):0"` to the `docker run`
(or pre-create and `chown` the host dir). macOS Docker Desktop bind mounts
generally just work.

## Deploy via Models + Inference Gateway

No plugin needed — use the core `nemo inference` commands. The deployment config
has no `model_name`/`model_namespace`, so the Models controller skips its model
puller and just runs the container; the server downloads its own weights.

```bash
# 1. Create the deployment config from the recipe (add HF_TOKEN to additional_envs
#    for the gated weights, or pre-seed a mounted cache; prefer a platform Secret
#    for shared deployments).
nemo inference deployment-configs create jbd-config \
  --input-file deploy/deployment-config.json

# 2. Create the deployment (controller runs the container; --wait blocks until READY)
nemo inference deployments create jbd --config jbd-config --wait

# 3. The controller mints a ModelProvider on READY; route to it via IGW passthrough.
nemo inference deployments get jbd
```

Point guardrails at the IGW provider passthrough (no library change):

```yaml
rails:
  input:
    flows: [jailbreak detection model]
  config:
    jailbreak_detection:
      nim_base_url: "<base>/apis/inference-gateway/v2/workspaces/<ws>/provider/jbd/-"
      nim_server_endpoint: "/v1/classify"
```

Tear down: `nemo inference deployments delete jbd`.

## Evaluating the model

We use the same [JailbreakHub](https://huggingface.co/datasets/walledai/JailbreakHub) dataset the `NemoGuard-JailbreakDetect` model used.

```bash
cd services/jailbreak-detect
JAILBREAK_CHECK_DEVICE=cpu uv run python model/server.py start --port 8000 &

# Freeze a balanced JailbreakHub subset once, then score it via an endpoint.
uv run python scripts/eval.py sample --out subset.jsonl
uv run python scripts/eval.py run --subset subset.jsonl \
  --base-url http://localhost:8000 --endpoint /v1/classify --out results_pkl.jsonl
```

## Tests

```bash
cd services/jailbreak-detect
uv run pytest                     # fast, mocked unit tests
uv run pytest --run-integration   # also loads the real model on CPU (slow; downloads weights)
```

The `integration`-marked tests load the real embedder + random forest (CPU is
fine, just slow; the first run downloads weights, and the gated forest needs
`HF_TOKEN`). They're skipped unless you pass `--run-integration`, and skip with a
clear message if the weights can't be fetched.
