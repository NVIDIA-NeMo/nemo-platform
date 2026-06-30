# Hyperparameters

Two backend job schemas live in this skill. Pick by plugin:

| Plugin | Schema class | Schema dump | Section below |
|--------|--------------|-------------|---------------|
| `automodel` | `AutomodelJobInput` (`plugins/nemo-automodel/src/nemo_automodel_plugin/schema.py`) | `nemo customization automodel explain` | **Automodel job JSON** (below) |
| `unsloth` | `UnslothJobInput` (`plugins/nemo-unsloth/src/nemo_unsloth_plugin/schema.py`) | `nemo customization unsloth explain` | **Unsloth job JSON** (further down) |

Both schemas use `extra="forbid"` — unknown keys raise validation errors. Field names are **not** interchangeable across backends (e.g. automodel uses `micro_batch_size` / `global_batch_size` / `parallelism`; unsloth uses `per_device_train_batch_size` / `gradient_accumulation_steps` / `hardware`). Use the right schema for the chosen plugin.

**Batch sizing, 48 GB VRAM tables, multi-GPU (data parallel vs tensor parallel), and throughput tuning** live in **`SKILL.md`** (§ Batch sizing — automodel, § Batch sizing — unsloth, § Multi-GPU). This file is the **field glossary**, full JSON template per backend, distillation/KD, and schema pointers — not the place to pick batch sizes for production runs.

---

## Integrations (automodel + unsloth)

Both backends accept the same `integrations` object on job JSON (`IntegrationsSpec` in `nemo_platform_plugin.integrations`). A non-null backend block **requests** that integration; the training runtime **activates** it only when credentials/URIs are available (W&B needs `WANDB_API_KEY`, MLflow needs a tracking URI). Omit the field or set a backend to `null` to disable. There is no `enabled` flag and no `report_to` on input — `report_to` is derived at runtime from activated backends. The compiler logs a warning when W&B is requested without `api_key_secret` or MLflow without `tracking_uri`.

```json
"integrations": {
  "wandb": {
    "project": "my-project",
    "name": "run-001",
    "entity": "my-team",
    "tags": ["sft", "llama"],
    "notes": "Experiment notes",
    "base_url": "https://wandb.internal",
    "api_key_secret": "default/wandb-api-key"
  },
  "mlflow": {
    "experiment_name": "llama-finetuning",
    "name": "run-001",
    "tracking_uri": "http://mlflow:5000",
    "tags": { "team": "nlp" },
    "description": "SFT experiment"
  }
}
```

| Field | Notes |
|-------|-------|
| `wandb` | Non-null requests W&B (requires `WANDB_API_KEY` at runtime). |
| `wandb.project` | W&B project; defaults to `output.name` at runtime if unset. |
| `wandb.name` | W&B run name; defaults to job ID. Legacy `run_name` is accepted with a deprecation warning. |
| `wandb.entity` | W&B team or username. |
| `wandb.tags` / `wandb.notes` | Optional run metadata. |
| `wandb.base_url` | Self-hosted W&B server URL. Without `api_key_secret`, W&B may still activate when `base_url` is set **and** the server allows access without a cloud API key — a compile-time warning is logged. |
| `wandb.api_key_secret` | Platform secret ref (`secret_name` or `workspace/secret_name`). The compiler injects `WANDB_API_KEY` into the training step environment. |
| `mlflow` | Non-null requests MLflow (requires tracking URI at runtime). |
| `mlflow.tracking_uri` | MLflow tracking server; can also come from `MLFLOW_TRACKING_URI` in the container. |
| `mlflow.experiment_name` | Defaults to `output.name` if unset. |
| `mlflow.name` | MLflow run name; defaults to job ID. Legacy `run_name` is accepted with a deprecation warning. |
| `mlflow.tags` / `mlflow.description` | Optional run metadata. |

Set `"integrations": null` or omit the field when tracking is not needed. Contract examples: `plugins/nemo-automodel/tests/fixtures/integrations_wandb_mlflow.json`, `plugins/nemo-unsloth/tests/fixtures/integrations_wandb_mlflow.json`.

**Local setup (MLflow server, `docker0` tracking URI, jobs-launcher, W&B secret):** `references/integrations-setup.md`.

**Unsloth note:** HuggingFace `TrainingArguments.run_name` is shared by W&B and MLflow. When both backends are active, `wandb.name` wins if set; otherwise `mlflow.name` is used. If both names are set to different values, a runtime warning is logged and W&B's name is used.

---

# Automodel job JSON

Job JSON for `nemo customization automodel submit` uses **`AutomodelJobInput`** (`plugins/nemo-automodel/src/nemo_automodel_plugin/schema.py`). Only fields in that schema are accepted (`extra="forbid"`).

