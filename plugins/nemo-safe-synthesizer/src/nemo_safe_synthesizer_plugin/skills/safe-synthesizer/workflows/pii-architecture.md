# PII classification architecture

## Prerequisites

- The job config includes `config.replace_pii`.
- The referenced provider exists in the target workspace and is written as `<workspace>/<provider_name>`.
- Platform jobs can reach the Models service and Inference Gateway.

## Provider Resolution

The plugin resolves `config.replace_pii.globals.classify.classify_model_provider` through Inference Gateway during job compilation. It stores only the provider route path in the task environment and lets the task combine that path with the platform Models service URL at runtime.

## Local Runs

Local runs read the same job spec but can bypass platform input filesets by passing `--data-source <local-file-or-dir>`. Provider-backed PII classification still needs a reachable endpoint or an equivalent local environment.

## Next Steps

- Configure provider fields with `workflows/config.md`.
- Run PII-only examples from `workflows/config-runs.md`.
- Diagnose endpoint failures with `workflows/diagnose.md`.
