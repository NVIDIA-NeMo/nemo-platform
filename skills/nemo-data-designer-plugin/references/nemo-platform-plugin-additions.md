# NeMo Plugin Additions

This skill ships in the NeMo Platform data-designer plugin. The CLI surface is `nemo data-designer …`. Most subcommands accept the same arguments as the upstream `data-designer` CLI; the differences are documented below.

## Validation

Upstream's `validate` command runs a local-only engine compile check. The plugin's `validate` does that **and** verifies the config against NeMo Platform-specific constraints — Inference Gateway provider resolution, Files-service seed sources, Nemotron Personas filesets, the remote seed-type whitelist, etc.

```bash
nemo data-designer validate <path>
```

```text
  ✘ Seed source 'df' is not supported on the NeMo Platform.
    Use a serializable seed source such as a HuggingFace dataset
    or the Files service.
```

A single invocation surfaces **every** problem it can detect (it doesn't short-circuit on the first failure). Exit code is 0 only when no errors are reported.

Useful flags:

- `--workspace <name>` — workspace used to resolve Inference Gateway providers and Files-service seed sources for the remote pass. Defaults to the SDK's configured workspace.
- `--output {text,json}` — `json` emits a structured `ValidationReport` for CI / scripting use.

## Model configs

The upstream skill assumes model aliases come from a YAML registry under `~/.data-designer/`. In this plugin you must reference models and providers registered in the platform; `agent context` does **not** see these

**Declare `ModelConfig`s programmatically in the script.** `DataDesignerConfigBuilder` accepts model configs directly, either via its constructor or `.add_model_config(...)`:

```python
import data_designer.config as dd

def load_config_builder() -> dd.DataDesignerConfigBuilder:
    config_builder = dd.DataDesignerConfigBuilder(
        model_configs=[
            dd.ModelConfig(
                alias="text",
                model="...",
                provider="default/nvidia-build",
                inference_parameters=dd.ChatCompletionInferenceParams(),
            ),
        ],
    )
    ...
```

Pick the right `inference_parameters` class for the generation type: `ChatCompletionInferenceParams`, `EmbeddingInferenceParams`, or `ImageInferenceParams`. The class determines the alias's `generation_type` and which column types can use it.

**Reference an Inference Gateway-managed model provider.** `ModelConfig.provider` may be a bare provider name (resolved in the active workspace) or `<workspace>/<provider>`.

Discover available Inference Gateway providers with `nemo inference providers list`. A common default created during `nemo setup` is `default/nvidia-build`, but it's optional — confirm before relying on it. If the user mentions a provider by name (e.g., "use my-vllm"), trust the name and let the registry surface a clear error at preview time if it isn't reachable.

When using an Inference Gateway provider, the `model` field in the `dd.ModelConfig` should use the `served_model_name` as understood by Inference Gateway, not the `model_entity_id`.

If `agent context` shows no usable aliases, that is **not** a blocker — it only means the local YAML registry is unconfigured, which is irrelevant in this plugin context anyways.

## Personas

The plugin adds a `personas` command group on top of upstream Data Designer. Use it to publish Nemotron Personas as NeMo Platform filesets so cluster-side workloads can read them.

```bash
nemo data-designer personas make-fileset \
  --locale en_US \
  --api-key-secret <workspace>/<secret-name>
```

Requires an NGC API key secret already registered in NeMo Platform. To create the secret in the same call, add `--api-key-env-var <ENV_VAR>` and set that env var to the API key value before running.

## Related NeMo Platform commands

- `nemo inference providers list` / `nemo models list` — NeMo Platform-side inference providers and models.
- `nemo secrets` — manage API keys used by `personas make-fileset` and other NeMo Platform-side flows.
- `nemo files` — manage filesets, including persona filesets created above.
- `nemo data-designer retrieval-generate` / `retrieval-prepare` — Nemotron retrieval SDG Stage 0/1. See `references/retrieval-sdg.md`.

These are alternatives to the local `~/.data-designer/` configuration the upstream skill assumes. The local configurations will not work when using this plugin.
