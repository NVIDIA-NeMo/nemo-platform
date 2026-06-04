# NeMo Data Designer Plugin

A NeMo Platform plugin that brings Data Designer into the platform.

## Validate a Config

`nemo data-designer validate` checks whether a Data Designer config is fit to submit to the platform:

```bash
nemo data-designer validate config.yaml
```

The exit code is `0` only when the service-backed context validates cleanly. JSON output (`--output json`) emits a structured `ValidationReport` for CI / automation use.

The validation mirrors what `nemo data-designer <preview|create> submit` accepts: unsupported seed types and `tool_configs` are rejected, IGW providers are resolved against the platform, Files-service seeds are looked up, and Nemotron Personas filesets are checked. The pass is a client-side simulation of those checks; it does not contact the data-designer service.

### Programmatic use

The same logic is exposed on the SDK via `DataDesignerResource.validate(config_builder, *, execution_context=None, workspace=None)` and its async sibling. Both return a `ValidationReport` from `nemo_data_designer_plugin.sdk.validation`.

## Nemotron Personas Filesets

Data Designer workloads that include `PersonSampler` columns require Nemotron Personas filesets to exist in the `system` workspace for each requested locale. These filesets can be created using the CLI.

Use an existing NGC API key secret:

```bash
nemo data-designer personas make-fileset \
  --locale en_US \
  --api-key-secret system/ngc-api-key
```

Create a new secret from an environment variable, then bind the fileset to it:

```bash
nemo data-designer personas make-fileset \
  --locale en_US \
  --api-key-secret system/my-ngc-key \
  --api-key-env-var NGC_API_KEY
```
