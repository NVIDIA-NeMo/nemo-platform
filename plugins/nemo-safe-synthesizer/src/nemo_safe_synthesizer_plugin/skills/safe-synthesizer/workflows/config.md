# Configuring Safe Synthesizer

Reference for the job spec fields the plugin accepts. For runnable examples, read `workflows/config-runs.md`. For provider resolution details, read `workflows/pii-architecture.md`.

## Job Spec Schema

```json
{
  "data_source": "default/my-input#input.csv",
  "config": {}
}
```

## Plugin Convenience Flags

The plugin accepts these fields inside `config` and maps them into the Safe Synthesizer runtime config:

- `enable_synthesis`: set to `false` to run only data processing / PII replacement without training and generation.
- `enable_replace_pii`: set to `false` to disable the default PII replacement pipeline.

See `workflows/config-runs.md` for "How to run PII-only and generation runs".

## Data Sources

- Platform jobs: use fileset URLs, e.g. `default/customer-data#input.csv`.
- Supported local file forms include CSV, Parquet, JSON, JSONL, and Hugging Face datasets paths.

## PII Classification Provider

When PII classification uses a model provider, set `classify_model_provider` as `<workspace>/<provider_name>`.

```json
{
  "data_source": "default/my-input#input.csv",
  "config": {
    "replace_pii": {
      "globals": {
        "classify": {
          "classify_model_provider": "default/my-nim"
        }
      },
      "steps": [{}]
    }
  }
}
```

See `workflows/pii-architecture.md` for "PII classification architecture".

## Secrets

Use `hf_token_secret` at the top level of the job spec when model initialization needs a Hugging Face token from the platform secrets service.
