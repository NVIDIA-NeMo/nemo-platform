# nmp-unsloth container image

Single image — `nmp-unsloth-training` — used for all four steps of an
Unsloth customization job (file_io download, training, file_io upload,
model_entity).

| Image | Dockerfile | Role |
|-------|------------|------|
| `nmp-unsloth-training` | `Dockerfile.nmp-unsloth-training` | NGC PyTorch base + Unsloth ML stack + platform glue. ENTRYPOINT is `/opt/venv/bin/python`. |

Bake file: **`docker-bake.hcl`** at the Platform repo root (`context = "."`). Run all commands from the Platform repo root.

Tags use the same bake variables as automodel (`IMAGE_REGISTRY`, `BAKE_TAG`; defaults in `docker-bake.hcl`):

- Default: `${IMAGE_REGISTRY}/nmp-unsloth-training:${BAKE_TAG}` (e.g. `…/nmp-unsloth-training:local` with `--load`)

Future-proofing: a leaner CPU image (`nmp-unsloth-tasks`) can be added
later for the file_io / model_entity steps. The compiler already routes
those steps through `get_tasks_image()`, which falls back to the training
image when `NMP_UNSLOTH_TASKS_IMAGE` is not set.

---

## Build & push (from Platform repo root)

```bash
cd /path/to/Platform

# --- Option A: local build (loads into the local daemon, no registry needed) ---
docker buildx bake \
  -f docker-bake.hcl \
  nmp-unsloth-training \
  --load \
  --set "*.platform=linux/amd64"
# Result: `${IMAGE_REGISTRY}/nmp-unsloth-training:${BAKE_TAG}` in `docker images`.

# --- Option B: push to a registry ---
docker login nvcr.io
export IMAGE_REGISTRY="my-registry/nemo-platform-dev"
export BAKE_TAG="$(git rev-parse --short HEAD)"
docker buildx bake \
  -f docker-bake.hcl \
  nmp-unsloth-training \
  --push \
  --set "*.platform=linux/amd64"
# Result: `${IMAGE_REGISTRY}/nmp-unsloth-training:${BAKE_TAG}` in the registry.
```

The build pulls the NGC PyTorch base, then runs unsloth's canonical install
in two steps:

1. `uv pip install unsloth --torch-backend=auto` — this is the command
   straight from unsloth's README. It pulls `unsloth`, `unsloth_zoo`, and the
   full HF stack (transformers, trl, peft, accelerate, datasets, bitsandbytes,
   xformers) at versions tested upstream — we deliberately don't pin any of
   them on our end, because unsloth's pyproject already has precise
   `!=X.Y.Z` blocklists for known-broken releases.
1b. Flash Attention 2 (Dockerfile step 1b) — source build with
    `--no-build-isolation` against the NGC base torch (cached Docker layer).
    Parallelism is capped via `MAX_JOBS` (default `2`, override with bake arg
    `FLASH_ATTN_MAX_JOBS`) and `NVCC_THREADS=1` to avoid OOM during nvcc.
    Unsloth does not depend on `flash-attn`; without it you may see
    `FA2 = False` and `Xformers = None` on newer CUDA stacks.
2. Editable install of the platform glue: `nemo-platform-sdk`,
   `nemo-platform-plugin`, `nmp-common`, `nmp-unsloth`.

We considered using the official `unsloth/unsloth` image as a base. We
didn't because it's 13 GB, bundles Jupyter Lab + SSH + Unsloth Studio
(which we don't need for a non-interactive job runner), and we'd still
need to layer the platform glue on top. Building on NGC PyTorch keeps
the image smaller and the entrypoint/user-config under our control.

---

## Local smoke test (no platform, no GPU)

```bash
# Use the same tag the bake produced. For local builds that's the bare name.
IMAGE=nmp-unsloth-training:local

# CMD prints the training help banner — proves entrypoint + the ML stack import cleanly.
docker run --rm "$IMAGE"

# Extra args replace CMD; include `-m nmp.unsloth.tasks.training` or you get plain `python --help`.
docker run --rm "$IMAGE" \
  -c "import unsloth, trl, peft, bitsandbytes; print('ok')"
```

---

## GPU pod runbook — end-to-end

The same runbook works whether the GPU pod is a developer's interactive
node, a CI cluster runner, or a customer's air-gapped lab.

### 0. Prereqs on the host

- NVIDIA driver compatible with the NGC PyTorch base (CUDA 13.1 at the
  time of writing; check `Dockerfile.nmp-automodel-base` for the latest
  pin if unsure).
- `nvidia-container-toolkit` installed so Docker can mount GPUs.
- Network access to your image registry (`nvcr.io` by default).
- A running NeMo Platform install (`make bootstrap` + `nemo services run`)
  with `platform.runtime: docker` configured. See top-level `AGENTS.md` for setup.

### 1. Build the image

From the Platform repo root, on a machine with Docker buildx.

Pick **one** of the following depending on where the GPU host will pull from:

**A) Same host builds and runs the platform** (e.g. the DinD GPU pod under
`services/unsloth/scripts/gpu-test/`). The bare local tag is enough:

