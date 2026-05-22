# Customization Job Reference

<a id="ft-customization-job-reference"></a>
Use this page when you need field-level details for customization job specifications, the complete API schema, or integration options.

For concepts, see [Customization Job overview](index.md).

## Key Fields

All job configuration (model, dataset, training, and output) is specified in the job spec.

| Field | Required | Description |
|-------|----------|-------------|
| `name` | No | Name for this customization job. Auto-generated if not provided |
| `workspace` | Yes | Workspace where the job runs. Determines what datasets and models are authorized to be used in the job. |
| `spec.model` | Yes | Reference to the Model Entity (`workspace/name` format) |
| `spec.dataset` | Yes | Dataset URI (`fileset://workspace/name`) |
| `spec.training` | Yes | Training method and hyperparameters (see [Training Configuration](hyperparameters.md)) |
| `spec.training.type` | Yes | Training method: `sft`, `distillation`, or `dpo` |
| `spec.training.peft` | No | PEFT adapter configuration (e.g., `{"type": "lora", ...}`). Omit for full-weight training |
| `spec.output` | No | Output artifact configuration (`{"name": "..."}`). Auto-generated if not provided |
| `spec.deployment_config` | No | Deployment configuration. Pass a string to reference an existing config by name, or an object with inline NIM deployment parameters (e.g., `{"lora_enabled": true}`). Omit to skip deployment |

---

## Complete API Reference

For generated REST API details, see the [Customizer API Reference](../../api/index.md#tag-customizer) and
search for `CustomizationJobInput`.

---

## Weights & Biases Integration

To enable W&B integration, add the `integrations` configuration:

=== "Python"

    ```python
    job = client.customization.jobs.create(
        name="my-job",
        workspace="default",
        spec={
            "model": "default/llama-3-2-1b",
            "dataset": "fileset://default/my-dataset",
            "training": {"type": "sft", "peft": {"type": "lora"}, "epochs": 3},
            "integrations": {
                "wandb": {
                    "project": "my-finetuning-project",
                    "entity": "my-team",
                    "tags": ["fine-tuning", "llama"],
                    "api_key_secret": "my-wandb-key",
                }
            },
        },
    )
    ```

=== "CLI"

    ```bash
    nemo customization jobs create my-job \
      --workspace default \
      --spec '{
        "model": "default/llama-3-2-1b",
        "dataset": "fileset://default/my-dataset",
        "training": {"type": "sft", "peft": {"type": "lora"}, "epochs": 3},
        "integrations": {
          "wandb": {
            "project": "my-finetuning-project",
            "entity": "my-team",
            "tags": ["fine-tuning", "llama"],
            "api_key_secret": "my-wandb-key"
          }
        }
      }'
    ```

The `api_key_secret` field references a stored secret containing your `WANDB_API_KEY`.
Use the secret name (e.g., `"my-wandb-key"`) to resolve it from the request workspace.
To create the secret, see [Weights & Biases Keys](../../get-started/concepts/manage-secrets.md).

| Field | Description |
|-------|-------------|
| `project` | W&B project name. Defaults to `output.name` if not set |
| `entity` | W&B entity (team or username) |
| `tags` | List of tags for filtering runs |
| `api_key_secret` | Reference to a secret containing `WANDB_API_KEY` |
| `name` | W&B run name. Defaults to the job ID if not provided |
| `notes` | Notes or description for the run |
| `base_url` | Base URL for self-hosted W&B servers (e.g., `https://wandb.mycompany.com`). Omit to use W&B cloud |

To view your training metrics in W&B after the job starts, see [ft-tut-metrics-wandb](../tutorials/metrics.md).

---

## MLflow Integration

To enable MLflow integration:

=== "Python"

    ```python
    job = client.customization.jobs.create(
        name="my-job",
        workspace="default",
        spec={
            "model": "default/llama-3-2-1b",
            "dataset": "fileset://default/my-dataset",
            "training": {"type": "sft", "peft": {"type": "lora"}, "epochs": 3},
            "integrations": {
                "mlflow": {
                    "experiment_name": "llama-finetuning",
                    "tracking_uri": "http://mlflow.example.com:5000",
                }
            },
        },
    )
    ```

=== "CLI"

    ```bash
    nemo customization jobs create my-job \
      --workspace default \
      --spec '{
        "model": "default/llama-3-2-1b",
        "dataset": "fileset://default/my-dataset",
        "training": {"type": "sft", "peft": {"type": "lora"}, "epochs": 3},
        "integrations": {
          "mlflow": {
            "experiment_name": "llama-finetuning",
            "tracking_uri": "http://mlflow.example.com:5000"
          }
        }
      }'
    ```

| Field | Description |
|-------|-------------|
| `experiment_name` | MLflow experiment name. Defaults to `output.name` if not set |
| `tracking_uri` | Set this to the MLflow tracking server URI. This can also be set via `MLFLOW_TRACKING_URI`. |
| `run_name` | MLflow run name. Defaults to the job ID if not provided |
| `tags` | Key-value pairs for filtering runs (e.g., `{"team": "nlp", "task": "sft"}`) |
| `description` | Description for the MLflow run |

## Next Steps

- [Create a customization job](create-job.md): Start a job with a model, dataset, training configuration, and optional integrations.
- [Monitor training metrics](../tutorials/metrics.md): View logs and metrics through MLflow or W&B.
- [Manage secrets](../../get-started/concepts/manage-secrets.md): Store credentials such as W&B API keys and provider tokens.
- [Troubleshooting MLflow integrations](../../troubleshooting/customizer.md): Diagnose failed or misconfigured customization jobs.
