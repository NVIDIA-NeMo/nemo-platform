# Run Safe Synthesizer Locally

Use the Safe Synthesizer plugin to run a job on a host GPU while preserving the platform `safe-synthesizer` API prefix.

## Prerequisites

- A CUDA-capable host with compatible NVIDIA drivers.
- The Safe Synthesizer plugin installed as a local editable plugin.
- The separate Safe Synthesizer runtime venv created with the engine/CUDA dependencies.
- A Safe Synthesizer job spec, such as `nss-job.json`.
- A running Files API if the job references platform filesets.

## Steps

=== "CLI"

    1. Sync the workspace and install this plugin outside the root lock:

       ```bash
       BOOTSTRAP_LOCAL_PLUGIN_DIRS=plugins/nemo-safe-synthesizer make bootstrap-python
       ```

    2. Create the separate runtime venv with the NSS engine/CUDA dependencies:

       ```bash
       uv run nemo safe-synthesizer runtime setup
       ```

    3. Create the model filesets used for offline model cache initialization:

       ```bash
       uv run python plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py --files-api-url http://localhost:8080
       ```

    4. Run the job locally:

       ```bash
       uv run nemo safe-synthesizer run-local --workspace default --spec-file nss-job.json --output-dir ./nss-output
       ```

=== "Managed Runtime"

    1. Sync the workspace, install this plugin outside the root lock, and create the runtime venv:

       ```bash
       BOOTSTRAP_LOCAL_PLUGIN_DIRS=plugins/nemo-safe-synthesizer make bootstrap-python
       uv run nemo safe-synthesizer runtime setup
       uv run python plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py --files-api-url http://localhost:8080
       ```

    2. Run the same local job through the managed runtime:

       ```bash
       uv run nemo safe-synthesizer run-local --workspace default --spec-file nss-job.json --output-dir ./nss-output
       ```

The command writes generated data, summaries, and any adapter output under `./nss-output`.

## Troubleshooting

- If model downloads fail, confirm the Files API URL is reachable and the model filesets exist in the selected workspace.
- If CUDA initialization fails, run `uv run nemo safe-synthesizer runtime info` and verify the runtime package matches the installed driver/runtime.
- If the job cannot load input data, pass a local data source or confirm the fileset reference in the job spec.

## Related Links

- `docs/safe-synthesizer/about/reference.md`
- `plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py`

## Next Steps

- Review the architecture reference: `docs/safe-synthesizer/about/reference.md`.
- Run the model setup script: `plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py`.
- Inspect local artifacts: `plugins/nemo-safe-synthesizer/src/nemo_safe_synthesizer_plugin/skills/safe-synthesizer/workflows/artifacts.md`.
