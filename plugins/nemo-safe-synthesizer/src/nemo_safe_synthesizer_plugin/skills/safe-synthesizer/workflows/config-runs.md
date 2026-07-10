# How to run PII-only and generation runs

## Prerequisites

- Read `workflows/config.md` for the job spec field reference.
- Resolve the CLI with `workflows/run.md`.
- Use a platform fileset `data_source` for platform jobs or pass `--data-source` for host-local input files.

## Basic Job Spec

=== "Python SDK"

    ```python
    spec = {
        "data_source": "default/my-input#input.csv",
        "config": {},
    }
    ```

=== "CLI"

    ```json
    {
      "data_source": "default/my-input#input.csv",
      "config": {}
    }
    ```

## PII-only Run

=== "Python SDK"

    ```python
    spec = {
        "data_source": "default/my-input#input.csv",
        "config": {
            "enable_synthesis": False,
            "enable_replace_pii": True,
        },
    }
    ```

=== "CLI"

    ```json
    {
      "data_source": "default/my-input#input.csv",
      "config": {
        "enable_synthesis": false,
        "enable_replace_pii": true
      }
    }
    ```

## Generation without PII Replacement

=== "Python SDK"

    ```python
    spec = {
        "data_source": "default/my-input#input.csv",
        "config": {
            "enable_synthesis": True,
            "enable_replace_pii": False,
            "generation": {"num_records": 100},
            "privacy": {"dp_enabled": False},
            "evaluation": {"enabled": True},
        },
    }
    ```

=== "CLI"

    ```json
    {
      "data_source": "default/my-input#input.csv",
      "config": {
        "enable_synthesis": true,
        "enable_replace_pii": false,
        "generation": {
          "num_records": 100
        },
        "privacy": {
          "dp_enabled": false
        },
        "evaluation": {
          "enabled": true
        }
      }
    }
    ```

## PII Classification Provider

=== "Python SDK"

    ```python
    spec = {
        "data_source": "default/my-input#input.csv",
        "hf_token_secret": "hf-token",
        "config": {
            "replace_pii": {
                "globals": {
                    "classify": {
                        "classify_model_provider": "default/my-nim",
                    },
                },
                "steps": [{}],
            },
        },
    }
    ```

=== "CLI"

    ```json
    {
      "data_source": "default/my-input#input.csv",
      "hf_token_secret": "hf-token",
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

## Submit the Spec

Use the Jobs API or SDK for the primary platform-container path. Pass the JSON object above as the `spec` field in the create-job request. Confirm the service is configured for container execution before submission:

```bash
export NEMO_SAFE_SYNTHESIZER_JOB_MODE=container
export NMP_IMAGE_REGISTRY=nvcr.io/nvidia/nemo-platform
export NMP_IMAGE_TAG=<tag>  # match your installed NeMo Platform release
export NEMO_SAFE_SYNTHESIZER_CONTAINER_IMAGE=safe-synthesizer-tasks
```

Use host-local execution only for local CUDA/GPU development or task debugging:

```bash
uv run nemo safe-synthesizer runtime setup
uv run nemo safe-synthesizer run-local \
  --workspace default \
  --spec-file nss-job.json \
  --data-source ./input.csv \
  --output-dir ./nss-output
```

## Next Steps

- Use `workflows/pii-architecture.md` for provider resolution details.
- Use `workflows/results.md` to retrieve outputs.
- Use `workflows/artifacts.md` to interpret `summary` and `summary.json` first.
