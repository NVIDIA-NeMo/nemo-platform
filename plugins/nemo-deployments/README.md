# NeMo Deployments Plugin

Substrate-agnostic deployment lifecycle for the NeMo Platform. This plugin provides
entity schemas, CRUD APIs, a `DeploymentBackend` ABC, and an executor registry.

**Scope (this ticket):** scaffold only — entity types, v1 CRUD routes, backend contract,
and executor registry. Docker/K8s backends and the reconcile controller land in follow-on
tickets (756–758).

## Prerequisites

- NeMo Platform workspace bootstrapped (`make bootstrap`, `nemo setup`)
- Plugin enabled in root `pyproject.toml` (`enabled-plugins` includes `deployments`)

## API base path

`/apis/deployments/v1/workspaces/{workspace}/...`

Cross-workspace bulk queries use the entity-store sentinel workspace ``-``:

``GET /apis/deployments/v1/workspaces/-/deployments?status_in=pending,starting``

## Next steps

- **756 / 757:** Docker and Kubernetes `DeploymentBackend` implementations
- **758:** Reconcile controller wiring status writes and backend lifecycle

## Tests

```bash
uv sync
uv run pytest plugins/nemo-deployments/tests/unit -v
```
