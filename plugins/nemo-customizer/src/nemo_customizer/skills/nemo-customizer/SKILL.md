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
- User asks to tune LR, epochs, LoRA rank, batch size, or parallelism → edit `/tmp/job.json` per **Batch sizing** below and `references/hyperparameters.md` (schema: `nemo customization automodel explain`).
- Skill **defaults** (`micro_batch_size` 1, `global_batch_size` 4) are safe on unknown VRAM. When the user has **≥48 GB** on one GPU, use **Batch sizing** instead of defaults.
- **Do not use local `docker info`** to pick automodel vs unsloth. After auth, run `uv run nemo jobs list-execution-profiles -f json` against the user's platform (see `references/troubleshooting.md`). Default output is a table — **`-f json` is required** for scripting; parse **stdout only** (do not pipe `2>&1` into `json.load`).
- For submit/image/plugin errors, read `references/troubleshooting.md`.

## Workflow

```
- [ ] export NEMO_BASE_URL (if user provided endpoint)
- [ ] cd nemo-platform && uv run nemo auth login --unsigned-token --email <user email or admin@example.com>
- [ ] uv run nemo jobs list-execution-profiles -f json — GPU profile → automodel; else see troubleshooting (no local docker check)
- [ ] Convert HF dataset → /tmp/train-data/*.jsonl (see references/hf-conversion.md)
- [ ] Create dataset fileset (--exist-ok), upload train.jsonl (+ validation.jsonl), nemo files list to verify
- [ ] Create HF weights fileset + model entity if missing (--exist-ok)
- [ ] Write /tmp/job.json (batch sizing for ≥48 GB GPU; else Defaults table)
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
| Batch | `global_batch_size` 4, `micro_batch_size` 1 (unknown VRAM; see **Batch sizing** for ≥48 GB) |
| Optimizer | `learning_rate` 5e-5 |
| Auth email | `admin@example.com` unless user specifies |

## Batch sizing (≥48 GB VRAM)

Assume **one GPU with at least 48 GB** (e.g. RTX 5880 / A6000 / L40), `parallelism` = 1 node × 1 GPU, `tensor_parallel_size` 1, bf16, `training_type` `sft`, LoRA **rank 16** unless the user asks otherwise.

**How to size**

1. Read **model size** from the entity (`nemo models get`) or HF card (parameter count).
2. Pick **`finetuning_type`**: `lora` (adapter only, default) vs `all_weights` (full SFT — much heavier).
3. Set **`max_seq_length`** (2048 is the skill default; shorter seq → more batch headroom).
4. Set **`micro_batch_size`** first (drives peak VRAM), then **`global_batch_size`** as a multiple of `micro_batch_size` (gradient accumulation when GBS > micro).

**Constraint:** `global_batch_size` must be divisible by `micro_batch_size × data_parallel_size`, where `data_parallel_size = (num_nodes × num_gpus_per_node) / (tensor_parallel_size × pipeline_parallel_size × context_parallel_size)` (1 for a single-GPU job).

### LoRA (`finetuning_type: lora`) — `max_seq_length` 2048

| Model params | `micro_batch_size` | `global_batch_size` | `learning_rate` |
|--------------|-------------------:|--------------------:|----------------:|
| ≤2B | 16 | 64 | `1e-4` |
| 2B–4B | 8 | 32 | `8e-5` |
| 4B–8B | 4 | 16 | `5e-5` |
| 8B–14B | 2 | 8 | `2e-5` |
| >14B | 1 | 4 | `1e-5` |

Validated on platform: **Qwen3-1.7B** LoRA + `commonsense_qa` @ 2048 — `micro` 1 / GBS 4 under-filled VRAM (~56 min); `micro` 16 / GBS 64 completed in ~8 min with similar val loss.

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
| Slow / low GPU memory use | Increase `micro_batch_size`, then raise `global_batch_size` (keep divisible); scale `learning_rate` up modestly with GBS (e.g. 5e-5 → 1e-4 when 4× GBS) |
| User wants max throughput | Prefer higher `micro_batch_size` over very large GBS with `micro_batch_size` 1 |

Field details and distillation: `references/hyperparameters.md`.

## Worked example

`Qwen/Qwen3-1.7B` + `tau/commonsense_qa` → CHAT JSONL, fileset `commonsense_qa`, entity `qwen3-1.7b`, output `qwen3-1.7b-commonsense-qa-lora`, `epochs: 1` (no `max_steps`). On ≥48 GB GPU use LoRA ≤2B row: `micro_batch_size` 16, `global_batch_size` 64, `learning_rate` `1e-4`.

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
| Hyperparameters, distillation, extra presets | `references/hyperparameters.md` |
| Batch sizing (≥48 GB), OOM / throughput | **Batch sizing** section above |
| Backend choice, execution profiles, submit failure, images, CLI | `references/troubleshooting.md` |
| Live JSON schema | `uv run nemo customization automodel explain` |
| Job JSON fixture | `plugins/nemo-automodel/tests/fixtures/qwen3_0.6b_sft_lora.json` (ignore `max_steps` for real runs) |

Related: `plugins/nemo-automodel/README.md`, `plugins/nemo-customizer/docs/CUSTOMIZATION.md`, skills **`nemo-files`**, **`nemo-status`**.
