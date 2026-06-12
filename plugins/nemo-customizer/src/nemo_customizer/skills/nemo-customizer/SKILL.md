---
name: nemo-customizer
description: >-
  Fine-tune models on NeMo Platform with `automodel` or `unsloth` (both `submit` →
  Docker GPU jobs via the platform Jobs service): HF dataset conversion, filesets,
  model entities, SFT/LoRA job JSON (hyperparameters, batch, schedule, optimizer),
  and job polling. Use for train, fine-tune, customize, SFT, LoRA, learning rate,
  epochs, or nemo customization.
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
  - unsloth submit
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

End-to-end **SFT + LoRA** on NeMo Platform. Two backend plugins ship in this repo — both are **`submit`-only** (local `run` is hard-disabled on each):

| Backend | Verb | Where it runs | Pick when |
|---------|------|---------------|-----------|
| **`automodel`** (default) | `submit` | Platform **Docker GPU executor** (Jobs service schedules containers on the platform host's daemon) | General SFT/LoRA; multi-GPU (data/tensor parallel); distillation; full-weight SFT |
| **`unsloth`** | `submit` | Same — Docker GPU job with 4 steps (download → train → upload → model-entity) | User asks for Unsloth, or wants Unsloth's 4-bit LoRA path / optimizer defaults on a single GPU |

`nemo-customizer` is the router (`nemo customization …`); training backends are separate plugins (`nemo-automodel`, `nemo-unsloth`). `submit` posts to the platform API; the platform runs training in container steps — **not** in the CLI shell. Heavy ML deps live in container images only.

Decision rule below in **Plugin pick**. Batch shell work; reuse resources with `--exist-ok`; skip CLI `--help` unless a command fails.

## Plugin pick

1. After `nemo auth login`, run `uv run nemo jobs list-execution-profiles -f json` (see `references/troubleshooting.md` for parsing).
2. If the user explicitly asked for Unsloth → **`unsloth`**.
3. Else if the user explicitly asked for Automodel → **`automodel`**.
4. Else if any profile has `provider: gpu` or `gpu_distributed` → **`automodel`** (default).
5. Else stop and tell the user GPU customization is unavailable (both backends need a GPU execution profile and `platform.runtime: docker` on the connected platform).

Training never runs inside the `nemo` CLI process. After `submit`, the platform's **local Docker executor** launches GPU container steps on the daemon attached to that platform host (often the same machine as `http://127.0.0.1:8080`, but always query the platform — not the agent's shell GPU or a separate `docker info` on another box).

## Gotchas

- Run all `uv run` commands from the **nemo-platform** git root (top-level `pyproject.toml`), not a plugin subfolder.
- Set `NEMO_BASE_URL` (or `NMP_BASE_URL`) only when the user gives a platform URL; default `http://127.0.0.1:8080` (same as `http://localhost:8080`). Track whether the user **overrode** the base URL — see **Platform unreachable** below.
- **Platform unreachable** — if any platform API call fails with a connection error (`Connection error`, timeout, refused):
  - **User gave a custom URL** (e.g. `10.0.0.51:8080`) or you exported a non-default `NEMO_BASE_URL` / `NMP_BASE_URL`: stop and tell the user the platform is not reachable at that address. Do **not** offer to start local services.
  - **Default URL only** (no user override): **ask** whether to start the platform locally. If they agree, from the **nemo-platform** git root run in the **background**:

    ```bash
    uv run nemo services run \
      --host 0.0.0.0 \
      --port 8080 \
      --controllers jobs,entities,models \
      --service-group all
    ```

    Poll until healthy (`curl -sf http://127.0.0.1:8080/health/ready` or retry `nemo jobs list-execution-profiles -f json`), then continue the workflow. Do not start services without asking.
