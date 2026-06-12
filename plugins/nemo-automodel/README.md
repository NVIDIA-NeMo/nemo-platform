# nemo-automodel-plugin

Automodel training contributor under `/apis/customization/v2/workspaces/{workspace}/automodel/`.

Requires **`nemo-customizer-plugin`** at runtime (router + `client.customization` SDK) and **`nmp-automodel`** (compiler/tasks). The Automodel plugin does not declare a pyproject dependency on the customizer plugin — install both via root `enabled-plugins`:

```bash
uv sync --group enabled-plugins
```

## CLI

Verbs are mounted directly on the contributor (no `jobs` subgroup):

```bash
nemo customization automodel explain
nemo customization automodel submit path/to/job.json
nemo customization automodel submit path/to/job.json -w acme-corp
nemo customization automodel submit path/to/job.json --cluster my-cluster
```

`run` is registered but **always fails** — Automodel training is submit-only (platform API / Docker GPU jobs), not local subprocess execution:

```bash
nemo customization automodel run path/to/job.json   # exits with error
```

Other customization backends may still use `nemo customization <backend> jobs submit ...`.

Job JSON uses the simplified `AutomodelJobInput` schema (see `nemo_automodel_plugin/schema.py`). Submit posts to `/apis/customization/v2/workspaces/{workspace}/automodel/jobs`.

Optional `integrations` (W&B / MLflow) use the shared `IntegrationsSpec` from `nemo_platform_plugin.integrations`. Example: `plugins/nemo-automodel/tests/fixtures/integrations_wandb_mlflow.json`. Field reference: customizer skill `references/hyperparameters.md` § **Integrations (automodel + unsloth)**.
