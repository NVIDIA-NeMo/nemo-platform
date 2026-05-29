# Skills Impact on Agentic Evals

Tracking the impact of Claude Code skills on non-easy CLI eval performance.

## Results

Results across two runs. First batch had 7 infra failures (agent ran as root) which were fixed with `runuser -u harbor` in entrypoints, then rerun.

| Eval | Baseline | With Skills | Time | Skills Invoked |
|------|----------|-------------|------|----------------|
| auditor-config-crud-cli | 0.0 (1:12) | **1.0** | 5:08 | nemo-auditor |
| auditor-default-job-cli | - | **1.0** | 2:29 | nemo-auditor |
| auditor-target-crud-cli | - | **1.0** | 3:19 | nemo-auditor |
| auth-authorization-cli | - | **1.0** | 4:40 | nemo-auth |
| data-designer-config-cli | - | **1.0** | 2:28 | nemo-secrets, nemo-inference-providers |
| entities-basic-cli | - | **1.0** | 2:24 | nemo-entities |
| files-crud-cli | 0.0 (3:05) | **1.0** | 4:34 | nemo-files |
| files-upload-dataset-cli | - | **1.0** | 3:07 | nemo-files |
| guardrails-content-safety-cli | 1.0 (3:24) | **1.0** | 2:08 | nemo-guardrails |
| guardrails-custom-config-cli | 0.0 (13:17) | **1.0** | 7:26 | nemo-secrets, nemo-inference-providers, nemo-guardrails |
| inference-chat-completions-cli | - | **1.0** | 3:09 | nemo-inference-gateway |
| inference-igw-provider-cli | - | 0.0 | 0:31 | (infra: root user, fixed) |
| inference-mockllm-cli | - | **1.0** | 1:59 | nemo-inference-providers, nemo-inference-gateway |
| inference-provider-reg-cli | 0.0 (3:07) | **1.0** | 3:57 | nemo-secrets, nemo-inference-providers |
| secrets-crud-cli | 0.0 (3:05) | **1.0** | 3:54 | nemo-secrets |
| workspace-basic-cli | - | **1.0** | 1:24 | nemo-auth |

**Summary**: Historical snapshot retained for the remaining CLI evals after retired evaluator CLI tasks were removed.

## Key Findings

1. **Skills dramatically improve pass rate**: Where we have baselines, skills turned 0.0 failures into 1.0 passes (auditor-config-crud, files-crud, guardrails-custom-config, inference-provider-reg, secrets-crud)
2. **Skill invocation requires instruction hints**: The agent reliably invokes skills when the instruction.md says "You have skills available for X. Use them before exploring --help."
3. **Root user bug**: Harbor's agent setup re-installs Claude Code as root. Fixed by adding `exec runuser -u harbor` to all ENTRYPOINT scripts.

## Skills Created

| Skill | Description | Evals Using It |
|-------|------------|----------------|
| nemo-secrets | Secrets CRUD | secrets-crud, data-designer-config, guardrails-custom-config, inference-provider-reg |
| nemo-inference-providers | Provider setup + update-status | data-designer-config, guardrails-custom-config, inference-provider-reg, inference-mockllm |
| nemo-inference-gateway | Chat completions, provider gateway, mock providers | inference-chat-completions, inference-mockllm |
| nemo-guardrails | Guardrail config + self-check rails | guardrails-content-safety, guardrails-custom-config |
| nemo-auditor | Audit configs, targets, jobs, probes | auditor-config-crud, auditor-default-job, auditor-target-crud |
| nemo-files | Filesets, upload/download, datasets | files-crud, files-upload-dataset |
| nemo-entities | Entity CRUD (model, dataset types) | entities-basic |
| nemo-auth | Workspaces + member management | auth-authorization, workspace-basic |
