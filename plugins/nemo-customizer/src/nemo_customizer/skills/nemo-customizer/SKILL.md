---
name: nemo-customizer
description: >-
  Fine-tune models on NeMo Platform with `automodel` (`submit` → GPU containers on
  the platform) or `unsloth` (`run --venv` → local in-process, BYO-venv): HF dataset
  conversion, filesets, model entities, SFT/LoRA job JSON (hyperparameters, batch,
  schedule, optimizer), and job polling. Use for train, fine-tune, customize, SFT,
  LoRA, learning rate, epochs, or nemo customization.
triggers:
  - nemo-customizer
  - nemo customizer
  - fine-tune
  - fine tune
  - finetune
  - train a model
  - customize a model
  - sft
  - lora
  - automodel
  - unsloth
  - nemo customization
  - nemo-customization
  - customizer
  - customization training
  - automodel submit
not-for:
  - nemo-build-agent (agent scaffold/deploy, not weight training)
  - nemo-explore (agent design only)
  - safe-synthesizer (tabular synthetic data training)
compatibility: >-
  Requires nemo-customizer-plugin and a customization contributor (`nemo.customization.contributors`).
  Platform must expose jobs, files, and models APIs.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Grep]
---

# NeMo Customizer

End-to-end **SFT + LoRA** on NeMo Platform. Two backend plugins ship in this repo:

| Backend | Verb | Where it runs | Pick when |
|---------|------|---------------|-----------|
| **`automodel`** (default) | `submit` | Platform-managed GPU containers (jobs service) | Platform exposes a GPU execution profile, or the user wants a persisted job they can poll/share |
| **`unsloth`** | `run --venv <path>` | **Locally**, in a BYO-venv re-exec on the caller's GPU | User asks for Unsloth, the platform has **no GPU execution profile**, or the user wants a quick single-GPU local SFT/LoRA |

Decision rule below in **Plugin pick**. Batch shell work; reuse resources with `--exist-ok`; skip CLI `--help` unless a command fails.

## Plugin pick

1. After `nemo auth login`, run `uv run nemo jobs list-execution-profiles -f json` (see `references/troubleshooting.md` for parsing).
2. If the user explicitly asked for Unsloth → **`unsloth`**.
3. Else if any profile has `provider: gpu` or `gpu_distributed` → **`automodel`** (default).
4. Else if the caller machine has a usable local GPU → **`unsloth`** (after the `--venv` one-time setup below).
5. Else stop and tell the user remote GPU customization is unavailable.

**Unsloth `--venv` requirement.** The base `nemo` install has no Unsloth/torch. Before the first `unsloth run`, set up a separate venv with the heavy ML extras (one-time):

```bash
UNSLOTH_VENV=/workspace/.venv-unsloth
uv venv "$UNSLOTH_VENV" --python 3.11
uv pip install --python "$UNSLOTH_VENV/bin/python" -e plugins/nemo-unsloth[unsloth]
```

Then every `unsloth run` passes `--venv "$UNSLOTH_VENV"`. The platform re-execs into that interpreter before importing `unsloth`. Without `--venv`, the run errors with an actionable setup hint.

## Gotchas

