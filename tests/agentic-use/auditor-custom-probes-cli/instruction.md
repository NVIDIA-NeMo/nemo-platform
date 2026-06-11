# Custom Audit with Selected Probes (CLI)

You have access to the `nmp` CLI for NeMo Platform operations. Note: MCP tools are not available in this environment - you must use the CLI.

The `nmp` CLI is available at `/app/.venv/bin/nmp`. The CLI connects to the local NeMo Platform API server at http://localhost:8080 by default. CLI auth is pre-configured.

## Context

An inference provider named `nvidia-inference` has been pre-configured in this environment with model access via NVIDIA's inference API. You can use this provider when creating audit targets.

## Task

Using the `nmp` CLI, create a custom audit configuration with specific selected probes, create an audit target, and run an audit with that custom config:

1. **Explore available global audit configs** to understand the config structure and available options
2. **Create an audit target** named `custom-audit-target` that references model `aws/anthropic/bedrock-claude-sonnet-4-5-v1` through the `nvidia-inference` provider
3. **Create a custom audit config** named `custom-probes-config` with description `Custom config with selected probes` that uses exactly these three probes: `dan.DanInTheWild`, `dan.AutoDANCached`, and `dan.Ablation_Dan_11_0`
4. **Verify the config** by retrieving it and confirming the probe selection
5. **Run an audit** using the `custom-probes-config` config and the `custom-audit-target` target
6. **Review the CLI output** for result artifact paths or errors

Note: The audit may take a long time to complete in this environment. If the local Garak runtime is unavailable, capture the CLI error after invoking the audit command. The important thing is that the target and custom config are created correctly and that the audit command is invoked with both of them.

## Available CLI Commands

```bash
# Create an audit target
nmp auditor targets create <name> -d '{"model": "<model-name>", "type": "<type>", "options": {"provider": "<provider-name>"}}'

# Create an audit config
nmp auditor configs create <name> -d '{"description": "<description>", "system": {"lite": true}, "run": {"generations": 5}, "plugins": {"probe_spec": "dan.DanInTheWild,dan.AutoDANCached,dan.Ablation_Dan_11_0"}, "reporting": {}}'

# Verify configs and targets
nmp auditor configs get <name>
nmp auditor targets get <name>

# Run an audit locally
nmp auditor audit run --spec '{"config": "default/<config-name>", "target": "default/<target-name>"}'
```

## Success Criteria

The task is complete when:
- An audit target named `custom-audit-target` exists referencing the model through the provider
- An audit config named `custom-probes-config` exists with the three specified probes
- The audit run command has been invoked with the custom config and target
- The CLI output has been reviewed for result artifact paths or errors
