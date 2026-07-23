# Hyperparameters

Two backend job schemas live in this skill. Each backend has its own field reference file — **pick by plugin**:

| Plugin | Schema class | Schema dump | Field reference |
|--------|--------------|-------------|-----------------|
| `automodel` | `AutomodelJobInput` (`plugins/nemo-automodel/src/nemo_automodel_plugin/schema.py`) | `nemo customization automodel explain` | **`hyperparameters-automodel.md`** |
| `unsloth` | `UnslothJobInput` (`plugins/nemo-unsloth/src/nemo_unsloth_plugin/schema.py`) | `nemo customization unsloth explain` | **`hyperparameters-unsloth.md`** |

Both schemas use `extra="forbid"` — unknown keys raise validation errors. Field names are **not** interchangeable across backends (e.g. automodel uses `micro_batch_size` / `global_batch_size` / `parallelism`; unsloth uses `per_device_train_batch_size` / `gradient_accumulation_steps` / `hardware`). Use the right schema for the chosen plugin.

**Batch sizing, 48 GB VRAM tables, multi-GPU (data parallel vs tensor parallel), and throughput tuning** live in **`batch-sizing.md`** (automodel + unsloth). These per-backend files are the **field glossary**, full JSON template per backend, and distillation/KD (automodel) — not the place to pick batch sizes for production runs.

## Table of contents

| Read this file | For |
|----------------|-----|
| **`hyperparameters-automodel.md`** | Automodel job JSON layout, full template, `training` / `schedule` / `batch` / `optimizer` / `parallelism` field reference, LR & LoRA-rank tuning, presets, distillation/KD |
| **`hyperparameters-unsloth.md`** | Unsloth job JSON layout, full template, `model` / `dataset` / `training` / `schedule` / `batch` / `optimizer` / `hardware` / `output` field reference, LR & LoRA-rank tuning, save-method picker |
| **`batch-sizing.md`** | ≥48 GB VRAM batch tables, multi-GPU (data vs tensor parallel), OOM / throughput tuning (automodel + unsloth) |
| **Integrations** (below) | W&B / MLflow `integrations` object — both backends (automodel, unsloth) |
| **Source of truth** (below) | Schema source files, compiler mappings, fixtures per backend |

---

## Integrations (all backends)

**Both backends** (automodel, unsloth) accept the same `integrations` object on job JSON (`IntegrationsSpec` in `nemo_platform_plugin.integrations`) — **W&B** and **MLflow**. A non-null `wandb` / `mlflow` block **requests** that integration; the training runtime **activates** it only when credentials/URIs are available (W&B needs `WANDB_API_KEY`, MLflow needs a tracking URI). Omit the field or set a block to `null` to disable. There is no `enabled` flag and no `report_to` on input — `report_to` is derived at runtime from activated integrations. The compiler logs a warning when W&B is requested without `api_key_secret` or MLflow without `tracking_uri`.

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

Set `"integrations": null` or omit the field when tracking is not needed. Fixtures per backend: automodel → `plugins/nemo-automodel/tests/fixtures/integrations_wandb_mlflow.json`; unsloth → `plugins/nemo-unsloth/tests/fixtures/integrations_wandb_mlflow.json`.

**Local setup (MLflow server, `docker0` tracking URI, jobs-launcher, W&B secret) — Docker-runtime (automodel / unsloth):** `references/integrations-setup.md`.

**Unsloth note:** HuggingFace `TrainingArguments.run_name` is shared by W&B and MLflow. When both backends are active, `wandb.name` wins if set; otherwise `mlflow.name` is used. If both names are set to different values, a runtime warning is logged and W&B's name is used.

---

# Source of truth

| Resource | Path | Use for |
|----------|------|---------|
| **Batch / multi-GPU / 48 GB LoRA (automodel)** | `batch-sizing.md` § Batch sizing — automodel, § Multi-GPU | Choosing `micro`, GBS, LR, TP vs data parallel |
| **Batch (unsloth, single GPU)** | `batch-sizing.md` § Batch sizing — unsloth | `per_device_train_batch_size` × `gradient_accumulation_steps` starting points |
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
