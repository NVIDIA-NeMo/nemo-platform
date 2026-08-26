<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Dataset formats

All three backends read JSONL from a platform fileset, but the **row shape and the job-JSON dataset block differ**. Pick the section that matches your plugin (automodel, unsloth, rl/DPO, or rl/GRPO).

Upload the JSONL files at the **fileset root**, then reference the fileset from the job JSON `dataset` block. The filenames differ by backend, so keep the contracts separate:

- **SFT (automodel, unsloth):** upload `train.jsonl` and optional `validation.jsonl`. Automodel points `dataset.training` / `dataset.validation` at the fileset; unsloth uses `dataset.path` (and `dataset.validation_path`).
- **rl (DPO):** upload both `training.jsonl` **and** `validation.jsonl` to a single fileset, referenced by one `dataset` string (no separate validation ref) — see § NeMo-RL (DPO).
- **rl (GRPO):** upload `training.jsonl` (required) and optional `validation.jsonl` to a single fileset. Rows are **NeMo Gym rollout rows**, not prompt/completion and not preference triples — see § NeMo-RL (GRPO).

## Automodel

Automodel detects schema from the **first JSONL line** (`DatasetSchema` in `services/automodel/.../datasets/preparation.py`).

| Schema | JSONL shape | Job JSON |
|--------|-------------|----------|
| **CHAT** (preferred when model has chat template) | `{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}` | (none) |
| **SFT** | `{"prompt": "...", "completion": "..."}` | (none) |
| **CUSTOM** | Any two columns, e.g. `{"input": "...", "output": "..."}` | `"prompt_template": "{input} {output}"` on `dataset` |
| **EMBEDDING** | `{"query": "...", "pos_doc": "...", "neg_doc": ["...", "..."]}` | embedding training type when applicable |

**Conversion preference:** CHAT if `AutoTokenizer(...).chat_template` or model `spec.is_chat` / `spec.chat_template` → else SFT. Use CUSTOM or EMBEDDING only when the user asks or the task requires it.

For **CUSTOM**, placeholders in `prompt_template` must match column names exactly (two placeholders).

## Unsloth

Unsloth has no schema auto-detection — the row shape is controlled by two `dataset` fields in the job JSON. The training driver hands rows to `trl.SFTTrainer`, which only reads one column (`text_field`) per row.

| Mode | `dataset.apply_chat_template` | Required JSONL shape | What the trainer sees |
|------|------------------------------|----------------------|----------------------|
| **Messages (preferred)** | `true` | `{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}` (same as automodel CHAT) | Each row's `messages` is rendered through `tokenizer.apply_chat_template(...)` at training time; the rendered string is written into `text_field` (default `"text"`). |
| **Pre-rendered text** | `false` (default) | `{"text": "<one fully-formed training string>"}` | The string in `text_field` is fed to SFTTrainer verbatim. |

Job JSON snippets:

```json
"dataset": { "path": "default/<dataset-fileset>", "apply_chat_template": true }
```

```json
"dataset": { "path": "default/<dataset-fileset>", "text_field": "text", "apply_chat_template": false }
```

Optional fields on the unsloth `dataset` block:

| Field | Default | Notes |
|-------|---------|-------|
| `validation_path` | `null` | Same ref shape as `path` (`"name"` or `"workspace/name"`). |
| `text_field` | `"text"` | Column the trainer reads. In messages mode it's the column the rendered string is **written to** before training. |
| `apply_chat_template` | `false` | Set `true` only when each row has a `messages` array. |
| `packing` | `false` | `trl.SFTTrainer` packing — concatenates short rows up to `max_seq_length` for throughput. Needs short, compatible rows; safe to leave off. |

**Conversion guidance:**

- If the model has a chat template (`AutoTokenizer.from_pretrained(...).chat_template` is truthy), use the same `to_chat` converter from `references/hf-conversion.md` and set `apply_chat_template: true`. This is the recommended path for instruction-tuned models.
- If the model has **no** chat template, render each example to a single training string yourself (e.g. `f"{prompt}\n{completion}"`) and emit `{"text": "..."}` rows. Then set `apply_chat_template: false` and keep `text_field: "text"`.
- The automodel SFT format `{"prompt": "...", "completion": "..."}` is **not** directly consumable by unsloth — unsloth has no built-in `prompt`/`completion` concatenation. Convert to either messages or pre-rendered text before upload.

