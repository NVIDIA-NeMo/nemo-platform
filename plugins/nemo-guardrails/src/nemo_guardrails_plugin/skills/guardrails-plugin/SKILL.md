---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
name: guardrails-plugin
description: Use when working on guardrailing chat completions through the Inference Gateway — creating guardrail configs, attaching the `nemo-guardrails` middleware to a VirtualModel, verifying configs with the `/checks` endpoint, or debugging input/output rail behavior.
metadata:
  owner: guardrails
  maturity: active
---

# Guardrails Plugin

Use this skill when the task is about applying input/output rails to chat-completions traffic served by the NeMo Inference Gateway (IGW). The plugin runs as an in-process inference middleware on the IGW path; the customer-facing surfaces are:

- `nemo guardrail configs ...` — CRUD on the `GuardrailConfig` entity (stored rails configurations).
- `nemo guardrail check` — standalone evaluator that runs rails against a single message without going through IGW. Use this to validate a config before binding it to a VirtualModel.
- `nemo virtual-models create|update` — attaches the plugin via `--request-middleware` / `--response-middleware`.
- `nemo inference gateway model post v1/chat/completions <vm-name>` — guardrailed chat call.

## Current Surfaces

- An `nemo.inference_middleware` plugin registered under the key `nemo-guardrails`.
- A `GuardrailConfig` entity exposed through `nemo guardrail configs`.
- A standalone `/v2/workspaces/{workspace}/checks` endpoint exposed through `nemo guardrail check`.
- A `MiddlewareCall` contract (`name: "nemo-guardrails"`, `config_type: "guardrail_config"`) consumed by IGW VirtualModels via `--request-middleware` and `--response-middleware`.

## CLI Quickstart

> **Prerequisites**
> - Activate the Python virtual environment before invoking the CLI: `source .venv/bin/activate`. `nemo` and `nmp` are aliases for the same binary.
> - The default workspace is `default`; override with `--workspace <name>` or `NMP_WORKSPACE`.
> - For `nemo guardrail check` alone you need a config and a main LLM entity reachable through IGW. For chat-time guardrailing on a VirtualModel you also need a real backend model entity the VirtualModel can proxy to (see the `nemo-secrets` and `inference` skills for provider setup).

### 1 — Create a guardrail config

Self-check input rail against the request's main LLM (no task LLM required):

```bash
nemo guardrail configs create content-safety \
  --workspace default \
  --description "Self-check input rail" \
  --data '{
    "rails": {"input": {"flows": ["self check input"]}},
    "prompts": [{
      "task": "self_check_input",
      "content": "Your task is to check if the user message below complies with safety policy.\n\nUser message: {{ user_input }}\n\nQuestion: Should this message be blocked (Yes or No)?\nAnswer:"
    }]
  }'
```

For larger payloads prefer `--input-file config.json` over inline `--data` JSON.

The remaining CRUD verbs follow the same shape — pass only the fields you want to change on `update`:

```bash
nemo guardrail configs list
nemo guardrail configs get <name>
nemo guardrail configs update <name> --description "<new description>"
nemo guardrail configs delete <name>
```

### 2 — Verify the config with `/checks`

```bash
nemo guardrail check \
  --workspace default \
  --model default/<main-model> \
  --messages '[{"role": "user", "content": "Your message here"}]' \
  --guardrails '{"config_id": "default/content-safety"}' \
  --max-tokens 256
```

`--model` is the LLM the rails self-check against; any task LLMs the config references (e.g. `content_safety`) must also be reachable through IGW. A blocked response has `"status": "blocked"` in the output.

### 3 — Attach the config to a VirtualModel

Output rails only (block bad bot responses):

```bash
nemo virtual-models create vm-guarded \
  --workspace default \
  --models '[{"model":"default/<backend-model>","backend_format":"OPENAI_CHAT"}]' \
  --response-middleware '[{
    "name":"nemo-guardrails",
    "config_type":"guardrail_config",
    "config_id":"default/content-safety"
  }]'
```

For input rails only, swap in `--request-middleware`. For full coverage, attach the **same** `MiddlewareCall` to **both** lists — each list dispatches its hook independently, so a config with both `rails.input.flows` and `rails.output.flows` attached to only one list silently no-ops on the other side.

Inline configs work too — replace `config_id` with `config`:

```json
{
  "name": "nemo-guardrails",
  "config_type": "guardrail_config",
  "config": {"rails": {...}, "prompts": [...]}
}
```