- **Both backends are `submit` only** — `nemo customization <plugin> run …` hard-fails on automodel and unsloth with a pointer to `submit`. Do not improvise verbs or pass `--venv`.
- **Never set `max_steps` together with `epochs`** (both backends). `max_steps` is a global cap and stops mid-epoch. Test fixtures include `max_steps` for smoke tests — do not copy into production jobs. Unsloth's schema enforces this as a hard mutex; automodel allows both but the result is surprising.
- **Job done (both backends) = top-level `status`** in `completed` | `error` | `cancelled`. Steps can all be `completed` while the job is still `active` (upload, entity registration). `status_details.phase` may stay `training` with `progress_pct: 100` for a long time — keep polling. `poll_customization_job.sh` works for any job id (`automodel-…` or `unsloth-…`); it exits **1** on `error` or `cancelled`.
- Model spec fills async: **submit without polling** `nemo models get` unless submit fails.
- HF dataset id from the user → convert locally; do not ask for local paths first.
- Dataset fileset name = HF dataset **name** only (`tau/commonsense_qa` → `commonsense_qa`), not the model name.
- Prefer **CHAT** JSONL when the model has a chat template; details in `references/dataset-formats.md` (automodel auto-detects schema; unsloth needs `dataset.apply_chat_template: true` to consume `messages`).
- User asks to tune **batch or parallelism** (automodel) → **Batch sizing** / **Multi-GPU** below. Other fields (LR, epochs, LoRA rank, distillation) → `references/hyperparameters.md`. For unsloth, see **Batch sizing — unsloth** and the `Unsloth job JSON` section in `references/hyperparameters.md`. Run `nemo customization <plugin> explain` for the live schema.
- Skill **defaults** (`micro_batch_size` 1, `global_batch_size` 4) are safe on unknown VRAM. When the user has **≥48 GB** on one GPU, use **Batch sizing** instead of defaults. Unsloth's analogues are `batch.per_device_train_batch_size` and `batch.gradient_accumulation_steps` (effective batch = product).
- **Unsloth training is single-GPU per job** (inside the container). `hardware.gpus` sets `CUDA_VISIBLE_DEVICES` before `import torch` — **selection, not reservation**. No `parallelism`/TP/PP block in job JSON. Multi-GPU sharding → use automodel. Pass `--profile <name>` on `unsloth submit` when the default `gpu` profile is wrong (automodel sets `training.execution_profile` in JSON instead).
- **Unsloth validation defaults** — when `dataset.validation_path` is set and `schedule.eval_steps` is omitted, the trainer runs validation once per effective epoch automatically. Report final `metrics.val_loss` from job status (see **Report to user**). Set `eval_steps` explicitly to override cadence.
- **Do not use local `docker info`** to pick automodel vs unsloth. After auth, run `uv run nemo jobs list-execution-profiles -f json` against the user's platform (see `references/troubleshooting.md`). Default output is a table — **`-f json` is required** for scripting; parse **stdout only** (do not pipe `2>&1` into `json.load`).
- **Do not merge stderr into stdout when parsing JSON** — `submit`, `explain`, and `-f json` commands write **JSON on stdout**; harmless warnings like `Configuration file not found, using defaults` go to **stderr**. Piping with **`2>&1`** before `json.load` raises `JSONDecodeError` even when submit **succeeded** — a common cause of **duplicate jobs** when the agent re-submits after a parse error. Parse stdout only; redirect stderr if needed (`2>/dev/null`). See `references/troubleshooting.md` § **Parsing CLI JSON**.
- For submit/image/plugin errors (both backends), read `references/troubleshooting.md`. Unsloth needs the `nmp-unsloth-training` container image on the **platform host's** Docker daemon (see `docker/unsloth/README.md`).
- **Missing training image on a remote platform** — if the user gave a non-localhost `NEMO_BASE_URL` / `NMP_BASE_URL` (e.g. `10.0.0.51:8080`) and the job errors with `Failed to pull image`, `manifest unknown`, or missing `nmp-unsloth-training` / automodel training image: **do not** run `docker build`, `docker pull`, or `docker buildx bake` on the agent machine. Report with **Report to user** (use **Output adapter fileset (planned):** on error), then append on-target build steps from `references/troubleshooting.md` § **Missing training images**.

## Workflow

Common steps then **branch by plugin pick**:

