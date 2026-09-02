<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Docker lock projects

This directory holds committed `uv` lock projects used by Docker builds that need
reproducible Python build environments.

## Mamba wheel builder lockfiles

`docker/base/Dockerfile.python-wheels` uses these lock projects:

- `mamba-wheel-build-py311`
- `mamba-wheel-build-py312`

Update the matching `pyproject.toml` first, then regenerate the lockfile from the
repo root:

```bash
uv lock --project docker/locks/mamba-wheel-build-py311 --python 3.11
uv lock --project docker/locks/mamba-wheel-build-py312 --python 3.12
```

### Torch version sync

The `torch` pin in these lockfiles **must** match the `torch` version in the
workspace `pyproject.toml` `[dependency-groups].cu128` section.  If the versions
diverge, the CUDA extension wheels (mamba-ssm, causal-conv1d) will be compiled
against a different torch ABI than the runtime images install, causing
`undefined symbol` errors at import time.

CI enforces this via `script/check-torch-version-sync.py` in the
`Docker Lock Lint` workflow. When bumping torch in the workspace, update the
lockfiles too:

```bash
# 1. Edit both pyproject.toml files to set the new torch version
# 2. Regenerate lockfiles
uv lock --project docker/locks/mamba-wheel-build-py311 --python 3.11
uv lock --project docker/locks/mamba-wheel-build-py312 --python 3.12
```

### Verifying lockfiles

If you change these lock projects, verify both Linux target environments still
resolve cleanly:

```bash
uv sync --project docker/locks/mamba-wheel-build-py311 --locked --no-install-project --dry-run --python-platform x86_64-unknown-linux-gnu
uv sync --project docker/locks/mamba-wheel-build-py311 --locked --no-install-project --dry-run --python-platform aarch64-unknown-linux-gnu
uv sync --project docker/locks/mamba-wheel-build-py312 --locked --no-install-project --dry-run --python-platform x86_64-unknown-linux-gnu
uv sync --project docker/locks/mamba-wheel-build-py312 --locked --no-install-project --dry-run --python-platform aarch64-unknown-linux-gnu
```

## Gym task image lockfile

`docker/Dockerfile.nmp-gym-tasks` uses `nmp-gym-tasks` for the isolated Gym
environment. The lock is separate from the workspace because Gym and Ray are
image-specific dependencies that are intentionally excluded from the shared CPU
task environment.

After changing `docker/locks/nmp-gym-tasks/pyproject.toml`, regenerate
its lock with Python 3.13.15 or newer:

```bash
uv lock --project docker/locks/nmp-gym-tasks --python 3.13.15
```

Verify both image architectures:

:::::{tab-set}

::::{tab-item} x86_64
```bash
uv sync --project docker/locks/nmp-gym-tasks --locked --no-install-project --dry-run --python 3.13.15 --python-platform x86_64-unknown-linux-gnu
```
::::

::::{tab-item} aarch64
```bash
uv sync --project docker/locks/nmp-gym-tasks --locked --no-install-project --dry-run --python 3.13.15 --python-platform aarch64-unknown-linux-gnu
```
::::

:::::

### Upgrading Gym task dependencies

Dependency upgrades are deliberate maintenance changes; the image build never
relocks dynamically:

1. Update the direct pins in `docker/locks/nmp-gym-tasks/pyproject.toml`.
2. Regenerate `uv.lock` with the command above.
3. Review the lock diff, especially the resolved `ray` version and packages
   containing native code.
4. Run both architecture checks above.
5. Build `nmp-gym-tasks-smoke-test`, which verifies the Gym CLI and imports the
   installed `nemo_gym`, `ray`, and `tiktoken` packages:

   ```bash
   docker buildx bake nmp-gym-tasks-smoke-test
   ```

6. Run the Evaluator agent-evaluation compiler tests, which verify that Gym
   targets route to this image.