- Run all `uv run` commands from the **nemo-platform** git root (top-level `pyproject.toml`), not a plugin subfolder.
- Set `NEMO_BASE_URL` (or `NMP_BASE_URL`) only when the user gives a platform URL; default `http://127.0.0.1:8080`.
- **Verb is backend-specific.** Automodel is **`submit` only** (no local `run`). Unsloth is **`run` only** (no `submit`); a stray `nemo customization unsloth submit ...` exits non-zero with a friendly hint. Do not improvise verbs.
- **Never set `max_steps` together with `epochs`** (both backends). `max_steps` is a global cap and stops mid-epoch. Test fixtures include `max_steps` for smoke tests — do not copy into production jobs. Unsloth's schema enforces this as a hard mutex; automodel allows both but the result is surprising.
- **Job done (automodel) = top-level `status`** in `completed` | `error` | `cancelled`. Steps can all be `completed` while the job is still `active` (upload, entity registration). `status_details.phase` may stay `training` with `progress_pct: 100` for a long time — keep polling. `poll_automodel_job.sh` exits **1** on `error` or `cancelled`.
- **Job done (unsloth) = `nemo customization unsloth run` returns.** It is synchronous and in-process — the result dict (`loss`, `output_path`, `output_fileset`, `output_model_entity`) prints to stdout. There is no remote job record to poll.
- Model spec fills async: **submit without polling** `nemo models get` unless submit fails.
- HF dataset id from the user → convert locally; do not ask for local paths first.
- Dataset fileset name = HF dataset **name** only (`tau/commonsense_qa` → `commonsense_qa`), not the model name.
- Prefer **CHAT** JSONL when the model has a chat template; details in `references/dataset-formats.md` (automodel auto-detects schema; unsloth needs `dataset.apply_chat_template: true` to consume `messages`).
- User asks to tune **batch or parallelism** (automodel) → **Batch sizing** / **Multi-GPU** below. Other fields (LR, epochs, LoRA rank, distillation) → `references/hyperparameters.md`. For unsloth, see **Batch sizing — unsloth** and the `Unsloth job JSON` section in `references/hyperparameters.md`. Run `nemo customization <plugin> explain` for the live schema.
- Skill **defaults** (`micro_batch_size` 1, `global_batch_size` 4) are safe on unknown VRAM. When the user has **≥48 GB** on one GPU, use **Batch sizing** instead of defaults. Unsloth's analogues are `batch.per_device_train_batch_size` and `batch.gradient_accumulation_steps` (effective batch = product).
- **Unsloth is single-GPU**. `hardware.gpus` is **selection, not reservation** (sets `CUDA_VISIBLE_DEVICES` before `import torch`). No `parallelism`/TP/PP block exists. Multi-GPU sharding → use automodel.
- **Do not use local `docker info`** to pick automodel vs unsloth. After auth, run `uv run nemo jobs list-execution-profiles -f json` against the user's platform (see `references/troubleshooting.md`). Default output is a table — **`-f json` is required** for scripting; parse **stdout only** (do not pipe `2>&1` into `json.load`).
- For submit/image/plugin errors (both backends) and the unsloth `--venv` install probe, read `references/troubleshooting.md`.

## Workflow

Common steps then **branch by plugin pick**:

```text
- [ ] export NEMO_BASE_URL (if user provided endpoint)
- [ ] cd nemo-platform && uv run nemo auth login --unsigned-token --email <user email or admin@example.com>
- [ ] uv run nemo jobs list-execution-profiles -f json — apply Plugin pick rules above
- [ ] Convert HF dataset → /tmp/train-data/*.jsonl (see references/hf-conversion.md)
- [ ] Create dataset fileset (--exist-ok), upload train.jsonl (+ validation.jsonl), nemo files list to verify
- [ ] Create HF weights fileset + model entity if missing (--exist-ok)

# automodel branch (remote, submit)
- [ ] Write /tmp/job.json (batch sizing for ≥48 GB GPU; else Defaults table)
- [ ] uv run nemo customization automodel submit /tmp/job.json --workspace default
- [ ] Poll until top-level terminal (scripts/poll_automodel_job.sh or 60–120s manual polls)
- [ ] Report using output template below

# unsloth branch (local, run --venv)
- [ ] Ensure $UNSLOTH_VENV is set up (see Plugin pick — Unsloth --venv requirement)
- [ ] Write /tmp/job.json using the UnslothJobInput shape (see Fast path — unsloth)
- [ ] uv run nemo customization unsloth run /tmp/job.json --venv "$UNSLOTH_VENV" --workspace default
- [ ] Read result dict from stdout (loss / output_path / output_fileset / output_model_entity)
- [ ] Report using output template below
```

## Fast path — automodel (remote)

Substitute `<hf-repo>`, `<hf-dataset>`, `<model-entity>`, `<weights-fileset>`, `<dataset-fileset>`, `<output-name>`.

**Setup**

```bash
export NEMO_BASE_URL=http://127.0.0.1:8080   # user override only
cd /path/to/nemo-platform
uv run nemo auth login --unsigned-token --email admin@example.com
uv run nemo jobs list-execution-profiles -f json   # platform GPU profiles → automodel; set training.execution_profile if needed
```

