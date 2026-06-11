# NeMo Deployments Plugin

Substrate-agnostic deployment lifecycle for the NeMo Platform. This plugin provides
entity schemas, CRUD APIs, a `DeploymentBackend` ABC, and an executor registry.
Backend implementations and the reconcile controller are delivered in follow-on tickets.

## API base path

`/apis/deployments/v1/workspaces/{workspace}/...`

Cross-workspace bulk queries use the entity-store sentinel workspace ``-``:

``GET /apis/deployments/v1/workspaces/-/deployments?status_in=pending,starting``

```bash
uv sync
uv run pytest plugins/nemo-deployments/tests/unit -v
```
