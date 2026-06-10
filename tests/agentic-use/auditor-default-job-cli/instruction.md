# Run Default Audit (CLI)

You have access to the `nmp` CLI for NeMo Platform operations. Note: MCP tools are not available in this environment - you must use the CLI.

The `nmp` CLI is available at `/app/.venv/bin/nmp`. The CLI connects to the local NeMo Platform API server at http://localhost:8080 by default. CLI auth is pre-configured.

## Context

An inference provider named `nvidia-inference` has been pre-configured in this environment with model access via NVIDIA's inference API. You can use this provider when creating audit targets.

## Task

Using the `nmp` CLI, create an audit target, create an audit config, and run an audit:

1. **Create an audit target** named `audit-target` that references model `aws/anthropic/bedrock-claude-sonnet-4-5-v1` through the `nvidia-inference` provider
2. **Create an audit config** named `default` with appropriate settings
3. **Run an audit** using the `default` config and the `audit-target` target

Note: The audit may take a long time to complete in this environment. The important thing is that the target and config are created correctly and the audit command is invoked with both of them.

## Available CLI Commands

```bash
# Create the audit target.
nmp auditor targets create audit-target -d '{"model": "aws/anthropic/bedrock-claude-sonnet-4-5-v1", "type": "openai", "options": {"provider": "nvidia-inference"}}'

# Create the default audit config.
nmp auditor configs create default -d '{"system": {"lite": true}, "run": {"generations": 5}, "plugins": {"probe_spec": "dan.AutoDANCached,goodside"}, "reporting": {}}'

# Run the audit locally.
nmp auditor audit run --spec '{"config": "default/default", "target": "default/audit-target"}'
```

## Success Criteria

The task is complete when:
- An audit target named `audit-target` exists referencing the model through the provider
- An audit config named `default` exists
- The audit run command has been invoked with the default config and audit target