**1. Dataset** — convert per `references/hf-conversion.md`, then:

```bash
DATASET=<dataset-fileset>   # e.g. commonsense_qa
uv run nemo files filesets create "$DATASET" --workspace default --purpose dataset --exist-ok
uv run nemo files upload /tmp/train-data/train.jsonl "$DATASET" --workspace default --remote-path train.jsonl
# validation.jsonl if present
uv run nemo files list "$DATASET" --workspace default
```

**2. Model** — skip if entity exists (`nemo models list --workspace default`).

```bash
WEIGHTS=<weights-fileset>   # e.g. qwen3-1.7b
MODEL_ENTITY=<model-entity>   # Models API entity (not dataset fileset, not HF id)
HF_REPO=<hf-repo>           # e.g. Qwen/Qwen3-1.7B

uv run nemo files filesets create "$WEIGHTS" --workspace default --purpose model --exist-ok \
  --storage '{"type":"huggingface","repo_id":"'"$HF_REPO"'","repo_type":"model","revision":"main"}'

uv run nemo models create "$MODEL_ENTITY" --workspace default --exist-ok \
  --input-data '{"name":"'"$MODEL_ENTITY"'","fileset":"default/'"$WEIGHTS"'","custom_fields":{"hf_model_id":"'"$HF_REPO"'"}}'
```

**3. Job JSON** — write `/tmp/job.json`. `model` is the **registered model entity** (`default/<model-entity>`), not an HF repo id or dataset fileset. Full hyperparameter reference: `references/hyperparameters.md`.

```json
{
  "model": "default/<model-entity>",
  "dataset": {
    "training": "default/<dataset-fileset>",
    "validation": "default/<dataset-fileset>"
  },
  "training": {
    "training_type": "sft",
    "finetuning_type": "lora",
    "lora": { "rank": 16, "alpha": 32 },
    "max_seq_length": 2048
  },
  "schedule": { "epochs": 1 },
  "batch": { "global_batch_size": 4, "micro_batch_size": 1 },
  "optimizer": { "learning_rate": 5e-5, "weight_decay": 0.01, "warmup_steps": 0 },
  "parallelism": { "num_nodes": 1, "num_gpus_per_node": 1, "tensor_parallel_size": 1 },
  "output": { "name": "<output-name>" }
}
```

**4. Submit and poll**

```bash
uv run nemo customization automodel submit /tmp/job.json --workspace default
bash plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/scripts/poll_automodel_job.sh automodel-<job-id> 90
```

Or poll manually: `uv run nemo jobs get-status automodel-<job-id>` every 60–120s.

## Fast path — unsloth (local)

Same substitutions as automodel. Steps 1 (dataset) and 2 (model entity) are identical — the differences are the job JSON shape and the run verb.

**0. One-time `--venv` setup** (skip if `$UNSLOTH_VENV` already passes the import probe):

```bash
export UNSLOTH_VENV=/workspace/.venv-unsloth   # any path you own
uv venv "$UNSLOTH_VENV" --python 3.11
uv pip install --python "$UNSLOTH_VENV/bin/python" -e plugins/nemo-unsloth[unsloth]
# Probe: this must print nothing and exit 0.
"$UNSLOTH_VENV/bin/python" -c "import nemo_platform, nemo_unsloth_plugin, unsloth"
```

**1. Dataset** — same as automodel Fast path step 1.

**2. Model** — same as automodel Fast path step 2.

**3. Job JSON** — write `/tmp/job.json` using the **`UnslothJobInput`** shape (see `references/hyperparameters.md` → *Unsloth job JSON*). `model` is an **object** (not a string), `dataset.path` is a single fileset ref, `hardware.gpus` replaces the `parallelism` block (single GPU). `nemo customization unsloth explain` prints the live schema.

