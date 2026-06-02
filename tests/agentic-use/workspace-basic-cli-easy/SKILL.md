---
name: workspace-basic-cli-easy
description: Use the NeMo Platform CLI to create and verify a basic workspace.
---

# Workspace Creation Test (CLI)

You have access to the `nemo` CLI for NeMo Platform operations. Note: MCP tools are not available in this environment - you must use the CLI.

## Task

Complete the following workspace operations using the `nemo` CLI:

1. Create a workspace named `harbor-test-workspace` with a description of your choice
2. Verify the workspace exists by listing all workspaces

## Available CLI Commands

The `nemo` CLI is available at `/app/.venv/bin/nemo`. You can use these commands:

- `nemo workspaces create <name> --description <description>` - Create a new workspace
- `nemo workspaces list` - List all workspaces
- `nemo workspaces get <name>` - Get a specific workspace
- `nemo workspaces delete <name>` - Delete a workspace

Note: The CLI connects to the local NeMo Platform API server at http://localhost:8080 by default.

## Success Criteria

The task is complete when:
- The workspace `harbor-test-workspace` has been successfully created
- The workspace appears in the workspace list when you list all workspaces
