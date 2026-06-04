<!-- @nemo-nb: process -->
<!-- @nemo-nb: skip-test -->
<a id="host-local-development"></a>
# Host-Local Development and Testing

Run {{nss_short_name}} on your machine's GPU with `nemo safe-synthesizer run-local`. This page covers the plugin CLI only (`run-local` and `runtime`). It does not cover platform job submission or `nemo safe-synthesizer jobs …` commands (not exposed in the CLI today).

## Prerequisites

- CUDA-capable NVIDIA GPU on the host (80GB+ VRAM recommended; check with `nvidia-smi`). See [Getting Started](../getting-started.md).
- NeMo Platform repository checkout with the Safe Synthesizer plugin installed.
- **No running platform required** for a typical local run when you pass `--data-source` — the NSS runtime can download base models from Hugging Face directly.

```bash
# From the NeMo Platform repository root
BOOTSTRAP_LOCAL_PLUGIN_DIRS=plugins/nemo-safe-synthesizer make bootstrap-python
uv run nemo safe-synthesizer runtime setup
uv run nemo safe-synthesizer runtime info
```

Confirm the CLI surface:

```bash
uv run nemo safe-synthesizer --help
# Commands: run-local, runtime
```

## Run a job locally

Use a job spec JSON (example in `plugins/nemo-safe-synthesizer/src/nemo_safe_synthesizer_plugin/nss-job.json`) and a local input file:

```bash
uv run nemo safe-synthesizer run-local \
  --workspace default \
  --spec-file ./nss-job.json \
  --data-source ./input.csv \
  --output-dir ./nss-output
```

| Flag | Role |
|------|------|
| `--spec-file` | Job spec JSON (`data_source`, `config`, …) |
| `--data-source` | Local CSV (or other supported file) used **instead of** downloading from `data_source` in the spec |
| `--output-dir` | Where artifacts are written (default `./nss-output`) |
| `--workspace` | Workspace label for spec fields that reference workspaces (default `default`) |

### Output layout

| Path | Description |
|------|-------------|
| `nss-output/synthetic-data.csv` | Generated records |
| `nss-output/summary.json` | Timing and run summary |
| `nss-output/evaluation-report.html` | Present when evaluation is enabled |
| `nss-output/adapter/` | LoRA adapter directory when synthesis training ran |

## Reuse a prior adapter (generation only)

Adapter reuse always skips training and runs **generate + evaluate** only — the same path as the OSS library's `load_from_save_path().generate()`.

### Run-local

Point `config.training.pretrained_model` at a prior run's adapter directory or work tree:

**Run 1** — train and write an adapter:

```bash
uv run nemo safe-synthesizer run-local \
  --spec-file ./job1-spec.json \
  --data-source ./input.csv \
  --output-dir ./nss-output-1
```

**Run 2** — generate more records from that adapter:

```json
{
  "data_source": "default/placeholder#input.csv",
  "config": {
    "enable_synthesis": true,
    "enable_replace_pii": false,
    "training": {
      "pretrained_model": "./nss-output-1/adapter"
    },
    "generation": {
      "num_records": 100
    }
  }
}
```

The plugin resolves `./nss-output-1/adapter` to the prior run under `./nss-output-1/work`. The `work/` tree must still exist from run 1.

You can also point at `./nss-output-1/work` or a specific run directory under it.

### Platform jobs (`pretrained_model_job`)

For platform jobs, set `pretrained_model_job` to a completed job that has an **`adapter`** result stored in Files:

```json
{
  "pretrained_model_job": "my-first-synth-job",
  "config": {
    "generation": {
      "num_records": 100
    }
  }
}
```

Do not set `config.training.pretrained_model` when using `pretrained_model_job`.

Training runs embed `safe-synthesizer-config.json` in the adapter artifact uploaded to Files so subsequent generation-only jobs can reload the prior run configuration.

Use an absolute path for local `pretrained_model` if you run from a different working directory.

## Runtime commands

```bash
# One-time: create the NSS engine/CUDA venv
uv run nemo safe-synthesizer runtime setup

# Inspect configured runtime paths and Python
uv run nemo safe-synthesizer runtime info

# Recreate the venv after driver or package changes
uv run nemo safe-synthesizer runtime setup --force
```

## Automated tests

### Unit tests (no GPU)

From `plugins/nemo-safe-synthesizer`:

```bash
uv run pytest plugins/nemo-safe-synthesizer/tests/unit/test_local_run.py -v
```

### Opt-in host-local E2E (GPU)

```bash
cd /path/to/nemo-platform
RUN_NSS_LOCAL_E2E=1 uv run pytest \
  plugins/nemo-safe-synthesizer/tests/e2e/test_local_synthesis.py \
  -v -m e2e
```

Optional: `NSS_LOCAL_E2E_TIMEOUT_SECONDS` (default `3600`).

Requires `RUN_NSS_LOCAL_E2E=1`, CUDA, and `nemo safe-synthesizer runtime setup`.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `run-local` not in `nemo safe-synthesizer --help` | `BOOTSTRAP_LOCAL_PLUGIN_DIRS=plugins/nemo-safe-synthesizer make bootstrap-python`; no duplicate top-level generated `safe-synthesizer` CLI |
| `runtime setup` / CUDA errors | `uv run nemo safe-synthesizer runtime info` and `nvidia-smi` |
| Model download failures | Hugging Face access from the NSS runtime venv; network and disk space |
| Reuse run fails to load adapter | Prior run's `work/` tree still exists (run-local), or adapter artifact in Files includes `metadata_v2.json` and embedded `safe-synthesizer-config.json` (platform) |
| `Use either 'pretrained_model_job' or 'config.training.pretrained_model'` | For run-local-only workflows, use only `config.training.pretrained_model` |

## Related topics

- [Parameters Reference](reference.md) — spec and `config` fields
- [Getting Started](../getting-started.md) — GPU and platform context
- [Jobs](jobs.md) — platform job lifecycle (separate from this run-local guide)
- Plugin README: `plugins/nemo-safe-synthesizer/README.md`
