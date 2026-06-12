# NeMo Deployments Plugin

Substrate-agnostic deployment lifecycle for the NeMo Platform: entity schemas,
CRUD APIs, a `DeploymentBackend` ABC, an executor registry, and a background
reconcile controller (`DeploymentsController`).

## Controller

Register `DeploymentsController` via the `nemo.controllers` entry point. The controller
paginates non-terminal deployment/volume lists, reconciles volumes before deployments,
gates deployment create on mounted volumes reaching `BOUND`, and writes status via the
entity client (including endpoints and status history). Orphan substrate cleanup runs on
a configurable interval and is skipped when the deployment list is unhealthy.

Per-config drift backoff overrides live on `DeploymentConfig.driftRecovery`; unset fields
fall back to `DeploymentsConfig.controller`.

## Deferred (follow-on tickets)

| Item | Why deferred |
|------|----------------|
| Volume delete → `RELEASED` | No `DELETING` state or `list_managed_volume_names` on the backend ABC yet |
| Volume orphan cleanup | Requires backend support to list substrate volumes without entities |
| Docker/K8s E2E | AIRCORE-756/757 — `BACKEND_CLASSES` empty until backends register |
| Per-volume executor routing | No `Volume.executor` field in 755; volumes use `default_executor` |

## API base path

`/apis/deployments/v2/workspaces/{workspace}/...`

Cross-workspace bulk queries use the entity-store sentinel workspace ``-``:

``GET /apis/deployments/v2/workspaces/-/deployments?status_in=pending,starting``

## Tests

```bash
uv sync
uv run pytest plugins/nemo-deployments/tests/unit -v
```

## Next steps

- **[AIRCORE-756](https://linear.app/nvidia/issue/AIRCORE-756):** Docker `DeploymentBackend`
- **[AIRCORE-757](https://linear.app/nvidia/issue/AIRCORE-757):** Kubernetes `DeploymentBackend`
- **[AIRCORE-759](https://linear.app/nvidia/issue/AIRCORE-759):** Models/agents adoption
- **755 scaffold:** entity CRUD and executor registry ([PR #280](https://github.com/NVIDIA-NeMo/nemo-platform/pull/280))
