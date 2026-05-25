<a id="nemo-ms-cli"></a>
# {{platform_name}} CLI

The {{platform_name}} CLI (`nemo`) is a command-line tool for interacting with {{platform_name}}. It provides a unified interface for managing models, running jobs, deploying inference endpoints, and working with a local setup.

## Key Capabilities

- **API Operations** - Manage models, jobs, workspaces, and other resources
- **Local Setup** - Configure local services, providers, and SDK context with a single command
- **Multiple Output Formats** - Table, JSON, YAML, CSV, and Markdown for integration with other tools
- **Context Management** - Switch between multiple environments (dev, staging, prod) seamlessly
- **Shell Completion** - Tab completion for Bash, Zsh, and Fish

## Installation

!!! note "This package downloads and installs additional third-party open source software projects. Review the license terms of these open source projects before use."
    If you previously installed the `nemo-microservices` package, uninstall it first to avoid conflicts:

    pip uninstall nemo-microservices
### Install in a Virtual Environment

```bash
pip install nemo-platform[services]
```

Or with uv:

```bash
uv pip install nemo-platform[services]
```

!!! warning "When installed in a virtual environment, the `nemo` command is only available when the environment is activated."

### Verify Installation

```bash
nemo --help
```

If you see `Unknown command: nemo`, see the [troubleshooting](troubleshooting.md) page.

## Getting Started

### 1. Configure the CLI

Set up your connection:

```bash
nemo config set --base-url https://nmp.example.com
nemo auth login
```

### 2. Verify Your Connection

```bash
nemo workspaces list
```

This command outputs a list of available workspaces. If the connection fails, see [troubleshooting](troubleshooting.md) for common issues and solutions.

## Command Structure

The CLI follows a consistent pattern:

```
nemo [GLOBAL OPTIONS] <command> [<subcommand>...] [OPTIONS]
```

--8<-- "_snippets/cli-summary.md"

## Common Workflows

### Exploring Commands

Use `--help` on any command to see available options and subcommands:

```bash
# See all available commands
nemo --help

# See subcommands for a specific resource
nemo models --help

# See options for a specific command
nemo models list --help
```

### Local Setup

```bash
# Set up the platform (interactive wizard)
nemo setup

# Check if services are running
curl -s http://localhost:8080/health/ready

# View service logs
cat ~/.local/state/nmp/instances/<scope>/services.log

# Stop services
pkill -f "nemo services run"
```

## Integrating with Other Tools

The CLI outputs JSON with `-f json`, making it easy to integrate with tools like `jq`, shell scripts, and CI/CD pipelines.

### Filtering with jq

```bash
# Get just the model names
nemo models list -f json | jq -r '.data[].name'

# Find models matching a pattern
nemo models list -f json | jq -r '.data[] | select(.name | contains("nvidia"))'
```

### CSV Export

```bash
# Export to CSV for spreadsheets
nemo models list -f csv --all-pages --no-truncate --output-columns all > models.csv
```

## Next Steps
- [configuration](configuration.md) - Contexts, authentication, environment variables, and shell completion
- [working-with-resources](working-with-resources.md) - Output formats, pagination, and input methods
- [troubleshooting](troubleshooting.md) - Common issues and solutions
- [reference](reference.md) - Full command reference