### 4 — Make a guardrailed chat call

```bash
nemo inference gateway model post v1/chat/completions vm-guarded \
  --workspace default \
  --body '{
    "model":"default/<backend-model>",
    "messages":[{"role":"user","content":"Hello"}],
    "max_tokens":256
  }'
```

`body["model"]` is the backend entity ID and also acts as the rails' **main** LLM (self-check flows call it). The VirtualModel name comes from the URL path.

When a rail blocks, the response content is exactly:

```
I'm sorry, I can't respond to that.
```

For streaming responses, set `"stream": true` in the body and `rails.output.streaming.chunk_size` in the config. The canned refusal arrives as a single non-streamed chunk if an output rail blocks mid-stream.

## MiddlewareCall Contract

```json
{
  "name": "nemo-guardrails",
  "config_type": "guardrail_config",
  "config_id": "<workspace>/<config-name>"
}
```

- `name` is always `"nemo-guardrails"` (the entry-point key).
- `config_type` is always `"guardrail_config"`.
- Provide `config_id` for stored configs (recommended — easier to update and reuse) or `config` for inline rails payloads.

## Rails Config

The plugin consumes the standard `nemoguardrails` `RailsConfig` shape. The **main** LLM is always the request's model (the `body["model"]` on chat completions) or `--model` (on `nemo guardrail check`) — entries with `type: "main"` in `models[]` are ignored. Add `models[]` only for task LLMs (`content_safety`, `topic_control`, `jailbreak_detection`, `embeddings`) that flows explicitly reference via `$model=<type>`.

See [Rails Config Reference](resources/rails-config.md) for the field reference, full-coverage examples (self-check input + output), custom keyword-blocking prompts, and streaming output rails.

For content-safety classifiers, see [Content Safety with a Task LLM](resources/content-safety.md).

## Common Gotchas

- **VirtualModels live at the top level** as `nemo virtual-models` (with hyphen), not under `nemo inference` and not `virtualmodels`.
- **For standalone verification, use `nemo guardrail check`.** For guardrailed chat completions, use `nemo inference gateway model post v1/chat/completions <vm-name>`.
- **Names are positional** for `nemo guardrail configs create <name>` and `nemo virtual-models create <name>`.
- **`--data` (configs) and `--body` / `--models` / `--*-middleware` (VirtualModels) take JSON strings.** Watch shell quoting for embedded backticks/quotes — prefer `--input-file` for large payloads.
- **The `guardrails` field on a chat-completions request body is options-only** (`options.log`, `return_choice`). It does **not** set the rails config — that comes from the VirtualModel's `MiddlewareCall`. Unsupported fields like `guardrails.config_id` are rejected with `422`.
- **Each middleware list dispatches its own hook independently.** For input + output coverage, attach to both `--request-middleware` and `--response-middleware`.
- **Output rails reject `n > 1`** in the completion request, and streaming with output rails requires `rails.output.streaming.enabled=true` when a streaming subsection is supplied — otherwise the plugin rejects the path with `400`.
- **Task LLMs and the main LLM must be reachable through IGW.** Use auto-discovered entity IDs from `nemo inference providers get ... | jq '.served_models[].model_entity_id'` for both `--models` and any `models[]` entry in the rails config. The provider reconciler re-syncs `served_models` from upstream auto-discovery and drops manually-registered entries on every refresh.

See [Guardrails Troubleshooting](resources/troubleshooting.md) for symptom→fix tables, the agentic-use mock-LLM harness, and failure-case deep dives.

## Config Updates

IGW's `StabilizedRailsConfigCache` is keyed on `(workspace, name, updated_at)`. A `PATCH` or `DELETE` on a `GuardrailConfig` advances `updated_at`, so the next IGW request retrieves the new entity, misses the cache, and rebuilds — there is no explicit cross-service invalidation, the freshness comes from the cache key. Inline `config` payloads have no entity revision to key on and are re-stabilized on every request.

## Python SDK

The plugin doesn't ship its own SDK accessor — guardrail configs and VirtualModel attachment go through the platform SDK:

```python
from nemo_platform import NeMoPlatform

client = NeMoPlatform(base_url="http://localhost:8080", workspace="default")
configs = client.guardrail.configs.list()
```

VirtualModels are created via `client.inference.virtual_models.create(...)` with `request_middleware` / `response_middleware` lists of `MiddlewareCall` dicts.
