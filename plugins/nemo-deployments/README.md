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

Prerequisites are currently declared on `DeploymentConfig` and resolve to a single
deployment per config name in a workspace. Multiple deployments sharing one config is
unsupported until prerequisites move to the `Deployment` entity (follow-up work).
