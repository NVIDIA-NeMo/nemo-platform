# Docker lock projects

This directory holds committed `uv` lock projects used by Docker builds that need
reproducible Python build environments.

## Mamba wheel builder lockfiles

`docker/base/Dockerfile.mamba-wheel` uses these lock projects:

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
