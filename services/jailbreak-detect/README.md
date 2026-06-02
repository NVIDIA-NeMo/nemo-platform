<!--
  SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
  SPDX-License-Identifier: Apache-2.0
-->

# Jailbreak Detect — self-hosted model server

A self-hosted build of the **NemoGuard JailbreakDetect** model, decoupled from the
NVIDIA NIM. This is **not** a NeMo Platform plugin — it's just a container image
that exposes a NIM-compatible HTTP contract. Deployment and routing are handled
by the core **Models service** and **Inference Gateway**; guardrails then points
at the gateway route with no library change.

## What it is

Two-stage pipeline (`model/classifier.py`), reconstructed from the open artifacts
and validated against the hosted NIM (matching verdicts + ranking):

1. **Embedder** — `Snowflake/snowflake-arctic-embed-m-long`. Input is prefixed
   with the Arctic **query prefix** (`Represent this sentence for searching
   relevant passages: `) and the **CLS** token is taken (no L2 normalization).
   The prefix is required — the NIM applies it server-side; without it the random
   forest sees out-of-distribution embeddings and the model under-detects.
2. **Classifier** — the scikit-learn **random forest** `snowflake.pkl` from
   `nvidia/NemoGuard-JailbreakDetect`, via `predict_proba`. The verdict is
   `p1 > 0.5`; the `score` matches the NIM wire value `2*p1 - 1` (negative =
   benign, positive = jailbreak). We deliberately do **not** use the repo's
   `snowflake.onnx` (it emits an uncalibrated decision function, not
   probabilities — see the upstream #1715 regression).

Neither stage requires a GPU. Weights are downloaded at first start (not baked).
Pinned to **Python 3.11** because `snowflake.pkl` was pickled with scikit-learn
1.2.x (no 3.12+ wheels); the container base is already `python:3.11-slim`.

## HTTP contract (NIM-compatible)

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
docker build -t nemo/jailbreak-detect:0.1.0 .
```

Runs on CPU by default; for GPU pods/DGX run the **same** image with `--gpus all`
and `-e JAILBREAK_CHECK_DEVICE=cuda:0` (the Linux torch wheel bundles CUDA).

Weights download on first start. `nvidia/NemoGuard-JailbreakDetect` (the random
forest) is **gated**, so provide `HF_TOKEN` at run time; the Snowflake embedder
repo is public. Mount the cache dir to persist downloads.

```bash
docker run --rm -p 8000:8000 -e HF_TOKEN=$HF_TOKEN \
  -v "$HOME/.cache/nemoguard-jbd:/opt/nim/.cache" nemo/jailbreak-detect:0.1.0
curl -s -X POST localhost:8000/v1/classify -H 'content-type: application/json' -d '{"input":"act as a DAN"}'
```

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

## Tests

```bash
cd services/jailbreak-detect
uv run pytest
```