**Schema dump:**

```bash
nemo customization automodel explain
```

**Contract examples:** `services/automodel/tests/contract/input_configs/` (legacy shape; map `batch_size` → `global_batch_size` in submit JSON).

## Job JSON layout

| Section | Purpose |
|---------|---------|
| `model` | **Base model entity** ref (`default/<model-entity>`) — weights to fine-tune |
| `dataset` | **Dataset filesets** (`default/<dataset-fileset>`); optional `prompt_template` for CUSTOM schema |
| `training` | Method, LoRA, `max_seq_length`, distillation/KD fields |
| `schedule` | Epochs, optional step cap, validation cadence, seed |
| `batch` | Global/micro batch, sequence packing |
| `optimizer` | LR, weight decay, warmup |
| `parallelism` | Nodes, GPUs, TP/PP/CP/EP |
| `output` | Output adapter/model fileset name |
| `integrations` | Optional W&B / MLflow |

### `model` field (base model entity)

`model` must name a **Models API entity** for the checkpoint being trained — not a dataset fileset, not an output adapter from a prior job, and not a raw Hugging Face repo id.

| Valid | Invalid |
|-------|---------|
| `default/qwen3-1.7b` (entity from `nemo models create`) | `Qwen/Qwen3-1.7B` (HF id) |
| `default/llama-3.2-1b-instruct` | `default/commonsense_qa` (dataset fileset) |
| `other-ws/my-model` (qualified ref) | `qwen3-1.7b-commonsense-qa-lora` (output fileset only, unless registered as entity) |

Register before submit (same as skill fast path): HF **model** fileset → `nemo models create <model-entity> …` with `"fileset":"default/<weights-fileset>"`. List: `nemo models list --workspace default`.

Full template:

```json
{
  "model": "default/<model-entity>",
  "dataset": {
    "training": "default/<dataset-fileset>",
    "validation": "default/<dataset-fileset>",
    "prompt_template": null
  },
  "training": {
    "training_type": "sft",
    "finetuning_type": "lora",
    "lora": {
      "rank": 16,
      "alpha": 32,
      "dropout": 0.0,
      "merge": false,
      "target_modules": null,
      "exclude_modules": null,
      "use_triton": true
    },
    "max_seq_length": 2048,
    "precision": null,
    "attn_implementation": "sdpa",
    "execution_profile": null
  },
  "schedule": {
    "epochs": 1,
    "max_steps": null,
    "val_check_interval": null,
    "seed": null
  },
  "batch": {
    "global_batch_size": 4,
    "micro_batch_size": 1,
    "sequence_packing": false,
    "sequence_packing_max_samples": 1000
  },
  "optimizer": {
    "learning_rate": 5e-5,
    "min_learning_rate": null,
    "weight_decay": 0.01,
    "adam_beta1": 0.9,
    "adam_beta2": 0.999,
    "adam_eps": 1e-8,
    "optimizer": "Adam",
    "lr_decay_style": "cosine",
    "warmup_steps": 0
  },
  "parallelism": {
    "num_nodes": 1,
    "num_gpus_per_node": 1,
    "tensor_parallel_size": 1,
    "pipeline_parallel_size": 1,
    "context_parallel_size": 1,
    "expert_parallel_size": null,
    "sequence_parallel": false
  },
  "output": { "name": "<output-name>", "description": null },
  "integrations": null
}
```

---

## Field reference

### Automodel `training`

| Field | Default | Notes |
|-------|---------|-------|
| `training_type` | `sft` | `distillation` requires `teacher_model` (entity ref) |
| `finetuning_type` | `lora` | `all_weights` (full fine-tune), `lora_merged` (merge adapter into base) |
| `lora.rank` | `16` | Higher → more capacity, more VRAM. Typical training range 8–32; **cap at 32** if the adapter will be served with default NIM / vLLM (rank > 32 may not load) |
| `lora.alpha` | `32` | Scaling; common rule of thumb **alpha ≈ 2× rank** |
| `lora.dropout` | `0.0` | LoRA dropout (0.0–1.0) for regularization |
| `lora.merge` | `false` | If true with `lora_merged`, output is full weights not adapter |
| `lora.target_modules` | `null` | e.g. `["q_proj","v_proj"]`; null = platform default targets |
| `lora.exclude_modules` | `null` | Patterns to exclude from LoRA, e.g. `["*.out_proj"]` |
| `lora.use_triton` | `true` | Use the optimized Triton LoRA kernel |
| `max_seq_length` | `2048` | Truncate/pack to this length; lower if OOM |
| `precision` | `null` | `bf16` \| `fp16` \| `fp32` \| `fp8`; null auto-detects from the checkpoint |
| `attn_implementation` | `sdpa` | `sdpa` (PyTorch native) \| `flash_attention_2` \| `eager` |
| `teacher_model` | — | **Model entity ref** (not HF id). Required for distillation; see below |
| `distillation_ratio` | `0.5` | KD blend (0–1) |
| `distillation_temperature` | `1.0` | KD temperature |
| `teacher_precision` | `bf16` | `bf16` \| `fp16` \| `fp32` |
| `offload_teacher` | `false` | Offload teacher weights to CPU |

