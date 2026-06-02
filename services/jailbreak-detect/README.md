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

Two-stage pipeline (`model/classifier.py`), ported from the `nemoguardrails`
library so it can run independently of the NIM:

1. **Embedder** — `Snowflake/snowflake-arctic-embed-m-long` (CLS pooling), a frozen feature extractor.
2. **Classifier** — a scikit-learn **random forest** exported to ONNX (`snowflake.onnx` from `nvidia/NemoGuard-JailbreakDetect`), run on CPU via `onnxruntime`.

Neither stage requires a GPU. Weights are downloaded at first start (not baked).

## HTTP contract (NIM-compatible)

- `POST /v1/classify` — `{"input": "<prompt>"}` → `{"jailbreak": <bool>, "score": <float>}`
- `GET  /v1/health/ready` → `{"object": "health-response", "message": "ready"}`
- `GET  /v1/models` → OpenAI-style model list

## Build the image

```bash
cd services/jailbreak-detect/model

# CPU (local / Apple Silicon)
docker build -t nemo/jailbreak-detect:0.1.0 -f Dockerfile .

# GPU (pods / DGX)
docker build -t nemo/jailbreak-detect:0.1.0-gpu -f Dockerfile-GPU .
```

Weights download on first start. `nvidia/NemoGuard-JailbreakDetect` (the random
forest) is **gated**, so provide `HF_TOKEN` at run time; the Snowflake embedder
repo is public. Run it directly to smoke-test:

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
uv run pytest    # or: PYTHONPATH=model pytest tests
```