```json
{
  "name": "<job-name>",
  "model": {
    "name": "default/<model-entity>",
    "max_seq_length": 2048,
    "load_in_4bit": true,
    "dtype": "auto"
  },
  "dataset": {
    "path": "default/<dataset-fileset>",
    "text_field": "text",
    "apply_chat_template": true
  },
  "training": {
    "training_type": "sft",
    "finetuning_type": "lora",
    "lora": { "rank": 16, "alpha": 32 }
  },
  "schedule": { "epochs": 1, "warmup_ratio": 0.1 },
  "batch": { "per_device_train_batch_size": 2, "gradient_accumulation_steps": 4 },
  "optimizer": { "learning_rate": 5e-5, "optim": "adamw_8bit" },
  "hardware": { "gpus": "0", "precision": "bf16" },
  "output": { "name": "<output-name>", "save_method": "lora" }
}
```

If the model uses `messages` chat format (preferred when the tokenizer has a chat template), keep `dataset.apply_chat_template: true`. Otherwise emit a single `text` column from your converter and set `apply_chat_template: false`.

**4. Run (no polling — synchronous)**

```bash
uv run nemo customization unsloth run /tmp/job.json --venv "$UNSLOTH_VENV" --workspace default
```

The result dict prints to stdout — capture `output_path`, `output_fileset`, and `output_model_entity` from it. If the command exits with the "Backend 'unsloth' is not importable" message, the `--venv` probe failed: re-run the one-time setup above.

## Defaults

Shared:

| Field | Value |
|-------|-------|
| Workspace | `default` |
| Plugin | `automodel` (override per **Plugin pick**) |
| Training | SFT + LoRA, `max_seq_length` 2048 |
| Schedule | `epochs` ≥ 1; omit `max_steps` |
| Auth email | `admin@example.com` unless user specifies |

Automodel-specific:

| Field | Value |
|-------|-------|
| Parallelism | 1 node, 1 GPU, TP=1 |
| Batch | `global_batch_size` 4, `micro_batch_size` 1 (unknown VRAM; see **Batch sizing** for ≥48 GB) |
| Optimizer | `learning_rate` 5e-5 |

Unsloth-specific:

| Field | Value |
|-------|-------|
| Hardware | `hardware.gpus` `"0"`, `hardware.precision` `bf16` (selection only, single GPU) |
| Model load | `load_in_4bit: true`, `dtype: "auto"` |
| Batch | `batch.per_device_train_batch_size` 2, `batch.gradient_accumulation_steps` 4 (effective batch 8; see **Batch sizing — unsloth** for ≥48 GB ramp) |
| Optimizer | `learning_rate` 5e-5, `optim` `adamw_8bit` |
| Output | `save_method: "lora"` (adapter-only) unless user asks for merged checkpoint |
| Gradient checkpointing | `training.use_gradient_checkpointing: "unsloth"` |

## Batch sizing — automodel (≥48 GB VRAM)

Tables, multi-GPU rules, and the tuning loop below are **automodel-specific** (fields `global_batch_size` / `micro_batch_size` / `tensor_parallel_size` / `num_gpus_per_node`). For unsloth see **Batch sizing — unsloth** further down.

Assume **one GPU with at least 48 GB** (e.g. RTX 5880 / A6000 / L40), `parallelism` = 1 node × 1 GPU, `tensor_parallel_size` 1, bf16, `training_type` `sft`, LoRA **rank 16** unless the user asks otherwise.

**How to size**

1. Read **model size** from the entity (`nemo models get`) or HF card (parameter count).
2. Pick **`finetuning_type`**: `lora` (adapter only, default) vs `all_weights` (full SFT — much heavier).
3. Set **`max_seq_length`** (2048 is the skill default; shorter seq → more batch headroom).
4. Set **`micro_batch_size`** first (drives peak VRAM), then **`global_batch_size`** as a multiple of `micro_batch_size` (gradient accumulation when GBS > micro).

**Constraint:** `global_batch_size` must be divisible by `micro_batch_size × data_parallel_size`, where `data_parallel_size = (num_nodes × num_gpus_per_node) / (tensor_parallel_size × pipeline_parallel_size × context_parallel_size)` (1 for a single-GPU job).

### LoRA (`finetuning_type: lora`) — `max_seq_length` 2048

**VRAM does not scale linearly with `micro_batch_size`.** LoRA loads the full base weights once; activation memory grows slowly. On 48 GB, **`micro_batch_size` must decrease as model size grows** (smaller models always ≥ larger models in the table). Use **`global_batch_size` ≈ 4 × `micro_batch_size`**.

