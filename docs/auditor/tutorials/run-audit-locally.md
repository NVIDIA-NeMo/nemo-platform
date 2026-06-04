<a id="auditor-submit-audit-job"></a>
# Submit an Audit Job

This tutorial walks through submitting a single audit with the {{__auditor_short_name}} plugin SDK. You will persist an audit configuration and target, submit the audit through the plugin service, and use the Jobs service to monitor it.

## Prerequisites

- Install and start {{platform_name}} using the [Setup guide](../../get-started/setup.md).
- Configure at least one Inference Gateway provider. This tutorial uses a `build` provider named `build`.
- Ensure the auditor service and Jobs backend are running.

## 1. Initialize the SDK

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
auditor = client.auditor

print(auditor.plugin_status())
```

## 2. Create an Audit Configuration

```python
from nemo_auditor.entities import (
    AuditPluginsData,
    AuditReportData,
    AuditRunData,
    AuditSystemData,
)

config = auditor.configs.create(
    workspace="default",
    name="quick-scan",
    description="Lite latentinjection scan, 3 generations per probe.",
    system=AuditSystemData(lite=True, parallel_attempts=4),
    run=AuditRunData(generations=3),
    plugins=AuditPluginsData(probe_spec="latentinjection", detector_spec="auto"),
    reporting=AuditReportData(report_prefix="quick-scan"),
)
```

## 3. Create an Audit Target

```python
target = auditor.targets.create(
    workspace="default",
    name="llama-31-8b",
    type="nim.NVOpenAIChat",
    model="meta/llama-3.1-8b-instruct",
    options={
        "nim": {
            "max_tokens": 1024,
            "nmp_uri_spec": {
                "inference_gateway": {
                    "workspace": "default",
                    "provider": "build",
                },
            },
        },
    },
)
```

The `nmp_uri_spec` block tells the plugin to resolve a concrete URI from the Inference Gateway provider at job runtime. See [Inference Gateway](../targets/inference-gateway.md) for details.

## 4. Submit the Audit

`run()` accepts either inline entities or name strings that reference entities in the entity store:

```python
job = auditor.run(
    config="quick-scan",
    target="llama-31-8b",
    workspace="default",
)

print(job["name"])
```

You can also pass the inline `AuditConfig` and `AuditTarget` objects:

```python
job = auditor.run(config=config, target=target, workspace="default")
```

## 5. Monitor and Download Results

Use the standard Jobs APIs or CLI with the job name returned by `run()`:

```bash
nemo jobs get-status <job-name> --workspace default
nemo jobs get-logs <job-name> --workspace default --all-pages
nemo jobs results list <job-name> --workspace default
```

Report artifacts are produced by the platform job. Download them with the Jobs results command once the job completes.

## Clean Up

```python
auditor.configs.delete(workspace="default", name="quick-scan")
auditor.targets.delete(workspace="default", name="llama-31-8b")
```

## Next Steps

- For the full SDK surface, see [SDK Resources](../sdk-resources.md).
- For more probe selection options, see [Selecting Probes](../configs/probes.md).
- For other generator types, see [Audit Targets](../targets/index.md).
