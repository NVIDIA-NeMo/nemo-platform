# Secure Agents

<a id="agents-security"></a>

Use the agent security workflow to check a deployed agent for guardrail
coverage and sensitive data exposure before you promote it. The workflow looks
at whether model traffic is routed through guardrails, samples recent
telemetry for PII and leaked secrets, and writes actionable suggestions you
can review alongside optimization suggestions.

## What the Security Workflow Checks

| Suggestion type | Signal | Result |
|-----------------|--------|--------|
| Guardrails | Agent LLMs call an unguarded model endpoint | Suggests creating a guarded virtual model and pointing the agent at it |
| Data safety | Recent telemetry contains likely PII or leaked secrets | Suggests redaction or regeneration and immediate credential rotation for secrets |
| Deep scan | Regex scanning is not enough for the data risk profile | Suggests running higher-recall GLiNER or NemoGuard model checks on a subset of traces |

Security state is stored separately from optimization state:

- `nemo-agent-security/security_snapshot.json`
- `nemo-agent-security/security_suggestions.jsonl`

## Prerequisites

Before running security checks, make sure you have:

1. Local services running (`nemo services run`).
1. At least one deployed platform-managed agent.
1. A model provider and model entities registered in the workspace.
1. Optional telemetry in the `nemo-agent-telemetry` fileset if you want data
   safety suggestions.

## Add Guardrails to the Model Path

Guardrails attach to an agent through a **guarded virtual model**: a
VirtualModel entity that uses a guardrail configuration to run input and
output rails on every call to the main model. Pointing the agent at the
guarded VirtualModel — instead of at the raw main model entity — secures the
agent's model path without changing its workflow logic.

Common catalog models to use as the guardrail backend (verify availability
with `nemo models list`):

- `nvidia-llama-3-1-nemoguard-8b-content-safety`
- `nvidia-llama-3-1-nemoguard-8b-topic-control`
- `nvidia-llama-3-1-nemotron-safety-guard-8b-v3`

For how to create the guardrail config that the virtual model references, see
the [Guardrails documentation](../guardrails/index.md).

There are two steps: create the guarded VirtualModel, then update the agent's
`llms` block to reference it.

### 1. Create a Guarded VirtualModel

=== "CLI"

    ```bash
    nemo inference virtual-models create guarded-agent-model \
      --workspace default \
      --models '[{"model":"default/<main-model-entity>","backend_format":"OPENAI_CHAT"}]' \
      --request-middleware '[{
        "name":"nemo-guardrails",
        "config_type":"guardrail_config",
        "config_id":"default/<guardrail-config>"
      }]' \
      --response-middleware '[{
        "name":"nemo-guardrails",
        "config_type":"guardrail_config",
        "config_id":"default/<guardrail-config>"
      }]'
    ```

    Wire the same `<guardrail-config>` on both `--request-middleware` (for
    input rails) and `--response-middleware` (for output rails). Omit a side
    if the config defines no flows for it. For the full middleware schema,
    entity-backed vs inline configs, and caching behavior, refer to
    [Guardrails Architecture](../guardrails/concepts/architecture.md).

=== "Skill"

    Ask your coding agent:

    > Secure my deployed agent.

    The `agents-secure` skill picks a deployed agent, checks guardrail
    coverage, samples recent telemetry, and writes suggestions to the
    `nemo-agent-security` fileset.

    Verify the skill is installed:

    ```bash
    nemo skills show agents-secure
    ```

    What it does under the hood:

    - Lists deployed agents and prompts you to choose one.
    - Inspects each LLM's `base_url`. If it does not route through a
      guardrails virtual model, suggests creating one with a content-safety,
      topic-control, or safety-guard backend.
    - Names the recommended guardrails catalog model and walks you through
      creating the guarded virtual model.
    - Persists suggestions to the `nemo-agent-security` fileset.

