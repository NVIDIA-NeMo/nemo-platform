<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Data Designer Plugin

A NeMo Platform plugin that brings Data Designer into the platform.

## Validate a Config

`nemo data-designer validate` checks whether a Data Designer config is fit to be executed on the platform.

```bash
nemo data-designer validate config.yaml
```

JSON output (`--output json`) emits a structured `ValidationReport` for CI / automation use.

### Programmatic use

The same logic is exposed on the SDK via `DataDesignerResource.validate(config_builder, *, workspace=None)` and its async sibling. Both return a `ValidationReport` from `nemo_data_designer_plugin.sdk.validation`.

## Build Evaluation Datasets from Intake

The `build-dataset` job materializes an immutable, reviewable Dataset Fileset from either a selected
set of normalized Intake traces or existing datasets. It intentionally stores dataset rows rather
than copying raw ATIF: each row contains the instruction, observed output, optional reference,
historical grader results, metric references, and exact trace/dataset lineage.

Create an agent-specific dataset from selected traces:

```bash
curl -X POST \
  "$NMP_BASE_URL/apis/data-designer/v2/workspaces/default/jobs/build-dataset" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "tea-traces-dataset-build",
    "spec": {
      "destination": {"name": "tea-traces-dataset-v1"},
      "source": {
        "kind": "intake-traces",
        "agent_name": "tea",
        "trace_ids": ["trace-1", "trace-2"],
        "grader_refs": ["default/testcrew-tea-quality-v1"]
      }
    }
  }'
```

The Intake trace list supports `agent_name`, so a UI can discover the selectable traces first:

```text
GET /apis/intake/v2/workspaces/default/traces?filter={"agent_name":"tea"}&mode=preview
```

Compose already-materialized agent datasets into a shared catalog dataset:

```bash
curl -X POST \
  "$NMP_BASE_URL/apis/data-designer/v2/workspaces/default/jobs/build-dataset" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "qa-catalog-dataset-build",
    "spec": {
      "destination": {"name": "qa-catalog-dataset-v1"},
      "source": {
        "kind": "datasets",
        "datasets": ["default/tea-traces-dataset-v1", "default/tra-traces-dataset-v1"]
      }
    }
  }'
```

The output Fileset has `purpose=dataset`, a canonical Parquet file at `data/data.parquet`, typed
dataset metadata (`record_count`, `grader_refs`, and dataset-level lineage).
Composition accepts only this versioned row contract and deduplicates identical trace-derived rows;
conflicting rows with the same stable id fail the job instead of silently choosing one.

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
