---
name: nemo-customizer
description: >-
  Fine-tune models on NeMo Platform with `automodel`, `unsloth`, or `rl` (all
  `submit`-only): HF dataset conversion, filesets, model entities, and job JSON
  (hyperparameters, batch, schedule, optimizer) + job polling. `automodel`/`unsloth`
  run SFT/LoRA as Docker GPU jobs; `rl` runs DPO (preference optimization) on a Ray
  cluster (Kubernetes). Use for train, fine-tune, customize, SFT, LoRA, DPO,
  preference optimization, learning rate, epochs, or nemo customization.
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
  - dpo
  - direct preference optimization
  - preference optimization
  - preference tuning
  - automodel
  - unsloth
  - nemo-rl
  - nemo rl
  - nemo customization
  - nemo-customization
  - customizer
  - customization training
  - automodel submit
  - unsloth submit
  - rl submit
not-for:
  - nemo-build-agent (agent scaffold/deploy, not weight training)
  - nemo-explore (agent design only)
  - nemo-setup (platform install; route here when CLI resolution fails)
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

End-to-end **SFT + LoRA** (automodel/unsloth) and **DPO** (rl) on NeMo Platform. Three backend plugins ship in this repo — all are **`submit`-only** (local `run` is hard-disabled on each):

| Backend | Verb | Trains | Where it runs | Pick when |
|---------|------|--------|---------------|-----------|
| **`automodel`** (default) | `submit` | SFT / LoRA | Platform **Docker GPU executor** (Jobs service schedules containers on the platform host's daemon) | General SFT/LoRA; multi-GPU (data/tensor parallel); distillation; full-weight SFT |
| **`unsloth`** | `submit` | SFT / LoRA | Same — Docker GPU job with 4 steps (download → train → upload → model-entity) | User asks for Unsloth, or wants Unsloth's 4-bit LoRA path / optimizer defaults on a single GPU |
| **`rl`** | `submit` | **DPO** (preference) | Platform **Kubernetes executor** — provisions a **Ray** cluster; 4 steps (download → DPO train → upload → model-entity) | Preference optimization / DPO / RLHF-style alignment from a `{prompt, chosen, rejected}` dataset; full-weight only |

`nemo-customizer` is the router (`nemo customization …`); training backends are separate plugins (`nemo-automodel`, `nemo-unsloth`, `nemo-rl`). `submit` posts to the platform API; the platform runs training in container steps — **not** in the CLI shell. Heavy ML deps live in container images only.

**Runtime split:** `automodel`/`unsloth` need `platform.runtime: docker`; `rl` needs `platform.runtime: kubernetes` (no local Docker fallback — it schedules a Ray cluster on the remote cluster). A given platform is usually one or the other — confirm with execution profiles before picking `rl`.

Decision rule below in **Plugin pick**. Batch shell work; reuse resources with `--exist-ok`; skip CLI `--help` unless a command fails.

## Pre-flight — CLI resolution

Run from the **nemo-platform** git root (top-level `pyproject.toml`), not a plugin subfolder. Example commands below use `nemo …` — resolve the invocation **once** before any other step:

```bash
cd /path/to/nemo-platform
if command -v nemo >/dev/null 2>&1; then
  echo "nemo"
elif command -v uv >/dev/null 2>&1 && uv run nemo --help >/dev/null 2>&1; then
  echo "uv run nemo"
else
  echo "CLI_NOT_FOUND"
fi
```

| Result | Action |
|--------|--------|
| `nemo` | Use `nemo …` for all commands in this workflow |
| `uv run nemo` | Prefix every command with `uv run` (repo dev checkout without `nemo` on `PATH`) |
| `CLI_NOT_FOUND` | Stop. Route to **nemo-setup** (`make bootstrap` then `nemo setup` from the nemo-platform repo root). Do not continue. |

## Authentication (optional)

Platform auth is **not required** to run customization when the cluster has authentication disabled. Check with `nemo auth status` — if it reports authentication is disabled, skip login and proceed.

When auth **is** enabled on the connected platform, API calls need credentials:

| Situation | Action |
|-----------|--------|
| Auth disabled | Skip login |
| Auth enabled, unsigned JWT allowed (typical local dev: `auth.allow_unsigned_jwt: true`) | `nemo auth login --unsigned-token --email <user email or admin@example.com>` |
| Auth enabled, OIDC configured | `nemo auth login` (or `--username` / `--password` for non-interactive) |
| 401/403 on any platform call | Run the matching login above, then retry |

Use `admin@example.com` unless the user specifies another email. Run `nemo auth status` after login to confirm.

## HuggingFace token (gated models)

Gated HF repos (Llama, Gemma, Mistral instruct, …) need a platform secret (convention: **`hf-token`**) referenced as **`token_secret`** on the **model fileset** — not in job JSON (unlike W&B's `api_key_secret`). The Files service does **not** read your local `~/.cache/huggingface` or shell `HF_TOKEN`.

| Model access | Action |
|--------------|--------|
| Public (e.g. `Qwen/Qwen3-1.7B`) | Skip; omit `token_secret` on the fileset |
| Gated / private HF repo | Before model fileset creation or job submit: `nemo secrets list --workspace default` and confirm `hf-token` exists. If missing, **ask the user** for their HF token and **stop** — do not create the fileset or submit until wired up. |

Full create/update commands, fileset `token_secret`, license acceptance, and download-phase errors: `references/troubleshooting.md` § **Gated HuggingFace models**.

## Plugin pick

1. Run `nemo jobs list-execution-profiles -f json` (login first only if auth is enabled — see **Authentication**; see `references/troubleshooting.md` for parsing).
2. If the task is **DPO / preference optimization** (a `{prompt, chosen, rejected}` dataset, "align", "preference", "RLHF-style") **or** the user explicitly asked for NeMo-RL → **`rl`** (requires a GPU profile **and** `platform.runtime: kubernetes`).
3. Else if the user explicitly asked for Unsloth → **`unsloth`**.
4. Else if the user explicitly asked for Automodel → **`automodel`**.
5. Else if any profile has `provider: gpu` or `gpu_distributed` → **`automodel`** (default, SFT/LoRA).
6. Else stop and tell the user GPU customization is unavailable (all backends need a GPU execution profile; `automodel`/`unsloth` also need `platform.runtime: docker`, `rl` needs `platform.runtime: kubernetes`).

**`rl` runtime gate:** `rl submit` fails fast unless the platform runs `platform.runtime: kubernetes` (`require_distributed_runtime`). rl job steps execute as **Kubernetes pods via the `kubernetes_job` execution backend** — the **`docker` job backend cannot run rl**. Before submitting rl, confirm with `nemo jobs list-execution-profiles -f json` that the `cpu`/`gpu` profiles report `backend: kubernetes_job` (or `volcano_job`). If they report `backend: docker`/`subprocess`, the platform is **not** configured for rl: stop and tell the user DPO needs a Kubernetes-runtime platform — do **not** start/reuse a docker-runtime platform, and do **not** fall back to automodel/unsloth (those are SFT/LoRA, not DPO). To stand up or configure one, see `references/rl-kubernetes-runtime.md`.

For **`automodel`/`unsloth`**, training never runs inside the `nemo` CLI process. After `submit`, the platform's **local Docker executor** launches GPU container steps on the daemon attached to that platform host (often the same machine as `http://127.0.0.1:8080`, but always query the platform — not the agent's shell GPU or a separate `docker info` on another box). **`rl` does not use the Docker executor** — its steps run on the Kubernetes cluster the platform is configured against.

## Gotchas

- Resolve the CLI per **Pre-flight — CLI resolution** before any `nemo …` command; run from the **nemo-platform** git root, not a plugin subfolder.
- Set `NMP_BASE_URL` only when the user gives a platform URL; default `http://127.0.0.1:8080` (same as `http://localhost:8080`). The `nemo` CLI reads this env var (see SDK `NMP_BASE_URL`). Track whether the user **overrode** the base URL — see **Platform unreachable** below.
- **Platform unreachable** — if any platform API call fails with a connection error (`Connection error`, timeout, refused):
  - **User gave a custom URL** or you exported a non-default `NMP_BASE_URL`: stop and tell the user the platform is not reachable at that address. Do **not** offer to start local services.
  - **Default URL only** (no user override): **ask** whether to start the platform locally. If they agree, from the **nemo-platform** git root run in the **background**:

    ```bash
    nemo services run \
      --host 0.0.0.0 \
      --port 8080 \
      --controllers jobs,entities,models \
      --service-group all
    ```

    Poll until healthy (`curl -sf http://127.0.0.1:8080/health/ready` or retry `nemo jobs list-execution-profiles -f json`), then continue the workflow. Do not start services without asking.
    - ⚠️ **This default start is a DOCKER-runtime platform — valid for `automodel`/`unsloth` only.** It is **NOT** valid for **`rl`**: rl needs `platform.runtime: kubernetes` with a `kubernetes_job` execution backend. Starting this default and submitting rl will fail the runtime gate. For rl, configure/point at a Kubernetes-runtime platform instead — see `references/rl-kubernetes-runtime.md`. Never start or reuse a docker-runtime platform for rl.
- **All backends are `submit` only** — `nemo customization <plugin> run …` hard-fails with a pointer to `submit` (automodel, unsloth, and rl each disable local `run`). Do not improvise verbs or pass `--venv`.
- **Never set `max_steps` together with `epochs`** (automodel + unsloth; rl has the same caveat — see **rl (DPO) gotchas**). `max_steps` is a global cap and stops mid-epoch. Test fixtures include `max_steps` for smoke tests — do not copy into production jobs. Unsloth's schema enforces this as a hard mutex; automodel allows both but the result is surprising.
- **Job done (all backends) = top-level `status`** in `completed` | `error` | `cancelled`. Steps can all be `completed` while the job is still `active` (upload, entity registration). `status_details.phase` may stay `training` with `progress_pct: 100` for a long time — keep polling. `poll_customization_job.sh` works for any job id (`automodel-…`, `unsloth-…`, or `rl-…`); it exits **1** on `error` or `cancelled`.
- Model spec fills async: **submit without polling** `nemo models get` unless submit fails.
- HF dataset id from the user → convert locally; do not ask for local paths first.
- Dataset fileset name = HF dataset **name** only (`tau/commonsense_qa` → `commonsense_qa`), not the model name.
- Prefer **CHAT** JSONL when the model has a chat template; details in `references/dataset-formats.md` (automodel auto-detects schema; unsloth needs `dataset.apply_chat_template: true` to consume `messages`).
- User asks to tune **batch or parallelism** (automodel) → `references/batch-sizing.md`. Other fields (LR, epochs, LoRA rank, distillation) → `references/hyperparameters-automodel.md`. For unsloth batch sizing see `references/batch-sizing.md`; for unsloth fields see `references/hyperparameters-unsloth.md`. Run `nemo customization <plugin> explain` for the live schema.
- Skill **defaults** (`micro_batch_size` 1, `global_batch_size` 4) are safe on unknown VRAM. When the user has **≥48 GB** on one GPU, use `references/batch-sizing.md` instead of defaults. Unsloth's analogues are `batch.per_device_train_batch_size` and `batch.gradient_accumulation_steps` (effective batch = product).
- **Unsloth training is single-GPU per job** (inside the container). `hardware.gpus` sets `CUDA_VISIBLE_DEVICES` before `import torch` — **selection, not reservation**. No `parallelism`/TP/PP block in job JSON. Multi-GPU sharding → use automodel. Pass `--profile <name>` on `unsloth submit` when the default `gpu` profile is wrong (automodel sets `training.execution_profile` in JSON instead).
- **Unsloth validation defaults** — when `dataset.validation_path` is set and `schedule.eval_steps` is omitted, the trainer runs validation once per effective epoch automatically. Report final `metrics.val_loss` from job status (see `references/reporting.md`). Set `eval_steps` explicitly to override cadence.
- **Do not use local `docker info`** to pick automodel vs unsloth. Run `nemo jobs list-execution-profiles -f json` against the user's platform (login first only if auth is enabled — see **Authentication**; see `references/troubleshooting.md`). Default output is a table — **`-f json` is required** for scripting; parse **stdout only** (do not pipe `2>&1` into `json.load`).
- **Do not merge stderr into stdout when parsing JSON** — `submit`, `explain`, and `-f json` commands write **JSON on stdout**; harmless warnings like `Configuration file not found, using defaults` go to **stderr**. Piping with **`2>&1`** before `json.load` raises `JSONDecodeError` even when submit **succeeded** — a common cause of **duplicate jobs** when the agent re-submits after a parse error. Parse stdout only; redirect stderr if needed (`2>/dev/null`). See `references/troubleshooting.md` § **Parsing CLI JSON**.
- For submit/image/plugin errors (all backends), read `references/troubleshooting.md`. Unsloth needs the `nmp-unsloth-training` container image on the **platform host's** Docker daemon (see `docker/unsloth/README.md`); rl needs the `nmp-rl-tasks` / `nmp-rl-training` images on the Kubernetes cluster (see **rl (DPO) gotchas** and `references/rl-kubernetes-runtime.md`).
- **Missing training image on a remote platform** — if the user gave a non-localhost `NMP_BASE_URL` and the job errors with `Failed to pull image`, `manifest unknown`, or missing `nmp-unsloth-training` / automodel training image: **do not** run `docker build`, `docker pull`, or `docker buildx bake` on the agent machine. Report with the template in `references/reporting.md` (use **Output adapter fileset (planned):** on error), then append on-target build steps from `references/troubleshooting.md` § **Missing training images**.
- **Gated HuggingFace models** (Llama, Gemma, …) — confirm `hf-token` + fileset `token_secret` before submit; download fails with `Failed to access upstream storage` / 502 when missing. See **HuggingFace token (gated models)** and `references/troubleshooting.md` § **Gated HuggingFace models**.
- **Post-training eval format** — use the same CHAT `messages` JSONL as training. **Do not** flatten rows to `prompt`/`expected` for the evaluator. Send `messages[:-1]` at inference (exclude final assistant label); score against `messages[-1].content`. See `references/post-training-eval.md` and `references/eval_helpers.py`.
- **LoRA adapters load automatically for eval** — when a LoRA job completes (`save_method: lora`), the adapter is registered on the base model entity and hot-reloaded on any **READY** deployment with `lora_enabled: true`. **Do not** create or update deployments before LoRA eval. **Full SFT** (`finetuning_type: all_weights`) and **merged checkpoints** (`merged_16bit` / `merged_4bit`) register a new **model** entity at `output.name` — **deploy that entity for inference** before chat or eval; full weights are not hot-reloaded onto the base deployment. For LoRA eval, route through the **provider** gateway (`/provider/<name>/-/v1` with `model: default--<adapter>`); the model-entity path (`/model/<entity>/-/v1`) always hits the base model. See `references/post-training-eval.md` § **Request routing (base vs LoRA)**.

### rl (DPO) gotchas

- **rl is DPO, not SFT** — it trains on **preference pairs** `{prompt, chosen, rejected}`, full-weight (no LoRA/adapter; `finetuning_type` is not user-set). Don't route SFT/LoRA work here, and don't route DPO to automodel/unsloth.
- **One preference fileset, two files** — `dataset` is a **single string** ref to a fileset that holds **both** `training.jsonl` and `validation.jsonl` (uploaded with `--remote-path`). Unlike automodel (`dataset.training`/`dataset.validation`) and unsloth (`dataset.path`/`validation_path`), there is no separate validation ref. See `references/dataset-formats.md` § NeMo-RL.
- **String refs** — `model` and `dataset` are plain strings (`"workspace/name"`), not objects. The training method goes under `training` with `type: "dpo"`.
- **Kubernetes job backend, not Docker** — rl steps run as Kubernetes pods via the `kubernetes_job` backend; the docker job backend cannot run rl. `rl submit` fails fast on a docker-runtime platform. The target cluster must have the **job-step images** (`nmp-rl-tasks`, `nmp-rl-training`), the **jobs-launcher** image (the per-step init container), and a **job-storage PVC**. Verify the platform with `nemo jobs list-execution-profiles -f json` (expect `backend: kubernetes_job`); to configure one, see `references/rl-kubernetes-runtime.md`. Multi-node (`parallelism.num_nodes > 1`) also needs the platform-side `NMP_RL_MULTINODE_SHARED_STORAGE_PATH` (shared FS for Ray coordination) or compile fails fast.
- **Job id prefix is `rl-<hex>`** and the platform auto-generates it — `rl submit` has **no `--name` flag** (the job JSON `name` is the *output* name, not the job id). Derive the job id from `nemo jobs list` (newest `rl-*`) for polling; `poll_customization_job.sh rl-<id>` works.
- **DPO main knob is `ref_policy_kl_penalty`** (β). For OOM, enable `activation_checkpointing: true` first. Full DPO field reference: `references/hyperparameters-rl.md`.
- **`max_steps` + `epochs`** — same caveat as the other backends: `max_steps` caps mid-epoch; it's in the smoke fixture (`plugins/nemo-rl/tests/fixtures/minimal_dpo.json`) — omit for real runs.

## Workflow

Common steps then **branch by plugin pick**:

```text
- [ ] Resolve CLI (Pre-flight — CLI resolution); cd nemo-platform
- [ ] export NMP_BASE_URL (if user provided endpoint); note whether base URL is user-overridden
- [ ] nemo auth status — skip login if auth disabled; if auth enabled and unsigned JWT allowed, `nemo auth login --unsigned-token --email <…>`; if OIDC, `nemo auth login`
- [ ] nemo jobs list-execution-profiles -f json — apply Plugin pick rules above (retry login on 401/403)
- [ ] On connection error: default URL → ask to start platform (see Platform unreachable); custom URL → report unreachable and stop
- [ ] Convert HF dataset → /tmp/train-data/*.jsonl (see references/hf-conversion.md)
- [ ] Create dataset fileset (--exist-ok), upload train.jsonl (+ validation.jsonl), nemo files list to verify
- [ ] Gated HF base model? → confirm `hf-token` exists; ask user and stop if missing (see HuggingFace token + troubleshooting § Gated HuggingFace models)
- [ ] Create HF weights fileset + model entity if missing (--exist-ok; gated repos need `token_secret` on fileset — see troubleshooting)

# automodel branch (submit → Docker GPU job)
- [ ] Write /tmp/job.json (batch sizing for ≥48 GB GPU; else Defaults table)
- [ ] nemo customization automodel submit /tmp/job.json --workspace default
- [ ] Poll until top-level terminal (`poll_customization_job.sh`; default 15s interval, or 30–60s manual polls)
- [ ] Report using the template in `references/reporting.md`
- [ ] Optional: compare base vs adapter on validation — `references/eval_helpers.py …` (LoRA only; CHAT format; adapters hot-reload automatically; see `references/post-training-eval.md`)

# unsloth branch (submit → Docker GPU job)
- [ ] Write /tmp/job.json using the UnslothJobInput shape (see Fast path — unsloth)
- [ ] nemo customization unsloth submit /tmp/job.json --workspace default [--profile <gpu-profile>]
- [ ] Poll until top-level terminal (`poll_customization_job.sh unsloth-<job-id>`; default 15s interval)
- [ ] Report using the template in `references/reporting.md`
- [ ] Optional: compare base vs adapter on validation — `references/eval_helpers.py …` (LoRA only; CHAT format; adapters hot-reload automatically; see `references/post-training-eval.md`)

# rl branch (DPO; submit → Kubernetes/Ray job) — requires platform.runtime: kubernetes
- [ ] Verify execution backend: `nemo jobs list-execution-profiles -f json` shows cpu/gpu at `backend: kubernetes_job` (NOT docker/subprocess). If not → stop; do not start a docker platform; configure per references/rl-kubernetes-runtime.md
- [ ] Dataset is PREFERENCE data: upload training.jsonl + validation.jsonl ({prompt,chosen,rejected}) to ONE fileset
- [ ] Write /tmp/job.json using the RlJobInput shape (see Fast path — rl (DPO))
- [ ] nemo customization rl submit /tmp/job.json --workspace default [--profile <gpu-profile>]
- [ ] Derive job id (newest rl-* from `nemo jobs list` — submit has no --name flag)
- [ ] Poll until top-level terminal (`poll_customization_job.sh rl-<job-id>`; default 15s interval)
- [ ] Report using the template in `references/reporting.md`
```

## Fast path — automodel

Substitute `<hf-repo>`, `<hf-dataset>`, `<model-entity>`, `<weights-fileset>`, `<dataset-fileset>`, `<output-name>`.

**Setup**

```bash
export NMP_BASE_URL=http://127.0.0.1:8080   # user override only
cd /path/to/nemo-platform
nemo auth status   # skip login if auth disabled; if enabled + unsigned JWT allowed → login --unsigned-token --email admin@example.com
nemo jobs list-execution-profiles -f json   # platform GPU profiles → automodel; set training.execution_profile if needed
```

**1. Dataset** — convert per `references/hf-conversion.md`, then:

```bash
DATASET=<dataset-fileset>   # e.g. commonsense_qa
nemo files filesets create "$DATASET" --workspace default --purpose dataset --exist-ok
nemo files upload /tmp/train-data/train.jsonl "$DATASET" --workspace default --remote-path train.jsonl
# validation.jsonl if present
nemo files list "$DATASET" --workspace default
```

**2. Model** — skip if entity exists (`nemo models list --workspace default`). For **gated** HF repos, complete **HuggingFace token (gated models)** first — see `references/troubleshooting.md` § **Gated HuggingFace models** for `token_secret` on the fileset.

```bash
WEIGHTS=<weights-fileset>   # e.g. qwen3-1.7b
MODEL_ENTITY=<model-entity>   # Models API entity (not dataset fileset, not HF id)
HF_REPO=<hf-repo>           # e.g. Qwen/Qwen3-1.7B

nemo files filesets create "$WEIGHTS" --workspace default --purpose model --exist-ok \
  --storage '{"type":"huggingface","repo_id":"'"$HF_REPO"'","repo_type":"model","revision":"main"}'

nemo models create "$MODEL_ENTITY" --workspace default --exist-ok \
  --input-data '{"name":"'"$MODEL_ENTITY"'","fileset":"default/'"$WEIGHTS"'","custom_fields":{"hf_model_id":"'"$HF_REPO"'"}}'
```

For gated repos, add `"token_secret":"hf-token"` to the `--storage` JSON (after creating the secret). See troubleshooting § **Gated HuggingFace models**.

**3. Job JSON** — write `/tmp/job.json`. `model` is the **registered model entity** (`default/<model-entity>`), not an HF repo id or dataset fileset. Full hyperparameter reference: `references/hyperparameters-automodel.md`.

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
nemo customization automodel submit /tmp/job.json --workspace default
bash plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/scripts/poll_customization_job.sh automodel-<job-id>
```

Read `<job-id>` from the `"name"` field in submit stdout (JSON). **Do not use `2>&1`** before `json.load` — warnings on stderr break parsing; see Gotchas. Optional interval override: append seconds (e.g. `… 30`). Or poll manually: `nemo jobs get-status automodel-<job-id>` every 30–60s.

## Fast path — unsloth

Same substitutions as automodel. Steps 1 (dataset) and 2 (model entity) are identical — the differences are the job JSON shape (`UnslothJobInput`) and the `unsloth submit` command.

**1. Dataset** — same as automodel Fast path step 1.

**2. Model** — same as automodel Fast path step 2.

**3. Job JSON** — write `/tmp/job.json` using the **`UnslothJobInput`** shape (see `references/hyperparameters-unsloth.md`). `model` is an **object** (not a string), `dataset.path` is a single fileset ref, `hardware.gpus` replaces the `parallelism` block (single GPU in the training container). `nemo customization unsloth explain` prints the live schema.

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
nemo customization unsloth submit /tmp/job.json --workspace default
bash plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/scripts/poll_customization_job.sh unsloth-<job-id>
```

Read `<job-id>` from the `"name"` field in submit stdout (JSON). **Do not use `2>&1`** before `json.load` — warnings on stderr break parsing; see Gotchas. Optional interval override: append seconds (e.g. `… 30`). Or poll manually: `nemo jobs get-status unsloth-<job-id>` every 30–60s. If submit fails on an unknown profile, re-list execution profiles and pass `--profile <name>` on submit (default is `gpu`).

If you try `nemo customization unsloth run …`, the CLI hard-fails with a pointer to `submit`.

## Fast path — rl (DPO)

DPO on a Ray cluster — **Kubernetes runtime only**, full-weight. **Before anything else**, confirm the platform dispatches jobs to Kubernetes: `nemo jobs list-execution-profiles -f json` must show `cpu`/`gpu` at `backend: kubernetes_job` (not `docker`/`subprocess`). If it doesn't, stop — do not start/use a docker-runtime platform; configure a Kubernetes-runtime one per `references/rl-kubernetes-runtime.md`. Model-entity setup (step 2) is identical to automodel; the dataset is **preference data** and the job JSON is the `RlJobInput` shape.

**1. Preference dataset** — rows are `{prompt, chosen, rejected}` (see `references/dataset-formats.md` § NeMo-RL). Upload **both** files to **one** fileset:

```bash
DATASET=<preference-fileset>   # e.g. dpo-data
nemo files filesets create "$DATASET" --workspace default --purpose dataset --exist-ok
nemo files upload /tmp/dpo-train.jsonl "$DATASET" --workspace default --remote-path training.jsonl
nemo files upload /tmp/dpo-val.jsonl   "$DATASET" --workspace default --remote-path validation.jsonl
nemo files list "$DATASET" --workspace default
```

**2. Model** — same as automodel Fast path step 2 (HF weights fileset + model entity; gated repos need `token_secret`).

**3. Job JSON** — write `/tmp/job.json`. `model` and `dataset` are **strings**; the method is under `training` with `type: "dpo"`. Full field reference: `references/hyperparameters-rl.md`.

```json
{
  "model": "default/<model-entity>",
  "dataset": "default/<preference-fileset>",
  "training": {
    "type": "dpo",
    "epochs": 1,
    "learning_rate": 5e-6,
    "max_seq_length": 1024,
    "batch_size": 32,
    "micro_batch_size": 1,
    "ref_policy_kl_penalty": 0.05,
    "parallelism": { "num_nodes": 1, "num_gpus_per_node": 1 }
  },
  "output": { "name": "<output-name>" }
}
```

**4. Submit and poll** — `rl submit` has **no `--name` flag** (the platform auto-generates the `rl-<hex>` job id), so derive it after submit:

```bash
nemo customization rl submit /tmp/job.json --workspace default   # add --profile <name> if the default gpu profile is wrong
JOB=$(nemo jobs list -f json | python3 -c "import sys,json;d=json.load(sys.stdin);items=d.get('data',d) if isinstance(d,dict) else d;rl=[j for j in items if str(j.get('name','')).startswith('rl-')];rl.sort(key=lambda j:j.get('created_at',''),reverse=True);print(rl[0]['name'] if rl else '')")
bash plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/scripts/poll_customization_job.sh "$JOB"
```

**Do not use `2>&1`** before `json.load` — warnings on stderr break parsing; see Gotchas. Or poll manually: `nemo jobs get-status rl-<job-id>` every 30–60s. If submit fails on an unknown profile, re-list execution profiles and pass `--profile <name>`. `nemo customization rl run …` is disabled (no local execution — it provisions a Ray cluster); `nemo customization rl explain` prints the live schema.

## Defaults

Shared:

| Field | Value |
|-------|-------|
| Workspace | `default` |
| Plugin | `automodel` (override per **Plugin pick**) |
| Training | SFT + LoRA, `max_seq_length` 2048 |
| Schedule | `epochs` ≥ 1; omit `max_steps` |
| Auth email (when login required) | `admin@example.com` unless user specifies |

Automodel-specific:

| Field | Value |
|-------|-------|
| Parallelism | 1 node, 1 GPU, TP=1 |
| Batch | `global_batch_size` 4, `micro_batch_size` 1 (unknown VRAM; see `references/batch-sizing.md` for ≥48 GB) |
| Optimizer | `learning_rate` 5e-5 |

Unsloth-specific:

| Field | Value |
|-------|-------|
| Hardware | `hardware.gpus` `"0"`, `hardware.precision` `bf16` (selection only, single GPU) |
| Model load | `load_in_4bit: true`, `dtype: "auto"` |
| Batch | `batch.per_device_train_batch_size` 2, `batch.gradient_accumulation_steps` 4 (effective batch 8; see `references/batch-sizing.md` for ≥48 GB ramp) |
| Optimizer | `learning_rate` 5e-5, `optim` `adamw_8bit` |
| Output | `save_method: "lora"` (adapter-only) unless user asks for merged checkpoint |
| Gradient checkpointing | `training.use_gradient_checkpointing: "unsloth"` |

rl-specific (DPO):

| Field | Value |
|-------|-------|
| Training | DPO, full-weight (`type: "dpo"`; no LoRA) |
| Model (if user gives none) | `Qwen/Qwen3-0.6B` |
| Dataset (if user gives none) | `nvidia/HelpSteer3` (preference subset; uploaded raw — see `references/dataset-formats.md` § NeMo-RL) |
| Schedule (if user gives none) | small demo run: `max_steps` 20 (completes fast, proves the pipeline). For a real run, set `epochs` and **omit** `max_steps`. |
| Parallelism | 1 node, 1 GPU (`parallelism.num_nodes`/`num_gpus_per_node`) |
| Batch | `batch_size` 32, `micro_batch_size` 1 |
| Optimizer | `learning_rate` 5e-6 (DPO uses a low LR), AdamW + cosine |
| DPO | `ref_policy_kl_penalty` (β) 0.05, `sft_loss_weight` 0.0 |
| Max sequence length | 1024 |
| Output | full-weight model entity (`output.name`); no adapter |

When the user asks for a DPO job **without specifics**, default to the above: a
20-step run of `Qwen/Qwen3-0.6B` on `nvidia/HelpSteer3` — small enough to finish
quickly and confirm the pipeline end-to-end.

## Batch sizing

`micro_batch_size` / `global_batch_size` (automodel) and `per_device_train_batch_size` × `gradient_accumulation_steps` (unsloth) on **≥48 GB GPUs**, multi-GPU (data vs tensor parallel), and OOM / throughput tuning live in **`references/batch-sizing.md`**. On unknown VRAM the **Defaults** above are safe — read batch-sizing before raising batch on a known ≥48 GB card. rl (DPO) batch knobs (`batch_size` / `micro_batch_size`) are in `references/hyperparameters-rl.md`.

## Worked example

**Automodel:** `Qwen/Qwen3-1.7B` + `tau/commonsense_qa` → CHAT JSONL, fileset `commonsense_qa`, entity `qwen3-1.7b`, output `qwen3-1.7b-commonsense-qa-lora`, `epochs: 1` (no `max_steps`). On ≥48 GB GPU use LoRA ≤4B **default**: `micro` 32, GBS 128, `learning_rate` `1e-4` (high-util: 64 / 256).

**Unsloth:** same model + dataset + entity + fileset, but `nemo customization unsloth submit /tmp/job.json -w default`. Job JSON ≤4B row: `batch.per_device_train_batch_size` 8, `batch.gradient_accumulation_steps` 16 (effective 128), `learning_rate` `1e-4`, `hardware.gpus` `"0"`, `output.save_method` `"lora"`. Poll `unsloth-<job-id>` to completion. Reference fixture: `plugins/nemo-unsloth/tests/fixtures/minimal_unsloth_sft.json` (ignore `max_steps` for real runs).

**rl (DPO):** the no-details default — `Qwen/Qwen3-0.6B` + `nvidia/HelpSteer3` (preference subset, uploaded raw), output `qwen3-0.6b-dpo`. First confirm `kubernetes_job` backend (see **Plugin pick** → rl runtime gate). Upload `training.jsonl` + `validation.jsonl` to one fileset, register the model entity, then submit a **small 20-step demo** job:

```json
{
  "model": "default/qwen3-0.6b",
  "dataset": "default/helpsteer3-dpo",
  "training": { "type": "dpo", "max_steps": 20, "batch_size": 32, "micro_batch_size": 1,
                "learning_rate": 5e-6, "max_seq_length": 1024, "ref_policy_kl_penalty": 0.05,
                "parallelism": { "num_nodes": 1, "num_gpus_per_node": 1 } },
  "output": { "name": "qwen3-0.6b-dpo" }
}
```

`nemo customization rl submit /tmp/job.json -w default`, derive the `rl-<hex>` id (submit has no `--name`), poll to completion. Reference fixture: `plugins/nemo-rl/tests/fixtures/minimal_dpo.json`. For a real run, replace `max_steps: 20` with `epochs`.

## Report to user

After polling reaches a **terminal** status (`completed`, `error`, or `cancelled`), report using the template in **`references/reporting.md`** — one format for all backends. It covers the **Fine-tune result** header, the **Training configuration** table (with per-backend examples: automodel, unsloth, rl/DPO), and **Using the adapter** (automodel/unsloth LoRA) vs **Using the fine-tuned model** (full SFT / merged / rl DPO), plus metrics extraction, notes by status, `/tmp` report saving, and error follow-ups.

## Reference files

| When | Read |
|------|------|
| HF conversion or MCQA shaping | `references/hf-conversion.md` |
| CHAT vs SFT vs CUSTOM (automodel); text vs messages (unsloth); preference triples (rl/DPO) | `references/dataset-formats.md` |
| Field glossary, full JSON template, distillation/KD, live-schema pointers (index routes per backend) | `references/hyperparameters.md` → `hyperparameters-automodel.md` / `hyperparameters-unsloth.md` / `hyperparameters-rl.md` |
| Batch sizing (≥48 GB), OOM / throughput (automodel + unsloth) | `references/batch-sizing.md` |
| Multi-GPU same node | `references/batch-sizing.md` § **Multi-GPU (same node)** (unsloth is single-GPU) |
| Reporting: result template, Training configuration, Using the adapter / fine-tuned model | `references/reporting.md` |
| Backend choice, execution profiles, submit failure, container images, missing image on remote platform, gated HF auth / download 502, CLI, connection errors | `references/troubleshooting.md` (§ **Parsing CLI JSON** for `2>&1` / `json.load`; § **Gated HuggingFace models** for `hf-token`) |
| rl (DPO) needs Kubernetes job execution — verifying / configuring `runtime: kubernetes` + `kubernetes_job` executors (local platform → remote cluster, launcher image, PVC, loopback) | `references/rl-kubernetes-runtime.md` |
| Live JSON schema | `uv run nemo customization automodel explain` / `uv run nemo customization unsloth explain` / `uv run nemo customization rl explain` |
| Job JSON fixture (automodel, minimal) | `plugins/nemo-automodel/tests/fixtures/qwen3_0.6b_sft_lora.json` (ignore `max_steps` for real runs) |
| Job JSON fixture (unsloth, minimal) | `plugins/nemo-unsloth/tests/fixtures/minimal_unsloth_sft.json` (ignore `max_steps` for real runs) |
| Job JSON fixture (rl / DPO, minimal) | `plugins/nemo-rl/tests/fixtures/minimal_dpo.json` (ignore `max_steps` for real runs) |
| Job JSON fixture — integrations (W&B / MLflow) | automodel: `plugins/nemo-automodel/tests/fixtures/integrations_wandb_mlflow.json` · unsloth: `plugins/nemo-unsloth/tests/fixtures/integrations_wandb_mlflow.json` · rl: `plugins/nemo-rl/tests/fixtures/integrations_wandb_mlflow.json` |
| Automodel compile-path contract configs | `services/automodel/tests/contract/input_configs/` → YAML in `output_configs/` (legacy `TrainingStepConfig` shape, not submit JSON) |
| W&B / MLflow field reference (all backends) | `references/hyperparameters.md` § **Integrations (all backends)** |
| W&B secret + MLflow local server + jobs-launcher | `references/integrations-setup.md` |
| Gated HF model auth (`hf-token`, fileset `token_secret`) | `references/troubleshooting.md` § **Gated HuggingFace models** |
| Post-training eval (base vs LoRA, CHAT format parity) | `references/post-training-eval.md`, `references/eval_helpers.py` |

Related: `plugins/nemo-automodel/README.md`, `plugins/nemo-unsloth/README.md`, `plugins/nemo-rl/README.md`, `docs/customizer/nemo-rl-dpo-plugin-design.md`, `plugins/nemo-customizer/docs/CUSTOMIZATION.md`, skills **`nemo-files`**, **`nemo-status`**, **`nemo-secrets`**.