LoRA block is auto-created when `finetuning_type` is `lora` or `lora_merged`.

### Automodel `schedule`

| Field | Default | Notes |
|-------|---------|-------|
| `epochs` | `1` | Must be **≥ 1**. Full passes over training set |
| `max_steps` | `null` | **Global step cap.** Omit for epoch-based runs |
| `val_check_interval` | `null` | `≤ 1.0` = fraction of epoch; `> 1` = every N steps |
| `seed` | `null` | Reproducibility |

**Gotcha:** Do **not** set `max_steps` with `epochs` for normal training. `max_steps` stops early (e.g. `epochs: 1` + `max_steps: 100` ends at step 100). Use `max_steps` **alone** only for smoke tests.

### Automodel `batch`

| Field | Default | Notes |
|-------|---------|-------|
| `global_batch_size` | `8` (schema) | Effective batch across all GPUs; **≥48 GB LoRA tables → `SKILL.md`** |
| `micro_batch_size` | `1` (schema) | **Per GPU**; same SKILL tables for single- and multi-GPU (TP=1) |
| `sequence_packing` | `false` | Pack short sequences for throughput (needs compatible data) |
| `sequence_packing_max_samples` | `1000` | Samples analyzed to estimate the optimal pack size (only when packing) |

**Validation:** `global_batch_size` must be divisible by `micro_batch_size × data_parallel_size`, where:

`data_parallel_size = (num_nodes × num_gpus_per_node) / (tensor_parallel_size × pipeline_parallel_size × context_parallel_size)`

Example: 1 node, 2 GPUs, TP=1 → DP=2 → GBS must be a multiple of `2 × micro_batch_size`. See **`SKILL.md` § Multi-GPU** for data parallel vs tensor parallel.

### Automodel `optimizer`

| Field | Default | Notes |
|-------|---------|-------|
| `learning_rate` | `5e-6` (schema) | Skill uses **5e-5** for small LoRA SFT; see tuning below |
| `min_learning_rate` | `null` | Floor for the cosine LR decay; null lets it decay toward 0 |
| `weight_decay` | `0.01` | L2-style regularization |
| `adam_beta1` | `0.9` | Adam optimizer beta1 |
| `adam_beta2` | `0.999` | Adam optimizer beta2 |
| `adam_eps` | `1e-8` | Adam/AdamW epsilon for numerical stability |
| `optimizer` | `Adam` | `Adam` \| `AdamW` |
| `lr_decay_style` | `cosine` | `cosine` \| `linear` \| `constant` |
| `warmup_steps` | `0` | Linear warmup; try ~10% of total steps for long runs |

### `parallelism`

| Field | Default | Notes |
|-------|---------|-------|
| `num_nodes` | `1` | Multi-node distributed jobs |
| `num_gpus_per_node` | `1` | GPUs per node |
| `tensor_parallel_size` | `1` | **> 1** when the model does not fit on one ≥48 GB GPU — see **`SKILL.md` § Multi-GPU** |
| `pipeline_parallel_size` | `1` | Pipeline stages |
| `context_parallel_size` | `1` | Long-context sharding |
| `expert_parallel_size` | `null` | MoE only; must divide `data_parallel_size × context_parallel_size` |
| `sequence_parallel` | `false` | Shard activations along the sequence dim (pairs with tensor parallelism) |

**MoE:** If `expert_parallel_size > 1` and multiple GPUs, `tensor_parallel_size` must be **1**.

### Automodel `integrations` (optional)

See **Integrations (automodel + unsloth)** above.

---

## Tuning guide (when the user asks)

Apply user overrides to `/tmp/job.json` before submit. For **batch / GPU count / parallelism**, follow **`SKILL.md`** (defaults table + § Batch sizing + § Multi-GPU). Below covers **non-batch** fields and defers VRAM/batch symptoms to the skill.