**Default batch** — start here for a reliable full epoch. **High utilization** — optional; double from default (or ramp in steps) to reach **~35–40 GiB**. Halve both if OOM (exit **137**) or training crashes (exit **1**).

| Model params | Default `micro` | Default GBS | `learning_rate` | High-util `micro` | High-util GBS |
|--------------|------------------:|------------:|----------------:|------------------:|--------------:|
| ≤4B | 32 | 128 | `1e-4` | 64 | 256 |
| 4B–8B | 24 | 96 | `8e-5` | 48 | 192 |
| 8B–14B | 16 | 64 | `8e-5` | 24 | 96 |
| >14B | 8 | 32 | `5e-5` | 16 | 64 |

Validated (`commonsense_qa` @ 2048, 48 GB, one job per GPU): **Qwen3-1.7B** — `micro` 16 / GBS 64 ~8 min; defaults above leave headroom to ramp. **Qwen3-8B** — `micro` 2–4 ≈16–18.5 GiB (under-filled); **`micro` 16 / GBS 64** stable default (~153 steps/epoch); high-util **`micro` 24 / GBS 96** (32 / 128 hit ~40 GiB but failed mid-epoch with exit 1).

### Multi-GPU (same node)

Pick the path by whether the **base model fits in ~48 GB on one GPU** (LoRA or full SFT):

| Situation | `tensor_parallel_size` | Goal |
|-----------|------------------------:|------|
| Model **fits** on one ≥48 GB GPU | **1** | **Data parallel** — more GPUs = faster training; keep `micro` per GPU, scale `global_batch_size` |
| Model **does not fit** on one ≥48 GB GPU | **> 1** (e.g. 2 on a 2-GPU node) | **Tensor parallel** — shard layers across GPUs so the model fits; lower `micro` / GBS vs single-GPU tables |

**Data parallel (TP = 1)** — default for Qwen3-8B LoRA and similar on 48 GB cards:

| Rule | Detail |
|------|--------|
| `micro_batch_size` | **Per GPU** — same as a stable single-GPU run |
| `global_batch_size` | ≈ **single-GPU GBS × `num_gpus_per_node`**; step count ≈ `samples / GBS` |
| Divisibility | `global_batch_size` ÷ **`micro_batch_size × num_gpus_per_node`** must be an integer |
| Scheduling | **One job** owns all GPUs; no overlapping 1-GPU and multi-GPU jobs |

```json
"parallelism": { "num_nodes": 1, "num_gpus_per_node": 2, "tensor_parallel_size": 1 },
"batch": { "global_batch_size": 128, "micro_batch_size": 16 }
```

**Tensor parallel (TP > 1)** — when weights + activations OOM on a single ≥48 GB GPU (large full SFT, very long `max_seq_length`, or models above the LoRA sizing table without fitting):

- Set **`num_gpus_per_node`** and **`tensor_parallel_size`** so **`num_gpus_per_node` is divisible by `tensor_parallel_size`** (e.g. 2 GPUs → `tensor_parallel_size: 2`, or 4 GPUs → TP 2 or 4).
- **`data_parallel_size`** = `(num_nodes × num_gpus_per_node) / (tensor_parallel_size × pipeline_parallel_size × context_parallel_size)` — use this in the GBS divisibility rule instead of raw GPU count.
- Start with **lower `micro_batch_size`** than the single-GPU table; increase only if VRAM allows. MoE models: if `expert_parallel_size > 1`, **`tensor_parallel_size` must be 1**.

```json
"parallelism": { "num_nodes": 1, "num_gpus_per_node": 2, "tensor_parallel_size": 2 },
"batch": { "global_batch_size": 8, "micro_batch_size": 1 }
```

`execution_profile` is usually still **`"gpu"`** — confirm with `uv run nemo jobs list-execution-profiles -f json`.

**Example — Qwen3-8B LoRA, 2× 48 GB (fits one GPU):** single-GPU **micro 16 / GBS 64** → 2-GPU data parallel **micro 16 / GBS 128**, `learning_rate` `8e-5`.

### Full-weight SFT (`finetuning_type: all_weights`) — `max_seq_length` 2048