EMBEDDING and CUSTOM (automodel-only schemas) are not supported by unsloth today.

## Post-training evaluation

Eval rows must use the **same CHAT `messages` shape** as training. Do not flatten to `prompt`/`expected` for the evaluator.

| Training JSONL | Eval dataset | Eval `prompt_template` | Metric reference |
|----------------|--------------|------------------------|------------------|
| `messages` (single- or multi-turn) | Same fileset split (`validation.jsonl`) | `messages[:-1]` — exclude final assistant label — see `post-training-eval.md` | `{{ item.messages[-1].content }}` |

LoRA inference and eval use the **provider** gateway on the **base** entity (`/provider/<name>/-/v1`, `model: default--<adapter>`). Base model uses the model-entity path. Full SFT / merged checkpoints use the **output** model entity's model-entity URL — deploy first. See `post-training-eval.md` and the **Using the adapter** / **Using the fine-tuned model** sections in `reporting.md`.

Shared helpers and compare CLI: `references/eval_helpers.py`. Full workflow: `references/post-training-eval.md`.

## NeMo-RL (GRPO) — NeMo Gym rollout rows

GRPO has **no labelled completions**. A row is a prompt plus enough routing information for the environment to run a rollout against it and score the result. The reward comes from the environment, not the file.

The dataset FileSet holds `training.jsonl` (required) and optionally `validation.jsonl`, referenced by the single `dataset` string. The environment is a **separate** FileSet — see `gym-environments.md`.

### Row schema

Source of truth: `GymDatasetRow` / `GymVerifiersDatasetRow` in `services/rl/src/nmp/rl/schemas/environment.py`. Validated at submit time by `DatasetValidator` with `training_type=grpo`.

```json
{
  "task_idx": 0,
  "vf_env_id": "ascii-tree",
  "responses_create_params": {"input": [{"role": "user", "content": "Draw a binary tree of depth 3."}]},
  "agent_ref": {"type": "responses_api_agents", "name": "verifiers_agent"},
  "question": "Draw a binary tree of depth 3.",
  "answer": "",
  "task": "ascii-tree",
  "example_id": "ex-0",
  "info": {}
}
```

| Key | Required | Meaning |
|---|---|---|
| `responses_create_params` | **yes** | The prompt, in OpenAI **Responses API** shape. The messages go under `input`, not at the row's top level. NeMo-RL also reads this to apply per-row sampling settings. |
| `agent_ref` | **yes** | `{"type": "responses_api_agents", "name": "<agent>"}`. Routes the row to an agent. `type` is the only allowed value; `name` must match the agent the environment declares (`verifiers_agent` for a converted package). |
| `vf_env_id` | verifiers envs | Passed to `verifiers.load_environment()`. Must equal the environment manifest's `metadata.vf_env_id`. |
| `task_idx` | verifiers envs | Row index. Required on the verifiers row type. |
| `answer` | no | Reference answer the environment scores against. Default `""`. Whether it is used at all is the environment's business. |
| `task` | no | Task label, conventionally the env id. Default `""`. |
| `example_id` | no | Stable id for the source example. Int or string, default `0`. |
| `info` | no | Free-form dict passed through to the environment. Default `{}`. |
| `question` | no | The last user message, denormalized for readability. |

**Extra keys are allowed and passed through** (`extra="allow"`), which is how environment-specific fields ride along. Note that any numeric key an environment returns in its result becomes a per-environment metric on the job — see `reporting.md`.

### Common mistakes

| Wrong | Right |
|---|---|
| `{"messages": [...]}` at the top level | Nest under `responses_create_params.input` |
| `{"prompt": "...", "completion": "..."}` | GRPO has no completions; the environment produces and scores them |
| `{"prompt": ..., "chosen": ..., "rejected": ...}` | That is DPO — see the next section |
| `"agent_ref": "verifiers_agent"` | An **object**: `{"type": "responses_api_agents", "name": "verifiers_agent"}` |
| `vf_env_id` differing from the manifest | They must match, or validation rejects the row |
| Prompt JSONL uploaded into the environment FileSet | Separate dataset FileSet; `.jsonl` in the env package is rejected |

