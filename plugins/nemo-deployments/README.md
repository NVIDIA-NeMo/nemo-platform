# NeMo Deployments Plugin

Backend-agnostic deployment lifecycle for the NeMo Platform: entity schemas,
CRUD APIs, a `DeploymentBackend` ABC, an executor registry, and a background
reconcile controller (`DeploymentsController`).

## Controller

Register `DeploymentsController` via the `nemo.controllers` entry point. The controller
paginates non-terminal deployment/volume lists, reconciles volumes before deployments,
gates deployment create on mounted volumes reaching `BOUND`, and writes status via the
entity client (including endpoints and status history). Orphan backend resource cleanup
runs on a configurable interval and is skipped when the deployment list is unhealthy.

The controller exposes `is_healthy`, which is `False` when either the deployment-list or
volume-list query fails. Internally these are tracked separately so operators can tell
which list query failed without losing that signal behind a single boolean.

Per-config drift backoff overrides live on `DeploymentConfig.driftRecovery`; unset fields
fall back to `DeploymentsConfig.controller`.

Prerequisites are declared on each `Deployment` and reference other deployment
names in the same workspace (bare name or `workspace/name`). The controller loads
terminal prerequisite deployments from the entity store when they are not in the
active non-terminal list.

## Docker executors

Host port allocation for published container ports is configured per named docker
executor (not on `DeploymentConfig.backend_config.docker`). Set the inclusive
`port_range_start` / `port_range_end` bounds on the executor `config` block in
platform YAML. The allocator scans every host port from `port_range_start`
through `port_range_end`, including both endpoints (for example, 9000–9100
allows 101 ports):

```yaml
deployments:
  executors:
    - name: local-docker
      backend: docker
      config:
        port_range_start: 9000
        port_range_end: 9100  # inclusive
  default_executor: local-docker
```

Entity-level `backend_config.docker` accepts only deployment-specific overrides such
as `network`.

## Docker resource naming

Docker container and volume names use a readable prefix plus a deterministic
8-character hash suffix. The hash is computed from ``{workspace}/{name}``, not
from the hyphen-joined string, so pairs like ``foo``/``bar-baz`` and
``foo-bar``/``baz`` cannot collide. Naming logic is shared via
``nemo_platform_plugin.k8s_naming`` (same module used by the models service).
Orphan cleanup matches identity labels, not names alone; existing containers
keep their old names after upgrade.
