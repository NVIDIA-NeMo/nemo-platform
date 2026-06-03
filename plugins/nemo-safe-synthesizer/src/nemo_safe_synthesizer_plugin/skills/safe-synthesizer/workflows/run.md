# Running Safe Synthesizer

## Local Run Prerequisites

- A Linux host with a CUDA-capable NVIDIA GPU.
- The Safe Synthesizer plugin installed as an editable local plugin, for repo development: `BOOTSTRAP_LOCAL_PLUGIN_DIRS=plugins/nemo-safe-synthesizer make bootstrap-python`.
- The separate Safe Synthesizer runtime venv created with `uv run nemo safe-synthesizer runtime setup`.
- A job spec JSON file with `data_source` and `config`.
- A local input file or directory when using `--data-source`.

If model downloads are needed through platform filesets, run:

```bash
uv run python plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py --files-api-url http://localhost:8080
```

## Platform Job Prerequisites

- The Safe Synthesizer service and Jobs service are available.
- `data_source` points to a platform fileset path such as `default/my-fileset#input.csv`.
- If `hf_token_secret` is set, the named platform secret exists in the target workspace.
- If PII classification is enabled, the model provider exists and is referenced as `<workspace>/<provider_name>`.

## Resolve the CLI

Run `command -v nemo 2>/dev/null || (test -x .venv/bin/nemo && realpath .venv/bin/nemo) || echo CLI_NOT_FOUND`.

- If the output is a path, use that path as the command prefix.
- If the output is `CLI_NOT_FOUND`, tell the user the NeMo CLI is not available in this environment and ask whether they want help installing or syncing dependencies.

## Choose the Execution Mode

Use host-local execution when the user is iterating on a local machine with CUDA/GPU access:

```bash
uv run nemo safe-synthesizer runtime setup
uv run nemo safe-synthesizer run-local \
  --workspace default \
  --spec-file nss-job.json \
  --data-source ./input.csv \
  --output-dir ./nss-output
```

Use platform job submission when the user wants the NMP Jobs service to run Safe Synthesizer:

```bash
nemo safe-synthesizer jobs create my-safe-synthesizer-job \
  --workspace default \
  --input-file platform-job.json \
  --wait
```

## Minimal Spec Shape

```json
{
  "data_source": "default/my-input#input.csv",
  "config": {
    "enable_synthesis": true,
    "enable_replace_pii": false,
    "generation": {
      "num_records": 100
    },
    "evaluation": {
      "enabled": true
    },
    "privacy": {
      "dp_enabled": false
    }
  }
}
```

For platform submission, pass this object as the `spec` field when using `--input-data`; with `--input-file`, the generated API command accepts the same create payload shape documented by CLI help.

`platform-job.json` wraps the job spec:

```json
{
  "spec": {
    "data_source": "default/my-input#input.csv",
    "config": {
      "enable_synthesis": true,
      "enable_replace_pii": false
    }
  }
}
```

## Next Steps

- Tune job parameters with `workflows/config.md` and `workflows/config-runs.md`.
- Retrieve job result files with `workflows/results.md`.
- Interpret output files with `workflows/artifacts.md`.
- Debug failed runs with `workflows/diagnose.md`.
