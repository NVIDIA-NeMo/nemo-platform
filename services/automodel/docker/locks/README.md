# Mamba / causal-conv1d wheel build locks

Copied from `nmp/docker/locks/` for building `causal-conv1d-wheel` and `mamba-ssm-wheel` images from the Platform repo (see `Dockerfile.mamba-wheel` and `docker-bake.hcl` group `nmp-automodel-gpu-wheels`).

To refresh locks after dependency changes:

```bash
cd /path/to/Platform
uv lock --project services/automodel/docker/locks/mamba-wheel-build-py311 --python 3.11
uv lock --project services/automodel/docker/locks/mamba-wheel-build-py312 --python 3.12
```
