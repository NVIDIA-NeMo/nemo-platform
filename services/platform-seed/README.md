# Platform seed task

Platform-centric seeding for NeMo Platform: auth role bindings (platform admin, wildcard default/system/workspace-creator), guardrails config store, the default model provider, and plugin-contributed seed jobs discovered from `nemo.seed`. This codebase provides the **task** (run via `nemo-platform run task --task nmp.platform_seed` or as a K8s Job). Optionally, the platform API can run the same seed once at startup when `platform.seed_on_startup` is true in the platform config (or `NMP_SEED_ON_STARTUP=true`). There is no standalone seed service.

**Layout** (aligned with hello-world): one package `nmp.platform_seed` with `config.py` and `tasks/seed/` for the task (run.py, __main__.py). The task can be run as `python -m nmp.platform_seed` or `python -m nmp.platform_seed.tasks.seed`.

The task uses the same platform config as the rest of the platform (e.g. `NMP_CONFIG_FILE_PATH` and `get_platform_config()`) to resolve service URLs. It uses `get_async_platform_sdk()` from the SDK factory for API calls. When run as a K8s Job or after boot, the task waits for dependencies using the same pattern as services: `async_wait_for_dependencies()` polls each dependency’s `/status` using `platform_config.get_service_url(service_name)`, so service APIs may live at different URLs. Dependency list: entities, auth, files.

## Usage

- **As a task**: Run `uv run python -m nmp.platform_seed` or `nemo-platform run task --task nmp.platform_seed` with platform config set so the SDK can reach the API.
- **On API startup**: Set `platform.seed_on_startup: true` in the platform config (or `NMP_SEED_ON_STARTUP=true`) so the platform runs the seed once in the background after the API server starts.
- **As a library**: Call `run_platform_seed(entity_client, sdk, config)` from your script or test.
- **Conditional**: Set `NMP_PLATFORM_SEED_ENABLED=false` to disable.

## Config (env)

| Variable | Default | Description |
|----------|---------|-------------|
| `NMP_PLATFORM_SEED_ENABLED` | true | Master switch |
| `NMP_PLATFORM_SEED_AUDITOR_ENABLED` | true | Seed auditor configs |
| `NMP_PLATFORM_SEED_AUTH_ENABLED` | true | Seed auth role bindings (PlatformAdmin plus wildcard Editor, Viewer, and WorkspaceCreator bindings) |
| `NMP_PLATFORM_SEED_GUARDRAILS_ENABLED` | true | Seed guardrail configs |
| `NMP_PLATFORM_SEED_MODEL_PROVIDER_ENABLED` | true | Seed nvidia-build model provider |
| `NMP_PLATFORM_SEED_<PLUGIN_NAME>_ENABLED` | true | Enable or disable an individual plugin seed job discovered under `nemo.seed` (`<PLUGIN_NAME>` is the seed job name uppercased with non-alphanumeric characters replaced by `_`) |
| `NMP_PLATFORM_SEED_GUARDRAILS_CONFIG_STORE_PATH` | (from `CONFIG_STORE_PATH`) | Guardrails config store path |
| `NMP_PLATFORM_SEED_WAIT_FOR_READY_ENABLED` | true | Wait for dependency services (entities, auth, files) via /status before seeding |
| `NMP_PLATFORM_SEED_WAIT_FOR_READY_RETRIES` | 60 | Max readiness checks per dependency (total timeout = retries × interval) |
| `NMP_PLATFORM_SEED_WAIT_FOR_READY_INTERVAL_SECONDS` | 5.0 | Seconds between readiness checks |
| `CONFIG_STORE_PATH` | /dev/null | Fallback guardrails config store path |
