<a id="data-designer-migration"></a>
# Moving Between Execution Modes

Data Designer configurations are mostly portable across plugin execution modes. The main migration question is not "library versus service"; it is whether the workload executes locally in the CLI process or through NeMo Services, and which resources the configuration references.

See [Execution Modes](execution-modes.md) for the full two-axis model.

## What Usually Stays the Same

Most configuration code can stay unchanged:

| Configuration area | Portability |
|--------------------|-------------|
| Column definitions | Same across CLI `run`, CLI `submit`, and SDK execution. |
| Prompt templates and Jinja2 references | Same across execution modes. |
| Constraints and profilers | Same across execution modes. |
| Model aliases and inference parameters | Same across execution modes. |
| Processors and generated dataset schema | Same across execution modes, subject to features supported by NeMo Services. |

For CLI execution, put your configuration in a Python module that exposes `load_config_builder()`. The plugin CLI loads the builder and executes it through either `run` or `submit`.

## Moving to Local CLI Execution

Use local CLI execution when you want the Data Designer workload to run in your current Python environment. Local CLI execution can use fully local resources, NeMo resources, or a mix of both:

| Resource pattern | Local CLI `run` behavior |
|------------------|--------------------------|
| Local files or DataFrames | Supported. The workload runs where those objects are available. |
| Local provider settings | Supported. The plugin checks local provider configuration first. |
| Environment or plaintext secrets | Supported. |
| Files API Filesets | Supported when NeMo Services access is configured. |
| Secrets API secrets | Supported when NeMo Services access is configured. |
| Inference Gateway providers | Supported when NeMo Services access is configured. |

This can be fully local, but it is not an offline-only mode. If the configuration references `default/nvidia-build`, a Fileset, or a Secrets API secret, the local workload still communicates with those NeMo Services APIs.

## Moving to NeMo Services Execution

Use NeMo Services execution when you want service-managed workload execution, logs, jobs, and artifacts. When moving a configuration from local CLI `run` to `submit` or SDK execution, check these areas:

| Area | Local CLI `run` | NeMo Services `submit` / SDK today | Migration action |
|------|-----------------|------------------------------------|------------------|
| **Inference** | Local providers and/or Inference Gateway providers. | Inference Gateway providers. | Register an Inference Gateway provider and reference it by workspace/name, such as `default/nvidia-build`. |
| **Secrets** | Environment variables, plaintext values, and Secrets API secrets. | Secrets API secrets. | Create Secrets API secrets and reference them from the configuration. |
| **Seed data** | Local files, DataFrames, HuggingFace, or Filesets. | HuggingFace or Filesets. | Upload local seed data to a Files API Fileset or use HuggingFace. |
| **Personas** | Local persona datasets downloaded to the managed assets directory. | Persona Filesets in NeMo Services. | Use `nemo data-designer personas make-fileset` for required locales. |
| **Artifacts** | Local execution output. | Job artifact storage. | Use job status/logs and artifact download helpers. |

## Moving Back to Local CLI Execution

If a configuration already runs through `submit` or the SDK, it can usually run through CLI `run` without changing NeMo resource references. Local execution can still use Filesets, Secrets, and Inference Gateway providers.

You may choose to simplify the configuration for local-only iteration:

| NeMo resource | Local CLI alternative |
|---------------|-----------------------|
| Fileset seed data | Local file or DataFrame seed data. |
| Secrets API secret | Environment variable or plaintext secret. |
| Inference Gateway provider | Local provider settings. |
| Persona Fileset | Locally downloaded persona dataset. |

These changes are optional. Keep NeMo resource references when you want the same configuration to work in both `run` and `submit`.

## SDK Local Execution

SDK execution uses the Data Designer API today. Local SDK execution is planned, but not available yet. Use CLI `run` for local in-process execution until the SDK supports the same mode.

## Migration Checklist

Before switching execution modes, verify:

- The configuration source exposes `load_config_builder()` for CLI execution.
- Model providers referenced in `ModelConfig.provider` are available in the target mode.
- Secret references are resolvable in the target mode.
- Seed data sources are compatible with the target mode.
- Persona datasets are installed locally or published as Files API Filesets as needed.

## Getting Help

- **Execution Modes:** See [Execution Modes](execution-modes.md) for the conceptual model.
- **CLI:** See [Data Designer CLI](cli.md) for `run`, `submit`, and persona commands.
- **Tutorials:** Follow the [tutorials](tutorials/index.md) for hands-on examples.
- **Library Docs:** Refer to the [open-source library documentation](https://nvidia-nemo.github.io/DataDesigner/0.5.7/) for configuration details.
