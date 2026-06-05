# NeMo Auditor Plugin

A NeMo Platform plugin which provides Auditor, an LLM
vulnerability scanner service powered by [Garak](https://https://github.com/NVIDIA/garak)

## CLI quickstart

### Prerequisites

Before running the `nemo auditor configs create` and `nemo auditor targets
create` commands below, make sure you have:

- **NeMo CLI installed and platform running** — follow
  [SETUP.md](../../SETUP.md) (`make bootstrap` + `nemo setup`).
- **CLI pointed at the platform** — `nemo setup` configures
  `http://localhost:8080` automatically; otherwise set it explicitly with
  `nemo config set --base-url <url>`.
- **A workspace to operate in** — the examples use `-w default`, which
  `nemo setup` creates. Substitute another workspace name as needed.

For detailed guides and reference material, see the full auditor
documentation at [`docs/auditor/`](../../docs/auditor/index.md).

### Managing configs and targets

Two persistent entity types — `AuditConfig` (probe / detector / reporting
settings) and `AuditTarget` (the model under test) — are managed through the
NeMo CLI:

```bash
# Create a config from a JSON file
nemo auditor configs create quick-scan -w default -f ./quick-scan.json

# Create a target inline
nemo auditor targets create llama-31-8b -w default -d '{
  "type": "nim",
  "model": "meta/llama-3.1-8b-instruct",
  "options": {"uri": "http://localhost:9000/v1"}
}'

# List, get, update, delete are all available
nemo auditor configs list -w default
nemo auditor targets get llama-31-8b -w default
nemo auditor configs delete quick-scan -w default
```

There is no CLI command for running an audit yet — the local-run path is
exposed through the SDK (below). The platform jobs service can submit
audits via the `auditor.audit` job entry point.

## SDK quickstart

Every CLI verb has a matching Python SDK method on `client.auditor`, plus
`client.auditor.run(...)` for in-process execution that bypasses the jobs
service.

```python
from nemo_platform import NeMoPlatform
from nemo_auditor.entities import (
    AuditSystemData, AuditRunData, AuditPluginsData, AuditReportData,
)

client = NeMoPlatform()

# Persist a config
cfg = client.auditor.configs.create(
    workspace="default",
    name="quick-scan",
    system=AuditSystemData(lite=True, parallel_attempts=4),
    run=AuditRunData(generations=3),
    plugins=AuditPluginsData(probe_spec="latentinjection", detector_spec="auto"),
    reporting=AuditReportData(report_prefix="quick-scan"),
)

# Persist a target
tgt = client.auditor.targets.create(
    workspace="default",
    name="llama-31-8b",
    type="nim",
    model="meta/llama-3.1-8b-instruct",
    options={"uri": "http://localhost:9000/v1"},
)

# Run an audit locally (no jobs-service submission) using the persisted entities
result = client.auditor.run(
    config="quick-scan",       # workspace-qualified name strings ("ws/name") also work
    target="llama-31-8b",
    workspace="default",
)
print(result["status"], result["returncode"])
for name, ref in result["results"].items():
    print(name, ref["artifact_url"])
```

`run()` shells out to a pre-installed garak interpreter (default
`~/.auditor/.venv/bin/python`, override via `$NEMO_AUDITOR_GARAK_PYTHON`)
and registers the resulting JSONL / HTML / hitlog reports as job results
under a temp directory managed by the local scheduler.
