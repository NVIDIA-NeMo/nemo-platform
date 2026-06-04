# Configuration

The NeMo CLI uses a configuration file to store connection settings, credentials, and preferences. This allows you to work with multiple environments and switch between them easily.

## Quick Setup

The quickest way to connect to an existing deployment is:

```bash
# Set base URL and authenticate in one command
nemo auth login --base-url https://nmp.example.com
```

To configure a named context:

```bash
nemo --context prod auth login --base-url https://nmp.prod.example.com
```

## Configuration File

The configuration is stored in `~/.config/nmp/config.yaml`. If the `XDG_CONFIG_HOME` environment variable is set, the file is stored in `$XDG_CONFIG_HOME/nmp/config.yaml` instead. You can also specify a custom location with the `NMP_CONFIG_FILE` environment variable.

## Managing Configuration

### View Configuration

Display configuration for the current context (secrets are redacted):

```bash
nemo config view
```

Display all contexts:

```bash
nemo config view --all-contexts
```

### Switch Contexts

Inspect the currently active context and resolved references:

```bash
nemo config view
```

Or print only the current context name:

```bash
nemo config current-context
```

Switch to a different context:

```bash
nemo config use-context prod
```

Use a context for a single command without switching:

```bash
nemo --context prod workspaces list
```

### Modify Configuration

Set specific values:

```bash
nemo config set --base-url https://nmp.example.com
nemo config set --workspace my-workspace
nemo config set --access-token -
```

When setting an access token, you'll be prompted to enter it securely (input is hidden).

## Environment Variables

Environment variables override configuration file settings. This is useful for CI/CD pipelines or temporary overrides.

| Variable | Description |
|----------|-------------|
| `NMP_CONFIG_FILE` | Path to configuration file |
| `NMP_CURRENT_CONTEXT` | Override current context |
| `NMP_BASE_URL` | API base URL |
| `NMP_ACCESS_TOKEN` | Access token for authentication |
| `NMP_WORKSPACE` | Default workspace |
| `NMP_OUTPUT_FORMAT` | Output format (table, json, yaml, csv, markdown) |
| `NMP_TIMESTAMP_FORMAT` | Timestamp format (relative, iso8601) |
| `NMP_COLOR_OUTPUT` | Enable/disable colored output (true/false) |

Example:

```bash
# Use a different context for this command
NMP_CURRENT_CONTEXT=prod nemo workspaces list

# Override base URL
NMP_BASE_URL=https://nmp.example.com nemo models list
```

## Configuration Precedence

Settings are resolved in this order (highest priority first):

1. **Command-line flags** - `--base-url`, `--context`, etc.
2. **Environment variables** - `NMP_BASE_URL`, `NMP_CURRENT_CONTEXT`, etc.
3. **Configuration file** - `~/.config/nmp/config.yaml`
4. **Defaults** - Built-in default values

This means you can set defaults in your config file and override them as needed with environment variables or flags.

## Shell Completion

The NeMo CLI supports tab completion for Bash, Zsh, and Fish shells. Enable it with:

```bash
nemo --install-completion
```

This detects your current shell and installs the appropriate completion script. Restart your shell for the changes to take effect.

After installation, test that completion is working:

```bash
nemo <Tab>
nemo models <Tab>
```

If completion isn't working, make sure you've restarted your shell and that your shell supports programmable completion. For Bash, ensure `bash-completion` is installed on your system.
