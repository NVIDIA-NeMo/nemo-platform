---
name: nemo-customizer
description: >-
  Fine-tune models on NeMo Platform via `nemo customization automodel submit`:
  HF dataset conversion, filesets, model entities, SFT/LoRA job JSON (hyperparameters,
  batch, schedule, optimizer), and job polling. Use for train, fine-tune, customize,
  SFT, LoRA, learning rate, epochs, or nemo customization.
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

End-to-end **SFT + LoRA** on NeMo Platform. Default plugin: **automodel**. Batch shell work; reuse resources with `--exist-ok`; skip CLI `--help` unless a command fails.

## Gotchas

- Run all `uv run` commands from the **nemo-platform** git root (top-level `pyproject.toml`), not a plugin subfolder.
- Set `NEMO_BASE_URL` (or `NMP_BASE_URL`) only when the user gives a platform URL; default `http://127.0.0.1:8080`.
- **Never set `max_steps` together with `epochs`.** `max_steps` is a global cap and stops mid-epoch. Test fixtures include `max_steps` for smoke tests — do not copy into production jobs.
- **Job done = top-level `status`** in `completed` | `failed` | `cancelled`. Steps can all be `completed` while the job is still `active` (upload, entity registration). `status_details.phase` may stay `training` with `progress_pct: 100` for a long time — keep polling.
- Model spec fills async: **submit without polling** `nemo models get` unless submit fails.
- HF dataset id from the user → convert locally; do not ask for local paths first.
- Dataset fileset name = HF dataset **name** only (`tau/commonsense_qa` → `commonsense_qa`), not the model name.
- Prefer **CHAT** JSONL when the model has a chat template; details in `references/dataset-formats.md`.
- User asks to tune LR, epochs, LoRA rank, batch size, or parallelism → edit `/tmp/job.json` per `references/hyperparameters.md` (schema: `nemo customization automodel explain`).
- **Do not use local `docker info`** to pick automodel vs unsloth. After auth, run `nemo jobs list-execution-profiles` against the user's platform (see `references/troubleshooting.md`).
- For submit/image/plugin errors, read `references/troubleshooting.md`.

## Workflow

```
- [ ] export NEMO_BASE_URL (if user provided endpoint)
- [ ] cd nemo-platform && uv run nemo auth login --unsigned-token --email <user email or admin@example.com>
- [ ] nemo jobs list-execution-profiles — GPU profile → automodel; else see troubleshooting (no local docker check)
- [ ] Convert HF dataset → /tmp/train-data/*.jsonl (see references/hf-conversion.md)
- [ ] Create dataset fileset (--exist-ok), upload train.jsonl (+ validation.jsonl), nemo files list to verify
- [ ] Create HF weights fileset + model entity if missing (--exist-ok)
- [ ] Write /tmp/job.json (defaults in SKILL.md; user tuning → references/hyperparameters.md)
- [ ] uv run nemo customization automodel submit /tmp/job.json --workspace default
- [ ] Poll until top-level terminal (scripts/poll_automodel_job.sh or 60–120s manual polls)
- [ ] Report using output template below
```

## Fast path

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

## Defaults

| Field | Value |
|-------|-------|
| Workspace | `default` |
| Plugin | `automodel` |
| Training | SFT + LoRA, `max_seq_length` 2048 |
| Schedule | `epochs` ≥ 1; omit `max_steps` |
| Parallelism | 1 node, 1 GPU, TP=1 |
| Batch | `global_batch_size` 4, `micro_batch_size` 1 |
| Optimizer | `learning_rate` 5e-5 |
| Auth email | `admin@example.com` unless user specifies |

## Worked example

`Qwen/Qwen3-1.7B` + `tau/commonsense_qa` → CHAT JSONL, fileset `commonsense_qa`, entity `qwen3-1.7b`, output `qwen3-1.7b-commonsense-qa-lora`, `epochs: 1` (no `max_steps`).

## Report to user

```markdown
## Fine-tune result

- **Job:** automodel-<id>
- **Model entity:** default/<model-entity>
- **Output adapter fileset:** <output.name>
- **Status:** <completed|failed|cancelled>
- **Notes:** <error_details or phase if failed>
```

## Reference files

| When | Read |
|------|------|
| HF conversion or MCQA shaping | `references/hf-conversion.md` |
| CHAT vs SFT vs CUSTOM | `references/dataset-formats.md` |
| Hyperparameters, tuning, LoRA, batch/schedule | `references/hyperparameters.md` |
| Backend choice, execution profiles, submit failure, images, CLI | `references/troubleshooting.md` |
| Live JSON schema | `uv run nemo customization automodel explain` |
| Job JSON fixture | `plugins/nemo-automodel/tests/fixtures/qwen3_0.6b_sft_lora.json` (ignore `max_steps` for real runs) |

Related: `plugins/nemo-automodel/README.md`, `plugins/nemo-customizer/docs/CUSTOMIZATION.md`, skills **`nemo-files`**, **`nemo-status`**.