```text
- [ ] export NEMO_BASE_URL (if user provided endpoint); note whether base URL is user-overridden
- [ ] cd nemo-platform && uv run nemo auth login --unsigned-token --email <user email or admin@example.com>
- [ ] uv run nemo jobs list-execution-profiles -f json — apply Plugin pick rules above
- [ ] On connection error: default URL → ask to start platform (see Platform unreachable); custom URL → report unreachable and stop
- [ ] Convert HF dataset → /tmp/train-data/*.jsonl (see references/hf-conversion.md)
- [ ] Create dataset fileset (--exist-ok), upload train.jsonl (+ validation.jsonl), nemo files list to verify
- [ ] Create HF weights fileset + model entity if missing (--exist-ok)

# automodel branch (submit → Docker GPU job)
- [ ] Write /tmp/job.json (batch sizing for ≥48 GB GPU; else Defaults table)
- [ ] uv run nemo customization automodel submit /tmp/job.json --workspace default
- [ ] Poll until top-level terminal (`poll_customization_job.sh`; default 15s interval, or 30–60s manual polls)
- [ ] Report using output template below

# unsloth branch (submit → Docker GPU job)
- [ ] Write /tmp/job.json using the UnslothJobInput shape (see Fast path — unsloth)
- [ ] uv run nemo customization unsloth submit /tmp/job.json --workspace default [--profile <gpu-profile>]
- [ ] Poll until top-level terminal (`poll_customization_job.sh unsloth-<job-id>`; default 15s interval)
- [ ] Report using output template below
```

## Fast path — automodel

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
bash plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/scripts/poll_customization_job.sh automodel-<job-id>
```

Read `<job-id>` from the `"name"` field in submit stdout (JSON). **Do not use `2>&1`** before `json.load` — warnings on stderr break parsing; see Gotchas. Optional interval override: append seconds (e.g. `… 30`). Or poll manually: `uv run nemo jobs get-status automodel-<job-id>` every 30–60s.

## Fast path — unsloth

Same substitutions as automodel. Steps 1 (dataset) and 2 (model entity) are identical — the differences are the job JSON shape (`UnslothJobInput`) and the `unsloth submit` command.

**1. Dataset** — same as automodel Fast path step 1.

**2. Model** — same as automodel Fast path step 2.

**3. Job JSON** — write `/tmp/job.json` using the **`UnslothJobInput`** shape (see `references/hyperparameters.md` → *Unsloth job JSON*). `model` is an **object** (not a string), `dataset.path` is a single fileset ref, `hardware.gpus` replaces the `parallelism` block (single GPU in the training container). `nemo customization unsloth explain` prints the live schema.

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

**4. Submit and poll**

```bash
uv run nemo customization unsloth submit /tmp/job.json --workspace default
bash plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/scripts/poll_customization_job.sh unsloth-<job-id>
```

Read `<job-id>` from the `"name"` field in submit stdout (JSON). **Do not use `2>&1`** before `json.load` — warnings on stderr break parsing; see Gotchas. Optional interval override: append seconds (e.g. `… 30`). Or poll manually: `uv run nemo jobs get-status unsloth-<job-id>` every 30–60s. If submit fails on an unknown profile, re-list execution profiles and pass `--profile <name>` on submit (default is `gpu`).

If you try `nemo customization unsloth run …`, the CLI hard-fails with a pointer to `submit`.

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
| Missing `nmp-unsloth-training` image | Build/pull the Unsloth container image — see `references/troubleshooting.md` and `docker/unsloth/README.md` |
| `Unsloth training requires platform.runtime: docker` | Platform not using the Docker executor | Start platform with `platform.runtime: docker` and a GPU execution profile; training runs in containers on that host's Docker daemon |
| Loss not moving | Raise `learning_rate` one step (e.g. `5e-5` → `1e-4`); confirm `apply_chat_template` matches the data shape; check the LoRA `target_modules` covers the right layers (defaults are Unsloth's 7-module set) |

## Worked example

**Automodel:** `Qwen/Qwen3-1.7B` + `tau/commonsense_qa` → CHAT JSONL, fileset `commonsense_qa`, entity `qwen3-1.7b`, output `qwen3-1.7b-commonsense-qa-lora`, `epochs: 1` (no `max_steps`). On ≥48 GB GPU use LoRA ≤4B **default**: `micro` 32, GBS 128, `learning_rate` `1e-4` (high-util: 64 / 256).

**Unsloth:** same model + dataset + entity + fileset, but `nemo customization unsloth submit /tmp/job.json -w default`. Job JSON ≤4B row: `batch.per_device_train_batch_size` 8, `batch.gradient_accumulation_steps` 16 (effective 128), `learning_rate` `1e-4`, `hardware.gpus` `"0"`, `output.save_method` `"lora"`. Poll `unsloth-<job-id>` to completion. Reference fixture: `plugins/nemo-unsloth/tests/fixtures/minimal_unsloth_sft.json` (ignore `max_steps` for real runs).

## Report to user

After polling reaches a **terminal** status (`completed`, `error`, or `cancelled`), report using this template for **both** backends. Fill fields from the job JSON and `nemo jobs get-status`.

```markdown
## Fine-tune result

