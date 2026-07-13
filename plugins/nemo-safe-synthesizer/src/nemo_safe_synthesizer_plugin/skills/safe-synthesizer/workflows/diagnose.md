# Diagnosing Safe Synthesizer

## Prerequisites

- NeMo CLI access through `nemo` or repo development invocation `uv run nemo`.
- Python dependencies synced into the active virtual environment.
- A GPU-capable Jobs backend for platform container jobs, or a compatible CUDA-capable GPU and driver for host-local generation.
- Files API URL access when the run uses filesets or model fileset setup.
- Workspace access to the input fileset, output job, `hf_token_secret`, and any PII classification provider.

## First Checks

1. Resolve the CLI with `command -v nemo 2>/dev/null || (test -x .venv/bin/nemo && realpath .venv/bin/nemo) || echo CLI_NOT_FOUND`.
2. Confirm whether the user is running a platform container job through the Jobs API or SDK, or host-local (`nemo safe-synthesizer run-local`).
3. Inspect the spec file before changing commands.

## Common Failures

### CLI command not found

Tell the user that the NeMo CLI or the Safe Synthesizer plugin is not installed in this environment. In this repo, development runs usually use `uv run nemo ...` after dependencies are synced.

### CUDA or GPU initialization fails

- For platform jobs, confirm the job executor profile targets GPU-capable workers.
- Confirm the host has a compatible NVIDIA GPU and driver with `nvidia-smi`.
- For repo development, verify the plugin runtime with `uv run nemo safe-synthesizer runtime info`.
- Recreate the runtime with `uv run nemo safe-synthesizer runtime setup --force` if the engine/CUDA packages are missing or stale.
- Host-local Safe Synthesizer training runs directly on the host GPU; a GPU inside another service container is not enough.

### Container image cannot be pulled or is the wrong tag

- Confirm platform jobs are using container mode: `NEMO_SAFE_SYNTHESIZER_JOB_MODE=container`.
- For released images, verify `NMP_IMAGE_REGISTRY=nvcr.io/nvidia/nemo-platform`, `NMP_IMAGE_TAG=<tag>`, and `NEMO_SAFE_SYNTHESIZER_CONTAINER_IMAGE=safe-synthesizer-tasks`.
- For local Docker executor testing, verify `NEMO_SAFE_SYNTHESIZER_CONTAINER_IMAGE_REF=safe-synthesizer-tasks:local` and that `docker image inspect safe-synthesizer-tasks:local` succeeds.
- For Kubernetes, push the image to a registry the cluster can pull and set `NEMO_SAFE_SYNTHESIZER_CONTAINER_IMAGE_REF` to that full pushed image reference.
- If the pull fails from `nvcr.io`, confirm NGC credentials or image pull secrets are configured for the Jobs backend.

### Data source cannot be loaded

- For platform jobs, verify `data_source` is a fileset URL: `<workspace>/<fileset>#<path>`.
- Confirm the fileset exists and the workspace is correct.
- For local runs, prefer `--data-source <local-file-or-dir>` when the input is on disk.
- Supported local file forms include CSV, Parquet, JSON, JSONL, and Hugging Face datasets paths.

### Model or fileset downloads fail

Run the model fileset setup when local tasks need model filesets:

```bash
uv run python plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py --files-api-url http://localhost:8080
```

Then confirm the Files API URL is reachable and the target workspace contains the expected filesets.

### PII classification provider fails

- Check `config.replace_pii.globals.classify.classify_model_provider`.
- The plugin requires `<workspace>/<provider_name>`, not just the provider name.
- Verify the provider exists with `nemo inference providers list --workspace <workspace>`.

### Job remains pending or results are missing

- Check the platform job status with the Jobs API or SDK.
- If the submission path supports waiting, retry creation with its documented wait or polling option.
- Inspect job result names from the artifacts workflow.

## Source Files for Development Debugging

Only inspect these when the user asks to change or debug plugin code:

- `plugins/nemo-safe-synthesizer/src/nemo_safe_synthesizer_plugin/cli.py`
- `plugins/nemo-safe-synthesizer/src/nemo_safe_synthesizer_plugin/api/v2/jobs/endpoints.py`
- `plugins/nemo-safe-synthesizer/src/nemo_safe_synthesizer_plugin/tasks/safe_synthesizer/__main__.py`

## Next Steps

- Re-run with the command shape in `workflows/run.md`.
- Recreate model filesets with `plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py`.
- Check platform job status with the Jobs API or SDK.
- Retrieve result names with `workflows/results.md`, then inspect `summary` or `summary.json` first.