| Model params | `micro_batch_size` | `global_batch_size` | `learning_rate` |
|--------------|-------------------:|--------------------:|----------------:|
| ≤2B | 2 | 8 | `2e-5` |
| 2B–4B | 1 | 4 | `1e-5` |
| 4B–8B | 1 | 2 | `5e-6` |
| >8B | 1 | 1 | lower LR or use TP / shorter seq |

Output type is **model** (full checkpoint), not adapter. Expect much longer runs than LoRA at the same batch.

### `max_seq_length` scaling

Scale **`micro_batch_size`** from the 2048 tables (round down, minimum 1):

| `max_seq_length` | Multiply `micro_batch_size` by |
|------------------|-------------------------------:|
| 512 | 4× |
| 1024 | 2× |
| 2048 | 1× (tables above) |
| 4096 | 0.5× |

Then set `global_batch_size` to a multiple of the new `micro_batch_size` (often keep the same ratio as the table, e.g. GBS = 4 × micro for LoRA).

### LoRA rank

Higher rank uses more VRAM. If OOM at rank 16, drop to rank 8 before lowering batch; if headroom remains, rank 32 is fine for training (deploy rank ≤32 on default NIM/vLLM).

### Tuning loop

| Symptom | Action |
|---------|--------|
| CUDA OOM | Halve `micro_batch_size`, then `global_batch_size`, then `max_seq_length` |
| Slow / low GPU memory use | Step up toward the **high-util** column (or double default `micro`+GBS); stop at ~35–40 GiB or when training fails, then use **default** for the retry |
| User wants max throughput | Raise `micro_batch_size` first; keep GBS ≈ 4× micro — avoid `micro_batch_size` 1 with huge GBS |

Field glossary, distillation/KD, and schema pointers: `references/hyperparameters.md` (batch/multi-GPU → **this file**, not hyperparameters).

## Batch sizing — unsloth (single GPU)

Unsloth is single-GPU by design. The effective batch is the **product** of two fields, not a global/micro split:

```text
effective_batch = batch.per_device_train_batch_size × batch.gradient_accumulation_steps
```

There is no `parallelism` block, no TP / PP / DP, no GBS divisibility math. Multi-GPU sharding → switch to automodel.

**Field mapping from the automodel tables above:**

| Automodel field | Unsloth analogue | Notes |
|-----------------|------------------|-------|
| `micro_batch_size` | `batch.per_device_train_batch_size` | Drives peak VRAM. |
| `global_batch_size` | `batch.per_device_train_batch_size × batch.gradient_accumulation_steps` | Set `gradient_accumulation_steps` so the product matches the GBS you'd pick on automodel. |
| `parallelism.num_gpus_per_node` | n/a — single GPU | Use `hardware.gpus: "0"` to pin to one GPU. |
| `tensor_parallel_size` | n/a | If the model doesn't fit on one GPU → use automodel. |

**Starting points (LoRA, `max_seq_length` 2048, one ≥48 GB GPU):**

| Model params | `per_device_train_batch_size` | `gradient_accumulation_steps` | Effective batch | `learning_rate` |
|--------------|------------------------------:|------------------------------:|----------------:|----------------:|
| ≤4B | 8 | 16 | 128 | `1e-4` |
| 4B–8B | 4 | 24 | 96 | `8e-5` |
| 8B–14B | 2 | 32 | 64 | `8e-5` |
| >14B | 1 | 32 | 32 | `5e-5` |

`load_in_4bit: true` (default) keeps base weights in 4-bit, which is what makes the "smaller per-device batch on bigger models" rule milder than vanilla HF. If you raise `per_device_train_batch_size` and hit OOM (exit 137) or training crashes (exit 1), halve `per_device_train_batch_size` first and double `gradient_accumulation_steps` to keep the effective batch the same.

**Save method.** Default `output.save_method: "lora"` (adapter only — small, fast, deploy-friendly). Use `"merged_16bit"` if the user wants a full-weight checkpoint to deploy without an adapter loader; `"merged_4bit"` only when storage is tight (lossy). Merged methods require `training.finetuning_type: "lora"`.

**Tuning loop (unsloth):**