| Symptom / goal | Try first |
|----------------|-----------|
| CUDA OOM | **`SKILL.md` tuning loop:** halve `micro_batch_size`, then `global_batch_size`, then `max_seq_length`; use TP > 1 only if the model does not fit one ≥48 GB GPU |
| Slow / low GPU use | **`SKILL.md`:** step toward high-util column or double `micro`+GBS until ~35–40 GiB; multi-GPU data parallel if model fits one GPU |
| Underfitting | More `epochs`, slightly higher `learning_rate`, higher LoRA `rank` (≤ 32 for NIM/vLLM deploy) |
| Overfitting | Fewer `epochs`, lower `learning_rate`, higher `weight_decay`, smaller `rank` |
| Quick smoke test | `max_steps` only (e.g. 10–50), **omit or ignore epoch goal**; or `epochs: 1` on tiny slice |
| Reproducibility | Set `schedule.seed` |

### Automodel learning rate (LoRA SFT, starting points)

| Model scale | Suggested `learning_rate` |
|-------------|---------------------------|
| ≤ 3B | `5e-5` – `1e-4` |
| 3B – 8B | `2e-5` – `5e-5` |
| > 8B | `1e-5` – `2e-5` |

Schema default is `5e-6` (conservative). Fixtures: `qwen3_0.6b_sft_lora.json` uses `5e-5`; `minimal_sft_lora.json` uses `5e-6`.

### Automodel LoRA rank / alpha

**Deployment cap:** Default **NIM** and **vLLM** LoRA serving paths support rank **≤ 32**. Use `rank` 32 (not higher) when the fine-tuned adapter will be deployed for inference on those stacks unless the user confirms a higher rank is supported.

| Use case | `rank` | `alpha` |
|----------|--------|---------|
| Default / balanced | 16 | 32 |
| Low VRAM / light touch | 8 | 16 |
| More capacity (inference-safe max) | 32 | 64 |

### Epochs vs dataset size

One epoch = one full pass over `train.jsonl`. Steps per epoch ≈ `train_samples / global_batch_size` (e.g. ~10k samples, GBS 64 → ~153 steps). Plan poll time from the **GBS you chose in `SKILL.md`**, not the unknown-VRAM default (GBS 4).

---

## Presets (non-batch fields)

Use **`SKILL.md` § Batch sizing** and **§ Multi-GPU** for `batch` and `parallelism` on ≥48 GB GPUs. Presets below only override schedule / training / optimizer.

**Smoke test (step-capped)**

```json
"schedule": { "epochs": 1, "max_steps": 50 }
```

**Higher-quality LoRA (more VRAM/time)**

```json
"training": { "lora": { "rank": 32, "alpha": 64 }, "max_seq_length": 2048 },
"schedule": { "epochs": 3 },
"optimizer": { "learning_rate": 2e-5, "warmup_steps": 100 }
```

Pair with batch rows from **`SKILL.md`** (e.g. ≤4B default `micro` 32 / GBS 128, not `micro` 1 / GBS 4).

---

## Distillation (`training_type: "distillation"`)

Use only when the user requests KD/distillation. **`model`** is the **student** entity; **`teacher_model`** is a separate **teacher** entity in the same workspace (unless qualified as `other-ws/name`).

### Teacher model entity

`teacher_model` must be a registered **model entity ref**, same shape as `model`:

| Form | Example |
|------|---------|
| Same workspace | `default/llama-3.2-3b-instruct` |
| Explicit workspace | `default/<teacher-entity>` |

It is **not** a Hugging Face repo id. Register the teacher like the student before submit:

```bash
TEACHER_WEIGHTS=llama-3.2-3b-instruct   # fileset name
TEACHER_ENTITY=llama-3.2-3b-instruct    # entity name
TEACHER_HF=meta-llama/Llama-3.2-3B-Instruct

nemo files filesets create "$TEACHER_WEIGHTS" --workspace default --purpose model --exist-ok \
  --storage '{"type":"huggingface","repo_id":"'"$TEACHER_HF"'","repo_type":"model","revision":"main"}'

nemo models create "$TEACHER_ENTITY" --workspace default --exist-ok \
  --input-data '{"name":"'"$TEACHER_ENTITY"'","fileset":"default/'"$TEACHER_WEIGHTS"'","custom_fields":{"hf_model_id":"'"$TEACHER_HF"'"}}'
```

Verify: `nemo models get <teacher-entity> --workspace default`. Reuse an existing entity with `nemo models list` when present.

**Compatibility:** Student and teacher must share the **same vocabulary / tokenizer family** (compiler loads both for KD). Mismatched tokenizers fail at runtime. Prefer a larger instruct model as teacher and a smaller base/chat model as student in the same family when possible.

**VRAM:** Set `offload_teacher: true` if the job OOMs loading student + teacher; `teacher_precision: "bf16"` is the default.

### Job JSON

