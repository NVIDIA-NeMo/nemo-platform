# nmp-automodel container images

Three images for the **nmp-automodel** customization backend. Published as flat repo names under **`my-registry/nemo-platform-dev/nmp-automodel-*`** (no nested `nmp/...` path — some registries reject that on push).

| Image | Dockerfile | Role |
|-------|------------|------|
| `nmp-automodel-base` | `Dockerfile.nmp-automodel-base` | PyTorch 26.05 + Automodel + `mamba-ssm` / `causal-conv1d` wheels |
| `nmp-automodel-tasks` | `Dockerfile.nmp-automodel-tasks` | Platform task glue (`file_io`, `model_entity`, `model_spec`); GPU-capable base |
| `nmp-automodel-training` | `Dockerfile.nmp-automodel-training` | Training step (`nmp.automodel.tasks.training`) |

Full references (default tag `local`):

- `my-registry/nemo-platform-dev/nmp-automodel-base:local`
- `my-registry/nemo-platform-dev/nmp-automodel-tasks:local`
- `my-registry/nemo-platform-dev/nmp-automodel-training:local`

Bake file: **`docker-bake.hcl`** at the Platform repo root (`context = "."`). Run all commands from the Platform repo root.

## `docker buildx bake --print`

`--print` only parses the HCL and prints JSON. A **0.0s FINISHED** result is normal — no image is built. Use it to verify targets, tags, and platforms before a real build.

## Prerequisites

1. **CUDA extension wheels** (`causal-conv1d-wheel`, `mamba-ssm-wheel`) - built from this directory or pulled from NGC. The wheel Dockerfile and uv locks live under `docker/locks/` (ported from `nmp`).

2. **Base image tag** - after building the base, set `BASE_TAG_AUTOMODEL` (or push to `BASE_REGISTRY`) before building tasks/training.

## Build wheels and push to NGC (from Platform root)

```bash
cd /path/to/Platform

docker login nvcr.io

export WHEELS_TAG="$(git rev-parse --short HEAD)"
# Bake variables (WHEELS_REGISTRY, WHEELS_TAG, IMAGE_REGISTRY) are overridden via env, not --set.
# Example:
#   export WHEELS_REGISTRY=my-registry/nemo-platform-dev
#   export IMAGE_REGISTRY=my-registry/nemo-platform-dev

docker buildx bake --print -f docker-bake.hcl nmp-automodel-gpu-wheels

docker buildx bake \
  -f docker-bake.hcl \
  nmp-automodel-gpu-wheels \
  --push \
  --set "*.platform=linux/amd64"
```

Override platform: `export BUILD_PLATFORM=linux/amd64` or `--set "*.platform=linux/amd64"`.

## Build automodel images (from Platform root)

```bash
cd /path/to/Platform

export WHEELS_TAG="${WHEELS_TAG:-3fd6986ff173b598446ffac06d9be3f84b482495}"
export BAKE_TAG="${WHEELS_TAG}"

docker buildx bake \
  -f docker-bake.hcl \
  nmp-automodel-base-builder \
  --push \
  --set "*.platform=linux/amd64"

docker buildx bake \
  -f docker-bake.hcl \
  nmp-automodel \
  --push \
  --set "*.platform=linux/amd64"
```

To use wheels already published without rebuilding, `export WHEELS_TAG=<existing-tag>` and matching `BAKE_TAG`.

Override registry: `export WHEELS_REGISTRY=...` and `export IMAGE_REGISTRY=...` before bake.

## Tasks / training runtime (platform glue)

**Base (`nmp-automodel-base`):** NGC PyTorch 26.05, Automodel `uv sync --locked`, pinned `transformers`/`torch`.

**Automodel cherry-picks:** Platform-specific patches under `docker/automodel/cherry-picks/` are applied after `update_pyproject_pytorch.sh` and before `uv sync`. Re-pin or drop patches when upstream `r0.x.y` absorbs the same changes.

| Patch | Purpose |
|-------|---------|
| `3d98f6e3.diff` | Drop `decord` + `imageio-ffmpeg` (old bundled ffmpeg); use `torchcodec` for VLM video (`FORCE_QWENVL_VIDEO_READER=torchcodec`) |

**Tasks image:** `uv sync --package nmp-automodel --no-dev --inexact` from the minimal workspace. CPU steps only need platform SDK glue; upgrading ancillary packages here does not affect training.

**Training image:** Do **not** use `uv sync` — it upgrades `transformers` and breaks `PreTrainedModel`. Use **`uv pip install -e`** with **`--overrides no_override_requirements.txt`**, then `uv pip install --no-deps -e /opt/Automodel` to re-pin `nemo_automodel` from the base clone (not PyPI).

## Runtime

Entrypoint is `/opt/venv/bin/python`. Job steps pass `-m nmp.automodel.tasks.<module>` (see `nmp.automodel.app.jobs.compiler`). Local smoke:

```bash
# No extra args → uses image CMD (python -m nmp.automodel.tasks --help).
docker run --rm $NMP_AUTOMODEL_TASKS_IMAGE

# Extra args replace CMD; include -m nmp.automodel.tasks or you get plain `python --help`.
docker run --rm $NMP_AUTOMODEL_TASKS_IMAGE -m nmp.automodel.tasks --list
```

The job compiler resolves `nmp-automodel-tasks` and `nmp-automodel-training` under `NMP_AUTOMODEL_IMAGE_REGISTRY` (default `my-registry/nemo-platform-dev`). See `nmp.automodel.images`.
