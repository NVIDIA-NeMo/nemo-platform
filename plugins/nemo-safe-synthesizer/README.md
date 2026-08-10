<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Run Safe Synthesizer Jobs

Use the Safe Synthesizer plugin to submit jobs through the platform Jobs service.

## Prerequisites

- A GPU-capable Jobs backend.
- The Safe Synthesizer plugin installed in the NeMo Platform environment.
- A Safe Synthesizer job spec, such as `nss-job.json`.
- A running platform with access to the required filesets and secrets.

## Steps

1. Start NeMo Platform and confirm readiness:

   ```bash
   curl -s http://localhost:8080/health/ready
   ```

2. Optionally register model filesets:

   ```bash
   uv run python plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py --files-api-url http://localhost:8080
   ```

3. Submit jobs through the SDK builder or Jobs API. See `docs/safe-synthesizer/sdk-resources.mdx`.

## Troubleshooting

- If model downloads fail, confirm the Files API URL is reachable and the model filesets exist in the selected workspace.
- If CUDA initialization fails, inspect the job logs and verify the task image matches the cluster driver/runtime.
- If the job cannot load input data, confirm the fileset reference in the job spec.

## Related Links

- `docs/safe-synthesizer/about/host-local-development.mdx` - runtime setup and inspection
- `docs/safe-synthesizer/about/reference.md`
- `plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py`

## Next Steps

- Review the architecture reference: `docs/safe-synthesizer/about/reference.md`.
- Run the model setup script: `plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py`.
- Retrieve job artifacts: `plugins/nemo-safe-synthesizer/src/nemo_safe_synthesizer_plugin/skills/safe-synthesizer/workflows/artifacts.md`.