```json
{
  "model": "default/<student-entity>",
  "dataset": { "training": "default/<dataset-fileset>" },
  "training": {
    "training_type": "distillation",
    "finetuning_type": "lora",
    "teacher_model": "default/<teacher-entity>",
    "distillation_ratio": 0.5,
    "distillation_temperature": 1.0,
    "teacher_precision": "bf16",
    "offload_teacher": false,
    "max_seq_length": 2048
  },
  "schedule": { "epochs": 1 },
  "batch": { "global_batch_size": 64, "micro_batch_size": 16 },
  "optimizer": { "learning_rate": 8e-5 },
  "parallelism": { "num_nodes": 1, "num_gpus_per_node": 1, "tensor_parallel_size": 1 },
  "output": { "name": "<output-name>" }
}
```

(`batch` / `parallelism` example uses an 8B-scale row from **`SKILL.md`**; adjust for student size.)

| Field | Meaning |
|-------|---------|
| `distillation_ratio` | Blend of KD vs CE loss (`0` = CE only, `1` = KD only) |
| `distillation_temperature` | Softmax temperature for teacher logits |
| `offload_teacher` | CPU-offload frozen teacher weights to save GPU memory |

---

# Unsloth job JSON

Job JSON for `nemo customization unsloth submit` uses **`UnslothJobInput`** (`plugins/nemo-unsloth/src/nemo_unsloth_plugin/schema.py`). Only fields in that schema are accepted (`extra="forbid"`). The canonical post-transform shape lives in `services/unsloth/src/nmp/unsloth/schemas.py` (`UnslothJobOutput`) and is what the training driver consumes in the GPU container.

**Schema dump:**

```bash
nemo customization unsloth explain
```

Unsloth is **submit-only, single-GPU inside the training container**. There is no `parallelism` block and no `training.execution_profile` in job JSON — pass `--profile` on `nemo customization unsloth submit` instead (default `gpu`). `hardware.gpus` sets `CUDA_VISIBLE_DEVICES` in the container before `import torch`. Multi-GPU sharding → use automodel.

## Job JSON layout (unsloth)

