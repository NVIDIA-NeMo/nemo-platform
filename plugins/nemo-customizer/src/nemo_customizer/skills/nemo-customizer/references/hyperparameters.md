# Hyperparameters (automodel job JSON)

Job JSON for `nemo customization automodel submit` uses **`AutomodelJobInput`** (`plugins/nemo-automodel/src/nemo_automodel_plugin/schema.py`). Only fields in that schema are accepted (`extra="forbid"`).

**Schema dump:** from nemo-platform root:

```bash
uv run nemo customization automodel explain
```

**Contract examples:** `tests/customizer-automodel-contract/input_configs/` (legacy shape; map `batch_size` → `global_batch_size` in submit JSON).

---

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
      "merge": false,
      "target_modules": null
    },
    "max_seq_length": 2048,
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
    "sequence_packing": false
  },
  "optimizer": {
    "learning_rate": 5e-5,
    "weight_decay": 0.01,
    "warmup_steps": 0
  },
  "parallelism": {
    "num_nodes": 1,
    "num_gpus_per_node": 1,
    "tensor_parallel_size": 1,
    "pipeline_parallel_size": 1,
    "context_parallel_size": 1,
    "expert_parallel_size": null
  },
  "output": { "name": "<output-name>", "description": null },
  "integrations": null
}
```

---

## Field reference

### `training`

| Field | Default | Notes |
|-------|---------|-------|
| `training_type` | `sft` | `distillation` requires `teacher_model` (entity ref) |
| `finetuning_type` | `lora` | `all_weights` (full fine-tune), `lora_merged` (merge adapter into base) |
| `lora.rank` | `16` | Higher → more capacity, more VRAM. Typical training range 8–32; **cap at 32** if the adapter will be served with default NIM / vLLM (rank > 32 may not load) |
| `lora.alpha` | `32` | Scaling; common rule of thumb **alpha ≈ 2× rank** |
| `lora.merge` | `false` | If true with `lora_merged`, output is full weights not adapter |
| `lora.target_modules` | `null` | e.g. `["q_proj","v_proj"]`; null = platform default targets |
| `max_seq_length` | `2048` | Truncate/pack to this length; lower if OOM |
| `teacher_model` | — | **Model entity ref** (not HF id). Required for distillation; see below |
| `distillation_ratio` | `0.5` | KD blend (0–1) |
| `distillation_temperature` | `1.0` | KD temperature |
| `teacher_precision` | `bf16` | `bf16` \| `fp16` \| `fp32` |
| `offload_teacher` | `false` | Offload teacher weights to CPU |

LoRA block is auto-created when `finetuning_type` is `lora` or `lora_merged`.

### `schedule`

| Field | Default | Notes |
|-------|---------|-------|
| `epochs` | `1` | Must be **≥ 1**. Full passes over training set |
| `max_steps` | `null` | **Global step cap.** Omit for epoch-based runs |
| `val_check_interval` | `null` | `≤ 1.0` = fraction of epoch; `> 1` = every N steps |
| `seed` | `null` | Reproducibility |

**Gotcha:** Do **not** set `max_steps` with `epochs` for normal training. `max_steps` stops early (e.g. `epochs: 1` + `max_steps: 100` ends at step 100). Use `max_steps` **alone** only for smoke tests.

### `batch`

| Field | Default | Notes |
|-------|---------|-------|
| `global_batch_size` | `8` | Effective batch across all GPUs (skill default **4** for small local runs) |
| `micro_batch_size` | `1` | Per-GPU microbatch; increase only if VRAM allows |
| `sequence_packing` | `false` | Pack short sequences for throughput (needs compatible data) |

**Validation:** `global_batch_size` must be divisible by `micro_batch_size × data_parallel_size`, where:

`data_parallel_size = (num_nodes × num_gpus_per_node) / (tensor_parallel_size × pipeline_parallel_size × context_parallel_size)`

Example: 1 node, 1 GPU, TP=1 → DP=1 → GBS must be a multiple of `micro_batch_size`.

### `optimizer`

| Field | Default | Notes |
|-------|---------|-------|
| `learning_rate` | `5e-6` (schema) | Skill uses **5e-5** for small LoRA SFT; see tuning below |
| `weight_decay` | `0.01` | L2-style regularization |
| `warmup_steps` | `0` | Linear warmup; try ~10% of total steps for long runs |

`adam_beta1` / `adam_beta2` are **not** in the simplified submit schema (fixed in compiler adapter). Use contract JSONs only if your platform version adds them.

### `parallelism`

| Field | Default | Notes |
|-------|---------|-------|
| `num_nodes` | `1` | Multi-node distributed jobs |
| `num_gpus_per_node` | `1` | GPUs per node |
| `tensor_parallel_size` | `1` | Shard layers across GPUs (large models) |
| `pipeline_parallel_size` | `1` | Pipeline stages |
| `context_parallel_size` | `1` | Long-context sharding |
| `expert_parallel_size` | `null` | MoE only; must divide `data_parallel_size × context_parallel_size` |

**MoE:** If `expert_parallel_size > 1` and multiple GPUs, `tensor_parallel_size` must be **1**.

### `integrations` (optional)

```json
"integrations": {
  "wandb": { "enabled": true, "project": "my-project", "api_key_secret": "wandb-api-key" },
  "mlflow": null
}
```

---

## Tuning guide (when the user asks)

Apply user overrides to `/tmp/job.json` before submit. If unspecified, keep skill defaults from `SKILL.md`.

| Symptom / goal | Try first |
|----------------|-----------|
| CUDA OOM | Lower `micro_batch_size` (→ 1), then `global_batch_size`, then `max_seq_length` |
| Training too slow | Raise `global_batch_size` (if divisible), enable `sequence_packing`, more GPUs |
| Underfitting | More `epochs`, slightly higher `learning_rate`, higher LoRA `rank` (≤ 32 for NIM/vLLM deploy) |
| Overfitting | Fewer `epochs`, lower `learning_rate`, higher `weight_decay`, smaller `rank` |
| Quick smoke test | `max_steps` only (e.g. 10–50), **omit or ignore epoch goal**; or `epochs: 1` on tiny slice |
| Reproducibility | Set `schedule.seed` |

### Learning rate (LoRA SFT, starting points)

| Model scale | Suggested `learning_rate` |
|-------------|---------------------------|
| ≤ 3B | `5e-5` – `1e-4` |
| 3B – 8B | `2e-5` – `5e-5` |
| > 8B | `1e-5` – `2e-5` |

Schema default is `5e-6` (conservative). Fixtures: `qwen3_0.6b_sft_lora.json` uses `5e-5`; `minimal_sft_lora.json` uses `5e-6`.

### LoRA rank / alpha

**Deployment cap:** Default **NIM** and **vLLM** LoRA serving paths support rank **≤ 32**. Use `rank` 32 (not higher) when the fine-tuned adapter will be deployed for inference on those stacks unless the user confirms a higher rank is supported.

| Use case | `rank` | `alpha` |
|----------|--------|---------|
| Default / balanced | 16 | 32 |
| Low VRAM / light touch | 8 | 16 |
| More capacity (inference-safe max) | 32 | 64 |

### Epochs vs dataset size

One epoch = one full pass over `train.jsonl`. For ~10k short MCQA examples and GBS 4, expect thousands of steps per epoch on 1 GPU — plan poll time accordingly.

---

## Presets (copy into job JSON)

**Small model, 1 GPU (default skill path)**

```json
"schedule": { "epochs": 1 },
"batch": { "global_batch_size": 4, "micro_batch_size": 1 },
"optimizer": { "learning_rate": 5e-5 },
"training": { "training_type": "sft", "finetuning_type": "lora", "max_seq_length": 2048 }
```

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

**Multi-GPU same node (e.g. 4× GPU, no TP)**

```json
"parallelism": { "num_nodes": 1, "num_gpus_per_node": 4, "tensor_parallel_size": 1 },
"batch": { "global_batch_size": 16, "micro_batch_size": 1 }
```

Ensure GBS is divisible by `4 × micro_batch_size`.

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

uv run nemo files filesets create "$TEACHER_WEIGHTS" --workspace default --purpose model --exist-ok \
  --storage '{"type":"huggingface","repo_id":"'"$TEACHER_HF"'","repo_type":"model","revision":"main"}'

uv run nemo models create "$TEACHER_ENTITY" --workspace default --exist-ok \
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
  "batch": { "global_batch_size": 4, "micro_batch_size": 1 },
  "optimizer": { "learning_rate": 5e-5 },
  "parallelism": { "num_nodes": 1, "num_gpus_per_node": 1, "tensor_parallel_size": 1 },
  "output": { "name": "<output-name>" }
}
```

| Field | Meaning |
|-------|---------|
| `distillation_ratio` | Blend of KD vs CE loss (`0` = CE only, `1` = KD only) |
| `distillation_temperature` | Softmax temperature for teacher logits |
| `offload_teacher` | CPU-offload frozen teacher weights to save GPU memory |

---

## Source of truth

| Resource | Path |
|----------|------|
| Submit schema | `plugins/nemo-automodel/src/nemo_automodel_plugin/schema.py` |
| Schema → compiler mapping | `services/automodel/src/nmp/automodel/adapter.py` |
| API field descriptions | `services/automodel/src/nmp/automodel/api/v2/jobs/schemas.py` |
| JSON examples | `plugins/nemo-automodel/tests/fixtures/*.json` |
| Full spec doc | `plugins/nemo-automodel/SCOPE.md` (simplified JSON section) |