- **Job:** <automodel-|unsloth-><id>
- **Backend:** <automodel|unsloth>
- **Model entity:** default/<model-entity>
- **Dataset fileset:** default/<dataset-fileset>
- **Output adapter fileset:** <output.name from job JSON>
- **Status:** <completed|error|cancelled>
- **Final train loss:** <last value in metrics.train_loss, or "n/a">
- **Final validation loss:** <last value in metrics.val_loss, or "n/a (no validation run)">
- **Notes:** <see below>
```

**Field guidance**

| Field | Source |
|-------|--------|
| **Job** | Job id from submit or poll (`automodel-…` / `unsloth-…`) |
| **Backend** | Plugin used for submit |
| **Model entity** | `model` in job JSON (automodel: string ref; unsloth: `model.name`) |
| **Dataset fileset** | automodel: `dataset.training`; unsloth: `dataset.path` |
| **Output adapter fileset** | `output.name` from job JSON. Label **Output adapter fileset (planned):** when status is `error` or `cancelled` and no output was registered |
| **Status** | Top-level `status` from `nemo jobs get-status` — not step-level status |
| **Final train loss** | Last entry in `status_details.metrics.train_loss` (or nested under a step's `status_details.metrics`). Use the **last** `value` in the list — not `status_details.train_loss` alone (that is the most recent logged step, which may differ from epoch-average loss on some backends). Round to 3 decimal places. |
| **Final validation loss** | Last entry in `status_details.metrics.val_loss`. If the list is empty, report `n/a (no validation run)` and note whether validation data was configured. Automodel validates once per epoch by default. Unsloth validates once per epoch when `dataset.validation_path` is set and `schedule.eval_steps` is omitted (platform default: `max(1, effective_steps - 1)`). |
| **Notes** | See **Notes by status** below |

**Metrics extraction** — after polling, always run `uv run nemo jobs get-status <job-id>` and read `status_details.metrics` (both backends accumulate `train_loss` and `val_loss` time series there). Include both final losses in the report even when status is `error` if training completed before the failure (e.g. entity registration failed after upload).

**Notes by status**

| Status | Notes |
|--------|-------|
| `completed` | Brief success summary (e.g. adapter registered on model entity). When `metrics.train_loss` has ≥2 entries, add a loss-drop sentence: *Loss dropped from \<first value, 1 dp\> at step 1 to \<last value, 3 dp\> at step \<N\>; validation loss was \<val or n/a\>.* |
| `error` | Quote `error_details.message` or the failing step; note setup that succeeded before the failure (auth, dataset upload, submit). |
| `cancelled` | Cancellation reason if available. |

**Training configuration (always)** — append a `### Training configuration` table after the header block (before **Using the adapter** when `completed`). Fill rows from the submitted job JSON; omit rows whose fields were not set. Use backend-specific labels:

| Setting | automodel source | unsloth source |
|---------|------------------|----------------|
| Training type | `training.training_type` | `training.training_type` |
| Finetuning type | `training.finetuning_type` | `training.finetuning_type` |
| LoRA rank / alpha | `training.lora.rank` / `training.lora.alpha` | same |
| Quantization | omit (full-precision / bf16 base weights) | `model.load_in_4bit` → `4-bit (load_in_4bit: true)` or omit when false |
| Max sequence length | `training.max_seq_length` | `model.max_seq_length` |
| Epochs | `schedule.epochs` | `schedule.epochs` |
| Batch | `micro_batch_size` / `global_batch_size` | `batch.per_device_train_batch_size` / `batch.gradient_accumulation_steps` |
| Effective batch size | `global_batch_size` | `per_device_train_batch_size × gradient_accumulation_steps` |
| Learning rate | `optimizer.learning_rate` | same |
| Optimizer | `optimizer` fields used (e.g. `weight_decay`, `warmup_steps`) | `optimizer.optim` (e.g. `adamw_8bit`) |
| Precision | `bf16` (default) | `hardware.precision` |
| GPU | `parallelism.num_gpus_per_node` (and `tensor_parallel_size` when >1) | `hardware.gpus` |
| Output save method | `output.type` (e.g. `adapter`) | `output.save_method` (e.g. `lora`) |