```bash
docker buildx bake \
  -f docker-bake.hcl \
  nmp-unsloth-training \
  --load \
  --set "*.platform=linux/amd64"
# → nmp-unsloth-training:local in the local daemon.
```

**B) Push to a registry the GPU host will pull from**:

```bash
export IMAGE_REGISTRY="my-registry/nemo-platform-dev"
export BAKE_TAG="$(git rev-parse --short HEAD)"

docker buildx bake \
  -f docker-bake.hcl \
  nmp-unsloth-training \
  --push \
  --set "*.platform=linux/amd64"
# → ${IMAGE_REGISTRY}/nmp-unsloth-training:${BAKE_TAG} in the registry.
```

**C) Air-gapped GPU host** (save + `scp` + `docker load`):

```bash
export IMAGE_REGISTRY="my-registry/nemo-platform-dev"
export BAKE_TAG="$(git rev-parse --short HEAD)"
docker buildx build \
  -f docker/Dockerfile.nmp-unsloth-training \
  --output type=docker,dest=/tmp/nmp-unsloth-training.tar \
  --target runtime \
  -t "${IMAGE_REGISTRY}/nmp-unsloth-training:${BAKE_TAG}" \
  --build-context "platform-workspace=path-to-platform-workspace" \
  .

scp /tmp/nmp-unsloth-training.tar gpu-pod:/tmp/
ssh gpu-pod docker load -i /tmp/nmp-unsloth-training.tar
```

### 2. Point the platform at your tag

On the host running `nemo services run`, set the full image ref. For a local
build this is just the bare name:

```bash
# Local bake (--load; matches docker-bake.hcl defaults):
export NMP_UNSLOTH_TRAINING_IMAGE="${IMAGE_REGISTRY:-my-registry/nemo-platform-dev}/nmp-unsloth-training:${BAKE_TAG:-local}"

# Or, when you pushed (Option B above):
export NMP_UNSLOTH_TRAINING_IMAGE="${IMAGE_REGISTRY}/nmp-unsloth-training:${BAKE_TAG}"

# Restart so the env var takes effect.
nemo services restart
```

Or persist in `~/.nemo/config.yaml`:

```yaml
unsloth:
  training_image: my-registry/nemo-platform-dev/nmp-unsloth-training:local
```

### 3. Prepare model + dataset filesets

```bash
# 0.5B Qwen — fast enough for a smoke test on a single GPU.
nemo files filesets create base-qwen-05b -w default
# Push your model weights (or use an existing entity that already points at a fileset).
nemo files upload <path-to-qwen-checkpoint> --fileset default/base-qwen-05b -w default

nemo models create base-qwen-05b \
  -w default \
  --fileset default/base-qwen-05b \
  --finetuning_type all_weights

# Tiny chat dataset.
nemo files filesets create unsloth-smoke-dataset -w default
nemo files upload ./smoke-dataset.jsonl --fileset default/unsloth-smoke-dataset -w default
```

### 4. Write a smoke job

Save as `unsloth-smoke.json`:

