# Manual Service Startup

Load this reference when the user asks to run only the local services, debug service startup directly, or avoid the higher-level `nemo setup` wizard.

If `nemo setup` is too high-level for debugging, start the core services manually after bootstrap:

```bash
source .venv/bin/activate
export NMP_BASE_URL=http://localhost:8080
uv run nemo services run \
  --services entities,models,inference-gateway,secrets \
  --controllers models
```

Use `nemo setup` again for provider registration, default-model selection, skill install, and demo-agent deployment.