### Converting a dataset to Gym rows

**Converted hub environments need no work** — `pi-to-gym-conversion` writes `training.jsonl` (and `validation.jsonl` with `--validation-fraction`) alongside the package. Use those.

For your own prompts, one row per prompt. `dataset_row_from_verifiers` in `services/rl/src/nmp/rl/tasks/environment/package.py` is the canonical shape; this mirrors it:

```python
import json

def gym_row(idx, prompt_text, *, vf_env_id, answer="", agent="verifiers_agent"):
    return {
        "task_idx": idx,
        "vf_env_id": vf_env_id,
        "responses_create_params": {"input": [{"role": "user", "content": prompt_text}]},
        "agent_ref": {"type": "responses_api_agents", "name": agent},
        "question": prompt_text,
        "answer": answer,
        "task": vf_env_id,
        "example_id": f"ex-{idx}",
        "info": {},
    }

with open("training.jsonl", "w", encoding="utf-8") as f:
    for i, ex in enumerate(examples):                    # e.g. a HF dataset split
        row = gym_row(i, ex["question"], vf_env_id="ascii-tree", answer=ex.get("answer", ""))
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

Multi-turn context goes in `input` as additional messages, in order — the same `role`/`content` dicts, ending with the turn the model must respond to.

### Validation sampling

`validate()` runs **exactly one rollout per row** of `validation.jsonl` — there is no validation counterpart to `num_generations_per_prompt`. To score a prompt *k* times (mean@k), repeat its **row** *k* times. Validation cost is therefore just the row count, and `val_at_start` / `val_at_end` score the same rows, which makes the before/after comparison paired.

## NeMo-RL (DPO) — preference data

DPO trains on **preference pairs**, not prompt→completion examples. The `rl` backend takes a **single** dataset fileset that must contain **both** `training.jsonl` **and** `validation.jsonl` at the fileset root (unlike automodel/unsloth, the dataset block in the job JSON is a single ref — there is no separate validation ref).

The dataset-preparation step **auto-detects the row schema from the first line** and selects the matching NeMo-RL loader. **Three preference formats are supported** (platform schemas `BinaryPreferenceDatasetItemSchema` / `HelpSteer3DatasetItemSchema` / `Tulu3PreferenceDatasetItemSchema`):

### Binary preference (`BinaryPreferenceDataset`)

Simple `prompt` / `chosen` / `rejected` — the `prompt` may be a plain string **or** a list of chat messages:

```json
{"prompt": "What is the capital of France?", "chosen": "The capital of France is Paris.", "rejected": "I'm not sure."}
```

| Key | Meaning |
|-----|---------|
| `prompt` | The input/context shown to the model (string or list of chat messages). |
| `chosen` | The preferred (higher-reward) response. |
| `rejected` | The dispreferred response. |

### HelpSteer3 (`HelpSteer3`)

A conversation `context` (string or chat messages), two candidate responses, and a signed `overall_preference` in **-3..3** — **negative** means `response1` is preferred, **positive** means `response2`, **0** is a tie. This is the **raw** schema of `nvidia/HelpSteer3` (the `preference` subset), so no conversion is needed:

```json
{"context": [{"role": "user", "content": "Explain how to use git rebase"}], "response1": "...", "response2": "...", "overall_preference": -2}
```

### Tulu3 preference (`Tulu3Preference`)

Full chat conversations for both branches — `chosen` and `rejected` are each a **list of messages** ending with the assistant turn:

```json
{"chosen": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "preferred"}], "rejected": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "dispreferred"}]}
```

Whichever format you upload, the job JSON dataset block is just the single fileset ref:

```json
"dataset": "default/<preference-fileset>"
```

**Notes**
- Upload both files to the **same** fileset (`--remote-path training.jsonl` and `--remote-path validation.jsonl`).
- `prompt` may be a plain string; the model's chat template is applied at training time (override with `training.chat_template` only when needed).
- DPO is **full-weight** — there is no LoRA/adapter dataset variant. The output is a full model checkpoint.

