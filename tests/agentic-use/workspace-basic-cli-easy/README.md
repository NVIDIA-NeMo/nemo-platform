# Workspace Basic CLI Test

This ACES Harbor Docker test verifies that an agent can create and list workspaces using the `nemo` CLI.

## Purpose

This test demonstrates that the `nemo` CLI is properly installed and functional in the Harbor test environment, and that Claude Code can successfully use CLI commands to interact with the NeMo Platform.

## Difference from workspace-basic-mcp

- **workspace-basic-mcp**: Uses MCP tools (Model Context Protocol) for workspace operations
- **workspace-basic-cli**: Uses the `nemo` CLI directly via bash commands

Both tests verify the same outcome (workspace creation), but through different interfaces.

**Important:** This test disables MCP by removing `/app/.mcp.json` in the Dockerfile, ensuring Claude Code must use the CLI.

## Test Flow

1. `astra-skill-eval` emits Harbor tasks from `evals/evals.json`
2. The selected agent receives instructions to create a workspace using the `nemo` CLI
3. The agent executes: `nemo workspaces create harbor-test-workspace --description "..."`
4. The agent verifies by listing: `nemo workspaces list`
5. ACES default metrics score the trajectory, and the custom pytest metric checks the API state

## CLI Commands Used

```bash
# Create a workspace
nemo workspaces create harbor-test-workspace --description "Test workspace"

# List workspaces
nemo workspaces list

# Get a specific workspace
nemo workspaces get harbor-test-workspace
```

## Run with ACES Harbor

```bash
docker build -f /Users/ngoncharenko/code/microservices/nemo-platform/Dockerfile.agentic-base \
  -t nmp-agentic-base:latest \
  /Users/ngoncharenko/code/microservices/nemo-platform

ASTRA_SKILL_EVAL_DEBUG=1 \
astra-skill-eval evaluate /Users/ngoncharenko/code/microservices/nemo-platform/tests/agentic-use/workspace-basic-cli-easy \
  --agent-eval -a codex \
  --results-dir /tmp/astra-results \
  --harbor-keep-jobs \
  --env-mode docker
```

This task uses `grading.mode: aces_plus_custom`: normal ACES scoring and
baseline lift remain enabled, and the pytest verifier appears as the
`nemo_workspace_pytest` custom metric.
