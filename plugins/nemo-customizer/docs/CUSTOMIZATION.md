# Customization contributor guide

Register a training backend under **`nemo.customization.contributors`** (not `nemo.services`).

## Contract

Implement `CustomizationContributor`:

- `name` — must match the entry-point key (e.g. `automodel`)
- `get_routers()` — `RouterSpec` list with a **unique** prefix under `v2/workspaces/{workspace}/<backend>/`
- `get_cli()` — optional `typer.Typer` mounted at `nemo customization <name>`
- SDK: contributors implement HTTP/CLI only; **`nemo-customizer-plugin`** owns `nemo.sdk` → `customization` and composes backends (e.g. `client.customization.automodel.jobs` from `nemo-automodel-plugin`)

## pyproject.toml

```toml
[project.entry-points."nemo.customization.contributors"]
automodel = "nemo_automodel_plugin.contributor:AutomodelContributor"
```

## Jobs

Use `add_job_routes(YourJob, service_name="customization", ...)` so Jobs records use `source=customization`.
