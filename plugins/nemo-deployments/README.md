# NeMo Deployments Plugin

Substrate-agnostic deployment lifecycle for the NeMo Platform: entity schemas,
CRUD APIs, a `DeploymentBackend` ABC, and an executor registry.

## Tests

```bash
uv sync
uv run pytest plugins/nemo-deployments/tests/unit -v
```
