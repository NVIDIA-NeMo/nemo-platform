<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Data Designer Plugin

A NeMo Platform plugin that brings Data Designer into the platform.

## Validate a Config

`nemo data-designer validate` checks whether a Data Designer config is fit for local library compatibility and/or platform submission. By default it runs every applicable execution context and reports each independently:

```bash
nemo data-designer validate config.yaml
```

Limit the check to one context with `--execution-context`:

```bash
# Only the local-library checks
nemo data-designer validate config.yaml --execution-context local

# Only the platform/remote checks
nemo data-designer validate config.yaml --execution-context remote
```

The exit code is `0` only when every requested context validates cleanly. JSON output (`--output json`) emits a structured `ValidationReport` for CI / automation use.

### Local vs. remote

- **Local** (`--execution-context local`) checks open-source library compatibility: the engine compiles the config and resolves model providers the library understands (including locally defined providers). This is a library/config check, not a platform execution path — there is no `nemo data-designer … run` verb.
- **Remote** (`--execution-context remote`) mirrors what `nemo data-designer <preview|create> submit` accepts on the platform: local seed types and `tool_configs` are rejected, **only Inference Gateway providers** are accepted, Files-service seeds are looked up, and Nemotron Personas filesets are checked. The remote pass is a client-side simulation of those checks; it does not contact the data-designer service.

### Programmatic use

The same logic is exposed on the SDK via `DataDesignerResource.validate(config_builder, *, execution_context=None, workspace=None)` and its async sibling. Both return a `ValidationReport` from `nemo_data_designer_plugin.sdk.validation`.

## Nemotron Personas Filesets

When executing remotely, Data Designer workloads that include `PersonSampler` columns require Nemotron Personas filesets to exist in the `system` workspace for each requested locale. These filesets can be created using the CLI.

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