**Automodel example:**

```markdown
### Training configuration

| Setting | Value |
|---------|-------|
| Training type | SFT |
| Finetuning type | LoRA |
| LoRA rank / alpha | 16 / 32 |
| Max sequence length | 2048 |
| Epochs | 1 |
| Micro batch size | 16 |
| Global batch size | 64 |
| Effective batch size | 64 |
| Learning rate | 1e-4 |
| Optimizer | weight_decay 0.01, warmup_steps 0 |
| Precision | bf16 |
| GPU | 1 (TP=1) |
| Output save method | adapter |
```

**Unsloth example:**

```markdown
### Training configuration

| Setting | Value |
|---------|-------|
| Training type | SFT |
| Finetuning type | LoRA |
| LoRA rank / alpha | 16 / 32 |
| Quantization | 4-bit (`load_in_4bit: true`) |
| Max sequence length | 2048 |
| Epochs | 1 |
| Per-device batch size | 8 |
| Gradient accumulation steps | 16 |
| Effective batch size | 128 |
| Learning rate | 1e-4 |
| Optimizer | adamw_8bit |
| Precision | bf16 |
| GPU | 0 |
| Output save method | lora |
```

**Using the adapter (`completed` only)** — after **Training configuration**, run `uv run nemo models get <model-entity> --workspace default` (parse stdout only) to confirm the adapter is listed under `adapters`. Append this section:

```markdown
### Using the adapter

The adapter `<output.name>` is attached to `default/<model-entity>`. List adapters with:

\`\`\`bash
export NEMO_BASE_URL=<platform-url>   # omit line when using default localhost
cd /path/to/nemo-platform
uv run nemo models get <model-entity> --workspace default
\`\`\`
```

Use the user's platform URL in `NEMO_BASE_URL` when they overrode it; omit the export line for default `http://127.0.0.1:8080`. The JSON `adapters` array shows `name`, `fileset`, `finetuning_type`, and `lora_config` for each registered adapter.

**Save report to `/tmp`** — unless the user opts out, write the full Markdown report (header, **Training configuration**, **Using the adapter** when `completed`, and **Resources created** when a slug or new filesets were used) to `/tmp/fine-tune-result-<slug-or-job-suffix>.md`. Use the random slug from the run when one was assigned; otherwise use the job id suffix (e.g. `a925b07ff678`).

**Error follow-ups** — when the failure has a known fix, append sections **below** the header block (do not replace the header). Examples:

| Error type | Append |
|------------|--------|
| Missing training image + user-overridden `NEMO_BASE_URL` / `NMP_BASE_URL` | `references/troubleshooting.md` § **Missing training images** — on-target build steps, env vars, re-submit commands. **Do not** `docker build` locally for a remote platform. |

For other terminal errors, keep the same header template; put remediation detail in **Notes** or a short **Next steps** section as appropriate.

## Reference files

| When | Read |
|------|------|
| HF conversion or MCQA shaping | `references/hf-conversion.md` |
| CHAT vs SFT vs CUSTOM (automodel); text vs messages (unsloth) | `references/dataset-formats.md` |
| Field glossary, distillation/KD, schema (both backends) | `references/hyperparameters.md` (not batch sizing) |
| Batch sizing (≥48 GB), OOM / throughput | **Batch sizing — automodel** / **Batch sizing — unsloth** above |
| Multi-GPU same node | **Multi-GPU (same node)** under automodel batch sizing (unsloth is single-GPU) |
| Backend choice, execution profiles, submit failure, container images, missing image on remote platform, CLI, connection errors | `references/troubleshooting.md` (§ **Parsing CLI JSON** for `2>&1` / `json.load`) |
| Live JSON schema | `uv run nemo customization automodel explain` / `uv run nemo customization unsloth explain` |
| Job JSON fixture (automodel) | `plugins/nemo-automodel/tests/fixtures/qwen3_0.6b_sft_lora.json` (ignore `max_steps` for real runs) |
| Job JSON fixture (unsloth) | `plugins/nemo-unsloth/tests/fixtures/minimal_unsloth_sft.json` (ignore `max_steps` for real runs) |

Related: `plugins/nemo-automodel/README.md`, `plugins/nemo-unsloth/README.md`, `plugins/nemo-customizer/docs/CUSTOMIZATION.md`, skills **`nemo-files`**, **`nemo-status`**.