```json
{
  "name": "qwen-unsloth-smoke",
  "model": {
    "name": "default/base-qwen-05b",
    "max_seq_length": 1024,
    "load_in_4bit": true,
    "dtype": "auto"
  },
  "dataset": {
    "path": "default/unsloth-smoke-dataset",
    "text_field": "text"
  },
  "training": {
    "finetuning_type": "lora",
    "lora": {"rank": 16, "alpha": 16}
  },
  "schedule": {
    "max_steps": 20,
    "warmup_steps": 2,
    "lr_scheduler_type": "linear",
    "logging_steps": 1
  },
  "batch": {
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 4
  },
  "optimizer": {
    "learning_rate": 2e-4,
    "optim": "adamw_8bit"
  },
  "hardware": {
    "gpus": "0",
    "precision": "bf16"
  },
  "output": {
    "name": "qwen-unsloth-smoke-out",
    "save_method": "lora"
  }
}
```

### 5. Submit and watch

```bash
# Sanity-check schema + planned compilation locally.
nemo customization unsloth explain
cat unsloth-smoke.json | jq .

# Submit. Captures the job id from the JSON response.
JOB_ID=$(
  nemo customization unsloth submit unsloth-smoke.json -w default --json \
    | jq -r '.id'
)
echo "Submitted: $JOB_ID"

# Tail the status — should go PENDING → ACTIVE → COMPLETED across the four steps.
nemo jobs status "$JOB_ID" -w default

# Stream logs from each step.
nemo jobs logs "$JOB_ID" -w default --step model-and-dataset-download --follow
nemo jobs logs "$JOB_ID" -w default --step training --follow
nemo jobs logs "$JOB_ID" -w default --step model-upload --follow
nemo jobs logs "$JOB_ID" -w default --step model-entity-creation --follow

# Verify the output entity (adapter, since save_method=lora).
nemo models adapters list -w default --model_name base-qwen-05b
nemo models adapters retrieve qwen-unsloth-smoke-out \
  --model_name base-qwen-05b -w default
```

### 6. Common gotchas

| Symptom | Fix |
|---|---|
| `compile()` errors with "platform.runtime: docker" | Set `platform.runtime: docker` in `~/.nemo/config.yaml` and restart services. |
| `compile()` errors with "Docker daemon unreachable" | Confirm `docker info` works as the user running `nemo services`. |
| First job step errors with `Model 'X' has no fileset attached` | Attach a fileset to the model entity (`nemo models update --fileset ...`). |
| `training` step errors with `bitsandbytes`/CUDA mismatch | Rebuild the image — the base NGC PyTorch tag may have moved. |
| `training` step OOMs on a small GPU | Reduce `model.max_seq_length` and / or set `model.load_in_4bit: true`. |
| `model-entity-creation` errors with "Adapter already exists" | Pick a fresh `output.name` (the unsloth compiler is "always create"; no overwrite). |
| Step config not picked up (`NEMO_JOB_STEP_CONFIG_FILE_PATH is not set`) | The container was started outside the Jobs runner — only platform-driven submit populates this. |

### 7. Cleanup

```bash
# Remove the smoke adapter + fileset.
nemo models adapters delete qwen-unsloth-smoke-out --model_name base-qwen-05b -w default
nemo files filesets delete qwen-unsloth-smoke-out -w default
```

---

## Architecture notes

- **Step layout** mirrors `docker/automodel/`. The compiler in
  `nmp.unsloth.app.jobs.compiler` emits the same 4-step
  `PlatformJobSpec` shape automodel emits; the only difference is the
  image and the training entrypoint module.
- **`nemo_automodel` is intentionally not in this image** — unsloth is a
  separate ML stack. If you need both backends on the same cluster, run
  both images side by side; jobs from each backend route to their own
  `nmp-{backend}-training` image via env-var overrides.
- **Why we don't pin transformers / trl / peft / bitsandbytes** — unsloth's
  own pyproject already constrains them tightly (e.g.
  `transformers>=4.51.3,!=4.52.0..3,!=4.53.0,!=4.54.0,!=4.55.0..1,!=4.57.0,
  !=4.57.4..5,!=5.0.0,!=5.1.0,<=5.5.0`). Our `[unsloth]` extra in
  `services/unsloth/pyproject.toml` is just `["unsloth[huggingface]"]` —
  delegating everything to upstream so we don't ship our own subtly-wrong
  constraints.
- **No CUDA wheels are pre-built** — `bitsandbytes` ships PyPI wheels
  (Ampere+; for older arches, swap to a source build or pin a compatible
  release).
