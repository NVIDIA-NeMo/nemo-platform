<a id="nss-getting-started"></a>
# Getting Started with {{nss_short_name}}

Get started with {{nss_short_name}} for generating private synthetic versions of sensitive tabular datasets on a host GPU.

## Prerequisites

Before using {{nss_short_name}}, complete [Setup](../get-started/setup.md) to install the CLI/SDK.

{{nss_short_name}} has the following additional requirements:

- An NVIDIA GPU **on the host machine** with 80GB+ VRAM (check with `nvidia-smi`). This is separate from any GPU inside a NIM container; Safe Synthesizer training runs directly on the host.
- Sufficient disk space for generated datasets (50GB+ recommended)

For general platform troubleshooting (port conflicts, health checks, and so on), refer to [Setup](../get-started/setup.md).

--8<-- "_snippets/nvidia-build-model-provider.md"

---

## Host-local CLI

For GPU development on your machine, install the Safe Synthesizer plugin from this repository and use `nemo safe-synthesizer run-local` (see [Local and Subprocess Execution](about/host-local-development.md)):

```shell
BOOTSTRAP_LOCAL_PLUGIN_DIRS=plugins/nemo-safe-synthesizer make bootstrap-python
uv run nemo safe-synthesizer runtime setup
uv run nemo safe-synthesizer run-local \
  --spec-file ./nss-job.json \
  --data-source ./input.csv \
  --output-dir ./nss-output
```

The `run-local` command launches the Safe Synthesizer task in a separate runtime Python subprocess. The `nemo safe-synthesizer` CLI today exposes **run-local** and **runtime** only; platform job submission uses the Jobs API or SDK.

---

## Next Steps

Create your first synthetic dataset:

- [Safe Synthesizer 101 Tutorial](tutorials/safe-synthesizer-101.md) - a beginner-friendly introduction
- [Local and Subprocess Execution](about/host-local-development.md) - local CLI and runtime task details
- [SDK Resources](sdk-resources.md) - Python SDK methods for jobs, builders, logs, and results

---