=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    guardrail_mw = {
        "name": "nemo-guardrails",
        "config_type": "guardrail_config",
        "config_id": "default/<guardrail-config>",
    }

    client.inference.virtual_models.create(
        name="guarded-agent-model",
        workspace="default",
        models=[{"model": "default/<main-model-entity>", "backend_format": "OPENAI_CHAT"}],
        request_middleware=[guardrail_mw],
        response_middleware=[guardrail_mw],
    )
    ```

### 2. Point the Agent at the Guarded VirtualModel

In the agent's workflow YAML, set `model_name` on the relevant `llms` entry to
the guarded VirtualModel's entity reference, with slashes converted to hyphens
(per the [agent configuration conventions](index.md#agent-definition)):

```yaml
llms:
  llm:
    _type: openai
    model_name: default-guarded-agent-model
```

Leave `base_url` and `api_key` unset. Once redeployed, every model call from
the agent flows through the guarded VirtualModel — the agent itself is
unchanged and unaware of the rails.

For the end-to-end request flow, streaming behavior, header forwarding, and
the `guardrails` request options, refer to
[Running Inference with Guardrails](../guardrails/concepts/inference.md).

Redeploy the agent, re-run evaluation, and compare quality, cost, latency,
and safety signals against the baseline before promoting.

## Scan Telemetry for Sensitive Data

The security skill samples recent telemetry from `nemo-agent-telemetry` and
looks for high-confidence patterns such as email addresses, SSNs, phone
numbers, credit cards, private keys, JWTs, and common model-provider API keys.
Findings are written with masked previews, file locations, and follow-up
actions.

For leaked secrets, rotate the credential before doing any other cleanup. For
PII in trace data, redact or regenerate affected traces before using them for
evaluation or optimization.

=== "CLI"

    ```bash
    nemo files list nemo-agent-telemetry
    ```

    Inspect the most recent trace files manually, or use the security skill
    to do this for you. Cap the data you download — telemetry can be large.

=== "Skill"

    Ask your coding agent:

    > Scan recent telemetry for my agent for PII and leaked secrets.

    The `agents-secure` skill caps downloaded telemetry at 1 GB and walks the
    most recent traces first. Verify it is installed:

    ```bash
    nemo skills show agents-secure
    ```

    What it does under the hood:

    - Samples recent files from `nemo-agent-telemetry` until the 1 GB cap.
    - Runs a high-confidence regex pass for PII and leaked credentials.
    - Writes findings with masked previews and follow-up actions to
      `nemo-agent-security/security_suggestions.jsonl`.
    - Optionally suggests a higher-recall GLiNER or NemoGuard scan on a
      subset of traces when regex coverage is not enough.

=== "Python SDK"

    The skill drives this workflow directly. To inspect what was written,
    list and download files from the security fileset:

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    for f in client.files.list(fileset="nemo-agent-security"):
        print(f.remote_path)
    ```

## Review Results

Use the Files service to inspect saved suggestions:

```bash
nemo files list nemo-agent-security

nemo files download nemo-agent-security \
  --remote-path security_suggestions.jsonl \
  -o security_suggestions.jsonl
```

## Troubleshooting

**No security suggestions were written.** Confirm the `nemo-agent-security` fileset exists with `nemo files list nemo-agent-security`. If it is empty, the security workflow has not run yet — invoke the `agents-secure` skill or run the checks manually before reviewing.

**No data safety findings appear.** Data safety scans require telemetry. Confirm the `nemo-agent-telemetry` fileset exists with `nemo files list nemo-agent-telemetry`. If the fileset is empty, the agent is not exporting traces — verify the agent uses the `nemo_files` telemetry exporter and that recent invocations have completed.

**The `agents-secure` skill is not available.** Run `nemo skills list` to confirm the skill is installed. If it is missing, install it with `nemo skills install --agent <claude|codex|cursor|opencode>`.

**Guardrail virtual model creation fails with an unknown model.** Confirm the backend model entity exists with `nemo models list`. The `<main-model-entity>` and `<guardrail-config>` placeholders must reference entities the workspace can resolve.

## Next Steps

- [Optimize Agents](optimization.md): reduce cost and improve quality after
  security coverage is in place.
- [Guardrails](../guardrails/index.md): create and manage guardrail
  configurations.
- [Models and Inference](../run-inference/about.md): manage model providers,
  model entities, and virtual models.