| Symptom | Action |
|---------|--------|
| CUDA OOM | Halve `per_device_train_batch_size` (keep effective batch via `gradient_accumulation_steps`); then lower `model.max_seq_length`; then drop `lora.rank` to 8 |
| `torch.cuda.is_available()` is False | Host CUDA / venv mismatch — see `references/troubleshooting.md` |
| `Backend 'unsloth' is not importable` | `$UNSLOTH_VENV` setup never ran or `--venv` was omitted (see Plugin pick) |
| Loss not moving | Raise `learning_rate` one step (e.g. `5e-5` → `1e-4`); confirm `apply_chat_template` matches the data shape; check the LoRA `target_modules` covers the right layers (defaults are Unsloth's 7-module set) |

## Worked example

**Automodel:** `Qwen/Qwen3-1.7B` + `tau/commonsense_qa` → CHAT JSONL, fileset `commonsense_qa`, entity `qwen3-1.7b`, output `qwen3-1.7b-commonsense-qa-lora`, `epochs: 1` (no `max_steps`). On ≥48 GB GPU use LoRA ≤4B **default**: `micro` 32, GBS 128, `learning_rate` `1e-4` (high-util: 64 / 256).

**Unsloth:** same model + dataset + entity + fileset, but `nemo customization unsloth run /tmp/job.json --venv "$UNSLOTH_VENV" -w default`. Job JSON ≤4B row: `batch.per_device_train_batch_size` 8, `batch.gradient_accumulation_steps` 16 (effective 128), `learning_rate` `1e-4`, `hardware.gpus` `"0"`, `output.save_method` `"lora"`. Reference fixture: `plugins/nemo-unsloth/tests/fixtures/minimal_unsloth_sft.json` (ignore `max_steps` for real runs).

## Report to user

**Automodel (submit):**

```markdown
## Fine-tune result

- **Job:** automodel-<id>
- **Model entity:** default/<model-entity>
- **Output adapter fileset:** <output.name>
- **Status:** <completed|error|cancelled>
- **Notes:** <error_details or phase if error>
```

**Unsloth (run):** the `run` command prints a result dict to stdout — pick fields from it.

```markdown
## Fine-tune result

- **Backend:** unsloth (local)
- **Model entity:** default/<model-entity>
- **Output model entity:** <result.output_model_entity.workspace>/<result.output_model_entity.name>
- **Output fileset:** <result.output_fileset.workspace>/<result.output_fileset.name>
- **Local checkpoint:** <result.output_path>
- **Final loss:** <result.loss>
- **Status:** completed (or `error: <exception>` if the command exited non-zero)
```

If the dict contains `upload_error` or `model_entity_error`, surface those — training succeeded but registration failed; the local `output_path` is still usable.

## Reference files

| When | Read |
|------|------|
| HF conversion or MCQA shaping | `references/hf-conversion.md` |
| CHAT vs SFT vs CUSTOM (automodel); text vs messages (unsloth) | `references/dataset-formats.md` |
| Field glossary, distillation/KD, schema (both backends) | `references/hyperparameters.md` (not batch sizing) |
| Batch sizing (≥48 GB), OOM / throughput | **Batch sizing — automodel** / **Batch sizing — unsloth** above |
| Multi-GPU same node | **Multi-GPU (same node)** under automodel batch sizing (unsloth is single-GPU) |
| Backend choice, execution profiles, `--venv` setup, submit/run failure, images, CLI | `references/troubleshooting.md` |
| Live JSON schema | `uv run nemo customization automodel explain` / `uv run nemo customization unsloth explain` |
| Job JSON fixture (automodel) | `plugins/nemo-automodel/tests/fixtures/qwen3_0.6b_sft_lora.json` (ignore `max_steps` for real runs) |
| Job JSON fixture (unsloth) | `plugins/nemo-unsloth/tests/fixtures/minimal_unsloth_sft.json` (ignore `max_steps` for real runs) |

Related: `plugins/nemo-automodel/README.md`, `plugins/nemo-unsloth/README.md`, `plugins/nemo-customizer/docs/CUSTOMIZATION.md`, skills **`nemo-files`**, **`nemo-status`**.
