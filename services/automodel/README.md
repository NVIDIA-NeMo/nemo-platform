# nmp-automodel

Compiler and task entrypoints for NeMo Automodel training jobs on the platform. **No HTTP server** — consumed by `nemo-automodel-plugin` and Jobs task images (`my-registry/nemo-platform-dev/nmp-customizer-tasks`, `.../nmp-automodel-training`).

Runtime exceptions from `nemo_automodel` are mapped to user-facing error types via `src/nmp/automodel/tasks/training/errors/error_rules.yaml`. See [docs/automodel_errors.md](docs/automodel_errors.md) for the full catalog and validation status of each Automodel error.