| Section | Purpose |
|---------|---------|
| `name` | Optional job name (auto-generated if omitted) |
| `model` | **Object** — base model entity ref + how to load it (4-bit, dtype, max_seq_length) |
| `dataset` | Single fileset ref (`path`) + optional `validation_path`; row shape selector (`text_field`, `apply_chat_template`, `packing`) |
| `training` | Method (`sft`), adapter shape (`lora`/`full`), LoRA hyperparams, gradient checkpointing |
| `schedule` | `epochs` xor `max_steps`; `warmup_steps` xor `warmup_ratio`; logging / save / eval cadence; LR scheduler |
| `batch` | `per_device_train_batch_size` × `gradient_accumulation_steps` = effective batch |
| `optimizer` | LR, weight decay, optimizer choice (`adamw_8bit` default) |
| `hardware` | GPU selection (`CUDA_VISIBLE_DEVICES`) + mixed precision (`bf16` / `fp16`) |
| `integrations` | Optional W&B / MLflow (same shape as automodel) |
| `output` | Output entity name, optional description, **`save_method`** (controls what's persisted) |

Full template (every section, defaults inline):

```json
{
  "name": "<job-name>",
  "model": {
    "name": "default/<model-entity>",
    "max_seq_length": 2048,
    "load_in_4bit": true,
    "load_in_8bit": false,
    "dtype": "auto",
    "trust_remote_code": false,
    "device_map": null,
    "rope_scaling": null
  },
  "dataset": {
    "path": "default/<dataset-fileset>",
    "validation_path": null,
    "text_field": "text",
    "apply_chat_template": true,
    "packing": false
  },
  "training": {
    "training_type": "sft",
    "finetuning_type": "lora",
    "lora": {
      "rank": 16,
      "alpha": 16,
      "dropout": 0.0,
      "target_modules": ["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
      "bias": "none",
      "use_rslora": false,
      "random_state": 3407,
      "use_dora": false,
      "loftq_config": null,
      "modules_to_save": null,
      "layers_to_transform": null,
      "layer_replication": null,
      "init_lora_weights": true
    },
    "use_gradient_checkpointing": "unsloth"
  },
  "schedule": {
    "epochs": 1,
    "max_steps": null,
    "warmup_steps": 0,
    "warmup_ratio": null,
    "lr_scheduler_type": "linear",
    "lr_scheduler_kwargs": null,
    "logging_steps": 1,
    "save_steps": null,
    "eval_steps": null,
    "seed": 3407
  },
  "batch": {
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 4
  },
  "optimizer": {
    "learning_rate": 5e-5,
    "weight_decay": 0.0,
    "optim": "adamw_8bit",
    "adam_beta1": 0.9,
    "adam_beta2": 0.999,
    "adam_epsilon": 1e-8,
    "max_grad_norm": 1.0,
    "label_smoothing_factor": 0.0,
    "neftune_noise_alpha": null
  },
  "hardware": {
    "gpus": "0",
    "precision": "bf16"
  },
  "integrations": null,
  "output": {
    "name": "<output-name>",
    "description": null,
    "save_method": "lora"
  }
}
```

## Field reference (unsloth)

### `model`

`model` is an **object** (not a string). `name` is the platform model entity ref.

| Field | Default | Notes |
|-------|---------|-------|
| `name` | — | Model entity ref: `"name"` (uses job workspace) or `"workspace/name"`. Plugin resolves to a local path before training. |
| `max_seq_length` | `2048` | Truncate / pack to this length; lower if VRAM tight. |
| `load_in_4bit` | `true` | bitsandbytes 4-bit. Mutex with `load_in_8bit`. Default for Unsloth's headline path; required to fit larger models on small GPUs. |
| `load_in_8bit` | `false` | bitsandbytes 8-bit. Mutex with `load_in_4bit`. |
| `dtype` | `"auto"` | One of `"auto"`, `"bfloat16"`, `"float16"`, `"float32"`. |
| `trust_remote_code` | `false` | HF `trust_remote_code` flag for custom model code (required by some hybrid Mamba/MoE models, e.g. Nemotron-H). |
| `device_map` | `null` | Placement for `FastLanguageModel.from_pretrained`. `null` pins the whole model to the single visible GPU (`{"": 0}`) — the right default for this single-GPU backend. Leave unset unless experimenting; `"auto"`/`"balanced"`/`"sequential"` can spill layers to CPU on unified-memory hosts (GB10 / DGX Spark) and abort 4-bit loads. |
| `rope_scaling` | `null` | RoPE scaling for long-context extension, e.g. `{"type": "linear", "factor": 2.0}`. `null` uses the model's native context length. |

**Mutex:** `load_in_4bit` xor `load_in_8bit`. Both quantization flags are also **incompatible with `training.finetuning_type: "all_weights"`** — full SFT must use a non-quantized base.

> **Hybrid Mamba/MoE models (e.g. NVIDIA Nemotron-H `*-A3B`):** load in **16-bit** (`load_in_4bit: false`, `load_in_8bit: false`) — Unsloth's supported path for these. The 4-bit (bitsandbytes) path can hit a dtype mismatch inside the model's MoE expert accumulation. Keep `device_map` unset (single-GPU default) and set `trust_remote_code: true`.

### `dataset`

See `references/dataset-formats.md` § Unsloth for row-shape rules.

| Field | Default | Notes |
|-------|---------|-------|
| `path` | — | Training fileset ref (`"name"` or `"workspace/name"`). |
| `validation_path` | `null` | Optional validation fileset ref. |
| `text_field` | `"text"` | Column SFTTrainer reads. In `apply_chat_template: true` mode, the rendered template string is written into this column. |
| `apply_chat_template` | `false` | Set `true` for rows with a `messages` array (preferred when the tokenizer has a chat template). |
| `packing` | `false` | trl.SFTTrainer packing for throughput on short rows. |

### Unsloth `training`

| Field | Default | Notes |
|-------|---------|-------|
| `training_type` | `"sft"` | Only `"sft"` is implemented today. |
| `finetuning_type` | `"lora"` | `"lora"` (adapter; default) or `"all_weights"` (full SFT — heavy, no quantization). |
| `lora` | auto-filled when `finetuning_type` is `lora` | See LoRA subsection below. |
| `use_gradient_checkpointing` | `"unsloth"` | `"unsloth"` (recommended), `"true"`, or `"false"`. Unsloth's variant is faster than HF's. |

**LoRA block (`training.lora`):**

| Field | Default | Notes |
|-------|---------|-------|
| `rank` | `16` | Higher → more capacity, more VRAM. Cap at 32 if the adapter will deploy via default NIM / vLLM. |
| `alpha` | `16` | LoRA scaling; common rule of thumb `alpha ≈ rank` or `2× rank`. |
| `dropout` | `0.0` | LoRA dropout (0.0–<1.0). |
| `target_modules` | Unsloth 7-module set: `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` | Full attention + MLP. Override with a subset like `["q_proj","v_proj"]` for a lighter touch. |
| `bias` | `"none"` | `"none"` / `"all"` / `"lora_only"`. |
| `use_rslora` | `false` | Rank-stabilized LoRA. |
| `random_state` | `3407` | Reproducibility seed for the LoRA init. |
| `use_dora` | `false` | DoRA (weight-decomposed LoRA). Better quality at low ranks; adds overhead. |
| `loftq_config` | `null` | LoftQ init config for quantized bases. `null` disables. |
| `modules_to_save` | `null` | Extra non-LoRA modules trained & saved in full, e.g. `["embed_tokens","lm_head"]` (vocab changes / continued pretraining). |
| `layers_to_transform` | `null` | Restrict LoRA to specific layer index(es). `null` = all layers. |
| `layer_replication` | `null` | Layer-replication ranges for stacking, e.g. `[[0,16],[8,24]]`. |
| `init_lora_weights` | `true` | Init scheme. `true` = PEFT default; `"gaussian"`/`"pissa"`/`"olora"`/`"loftq"` for advanced inits. |

`lora` is auto-filled with these defaults when `finetuning_type: "lora"` and the user omits the block. Must be `null` / omitted when `finetuning_type: "all_weights"`.

### Unsloth `schedule`

| Field | Default | Notes |
|-------|---------|-------|
| `epochs` | `null` | Full passes. **`epochs` xor `max_steps`** — exactly one is required. |
| `max_steps` | `null` | Global step cap. Use alone for smoke tests; do not combine with `epochs`. |
| `warmup_steps` | `0` | Linear warmup. Mutex with `warmup_ratio`. |
| `warmup_ratio` | `null` | Fractional warmup over total steps. Mutex with `warmup_steps`. |
| `lr_scheduler_type` | `"linear"` | `"linear"`, `"cosine"`, `"constant"`, `"constant_with_warmup"`, `"cosine_with_restarts"`. |
| `lr_scheduler_kwargs` | `null` | Extra scheduler kwargs, e.g. `{"num_cycles": 3}` for `cosine_with_restarts`. `null` uses defaults. |
| `logging_steps` | `1` | Loss-log cadence. |
| `save_steps` | `null` | If set, save checkpoint every N steps. |
| `eval_steps` | `null` | If set with `validation_path`, eval every N steps. When `null` and `validation_path` is set, the training driver defaults to **one validation pass per effective epoch** at `max(1, effective_steps - 1)` (same effective-step cap as automodel's default `val_check_interval`). |
| `seed` | `3407` | Trainer seed (`TrainingArguments.seed`). |

**Hard mutex enforced by the schema:** `epochs` xor `max_steps`; `warmup_steps` xor `warmup_ratio`. Validation errors surface at submit time.

### Unsloth `batch`

| Field | Default | Notes |
|-------|---------|-------|
| `per_device_train_batch_size` | `1` | Forwarded verbatim to `TrainingArguments`. Drives peak VRAM. |
| `gradient_accumulation_steps` | `1` | Multiplies effective batch without raising VRAM. |

`effective_batch = per_device_train_batch_size × gradient_accumulation_steps`. No GBS divisibility math (single GPU). Starting points by model size are in `SKILL.md` § Batch sizing — unsloth.

### Unsloth `optimizer`

| Field | Default | Notes |
|-------|---------|-------|
| `learning_rate` | `2e-4` (schema default; skill uses `5e-5` for LoRA SFT) | See LR table below. |
| `weight_decay` | `0.0` | L2-style regularization. |
| `optim` | `"adamw_8bit"` | `"adamw_torch"`, `"adamw_torch_fused"` (Hopper+), `"adamw_8bit"`, `"paged_adamw_8bit"`, `"sgd"`. `adamw_8bit` has the smallest optimizer state and is Unsloth's notebook default. |
| `adam_beta1` | `0.9` | Adam/AdamW beta1. |
| `adam_beta2` | `0.999` | Adam/AdamW beta2. |
| `adam_epsilon` | `1e-8` | Adam/AdamW epsilon. |
| `max_grad_norm` | `1.0` | Gradient-clipping max norm (TRL default). |
| `label_smoothing_factor` | `0.0` | Label smoothing for the CE loss. `0.0` disables. |
| `neftune_noise_alpha` | `null` | NEFTune embedding-noise alpha (quality boost). `null` disables. |

`warmup_steps` is on `schedule`, not on `optimizer` (different from the automodel schema).

### `hardware`

| Field | Default | Notes |
|-------|---------|-------|
| `gpus` | `null` | Comma-separated CUDA indices inside the training container: `"0"` (typical). Sets `CUDA_VISIBLE_DEVICES` **before** `import torch`. **Selection, not reservation.** Unsloth uses one GPU per training process. |
| `precision` | `"bf16"` | `"bf16"` (Ampere+) or `"fp16"`. |

### Unsloth `integrations`

See **Integrations (automodel + unsloth)** above.

### `output`

| Field | Default | Notes |
|-------|---------|-------|
| `name` | auto-derived from `<model-entity>-<dataset>-<hex12>` | The output model entity / fileset name. |
| `description` | `null` | Free-form description carried onto the entity and fileset. |
| `save_method` | `"lora"` | `"lora"` (adapter — hot-reloads on base LoRA deployment; no new inference deploy), `"merged_16bit"` (merged checkpoint — **deploy** `output.name` as model entity), `"merged_4bit"` (lossy, storage-tight; deploy like merged). `merged_*` requires `training.finetuning_type: "lora"`. |

After `to_spec`, the canonical `OutputResponse` also carries `type` (`"adapter"` for `save_method: "lora"`, `"model"` otherwise) and `fileset` (defaults to `name`); both are derived — submitter doesn't set them.

## Tuning guide (unsloth)

VRAM / batch tuning is in **`SKILL.md` § Batch sizing — unsloth**. Below covers non-batch fields.

### Unsloth learning rate (LoRA SFT, starting points)

Same scale as automodel (the underlying optimizer math is the same):

| Model scale | Suggested `learning_rate` |
|-------------|---------------------------|
| ≤ 3B | `5e-5` – `1e-4` |
| 3B – 8B | `2e-5` – `5e-5` |
| > 8B | `1e-5` – `2e-5` |

Schema default is `2e-4` (Unsloth notebook default — works for small adapters with `adamw_8bit`). Skill defaults are conservative `5e-5`.

### Unsloth LoRA rank / alpha

| Use case | `rank` | `alpha` |
|----------|--------|---------|
| Default / balanced | 16 | 16 |
| Lighter touch | 8 | 16 |
| More capacity (inference-safe max on default NIM/vLLM) | 32 | 32 or 64 |

Drop `rank` before lowering batch when OOM. Higher `alpha/rank` ratios amplify adapter influence; Unsloth's defaults keep `alpha == rank`.

### Save-method picker

| User wants | `save_method` | Inference after training |
|------------|---------------|--------------------------|
| Smallest artefact; hot-reload on base LoRA deployment | `lora` | No new deploy — adapter loads on existing `lora_enabled` deployment |
| Full-weight checkpoint as standalone model | `merged_16bit` | **Deploy** `output.name` as new model entity |
| Disk-tight merged checkpoint (lossy) | `merged_4bit` | **Deploy** `output.name` as new model entity |
| Full SFT (no LoRA) | `lora` is invalid; output is always a full model | **Deploy** `output.name` as new model entity |

`merged_*` require `training.finetuning_type: "lora"`. The schema validator surfaces a clear error if violated.

### Smoke test (unsloth)

```json
"schedule": { "max_steps": 50 }
```

(omit `epochs`).

### Distillation

Not supported by unsloth today (`training_type` is `Literal["sft"]`). Use automodel for distillation.

---

# Source of truth

| Resource | Path | Use for |
|----------|------|---------|
| **Batch / multi-GPU / 48 GB LoRA (automodel)** | `SKILL.md` § Batch sizing — automodel, § Multi-GPU | Choosing `micro`, GBS, LR, TP vs data parallel |
| **Batch (unsloth, single GPU)** | `SKILL.md` § Batch sizing — unsloth | `per_device_train_batch_size` × `gradient_accumulation_steps` starting points |
| Submit schema (automodel) | `plugins/nemo-automodel/src/nemo_automodel_plugin/schema.py` | Allowed JSON fields |
| Schema → compiler mapping (automodel) | `services/automodel/src/nmp/automodel/adapter.py` | `dataset.training` → compiler `dataset` string |
| API field descriptions (automodel) | `services/automodel/src/nmp/automodel/api/v2/jobs/schemas.py` | Compiler-internal shape (not submit JSON) |
| Submit schema (unsloth) | `plugins/nemo-unsloth/src/nemo_unsloth_plugin/schema.py` | Allowed JSON fields (`UnslothJobInput`) |
| Canonical schema (unsloth) | `services/unsloth/src/nmp/unsloth/schemas.py` | Post-`to_spec` shape; what `train_sft` consumes |
| Training driver (unsloth) | `services/unsloth/src/nmp/unsloth/tasks/training/backends/unsloth_sft.py` | Field → call-site mapping (FastLanguageModel.from_pretrained, SFTTrainer, save_pretrained{,_merged}) |
| JSON examples (automodel) | `plugins/nemo-automodel/tests/fixtures/*.json` | Copy-paste templates (ignore fixture `max_steps` in prod) |
| JSON example (unsloth) | `plugins/nemo-unsloth/tests/fixtures/minimal_unsloth_sft.json` | Smoke-test template (ignore `max_steps` for real runs) |
| Full spec doc (automodel) | `plugins/nemo-automodel/SCOPE.md` (simplified JSON section) | Design notes |
| Plugin README (unsloth) | `plugins/nemo-unsloth/README.md` | Submit-only CLI, 4-step container job, GPU selection |
