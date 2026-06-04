# Working with Resources

This page covers how to list, view, and create resources with the CLI.

## Output Formats

Control how output is displayed with the `--output-format` (or `-f`) option.

### Table (Default for Lists)

Human-readable table format, ideal for interactive use:

```bash
nemo workspaces list
nemo workspaces list -f table
```

### JSON

Machine-readable JSON, ideal for scripting and piping to `jq`:

```bash
nemo workspaces list -f json
nemo workspaces get default -f json | jq '.id'
```

### YAML

YAML output, useful for configuration files:

```bash
nemo workspaces get default -f yaml > workspace.yaml
```

### CSV

Comma-separated values for spreadsheets and data analysis:

```bash
nemo workspaces list -f csv > workspaces.csv
```

### Markdown

Markdown table format, useful for documentation:

```bash
nemo workspaces list -f markdown
```

## Pagination

List commands return paginated results. By default, only the first page is shown.

### Page Size

Control how many items per page with `--page-size`:

```bash
nemo workspaces list --page-size 50
```

### Fetch All Pages

Use `--all-pages` to fetch all results (with a progress indicator):

```bash
nemo workspaces list --all-pages
```

### Manual Pagination

For page-based endpoints, use `--page` to fetch a specific page:

```bash
nemo workspaces list --page 1
nemo workspaces list --page 2
```

## Output Columns

Control which columns appear in table, CSV, and Markdown output.

### Default Columns

By default, the CLI shows the most commonly needed columns:

```bash
nemo workspaces list
```

### All Columns

Use `--output-columns all` to show all available columns:

```bash
nemo workspaces list --output-columns all
```

### Specific Columns

Specify exactly which columns to display:

```bash
nemo workspaces list --output-columns "id,name,created_at,updated_at"
```

## Truncation

By default, long values are truncated in table, CSV, and Markdown output. Use `--no-truncate` to show full values:

```bash
nemo workspaces list --no-truncate
```

## Full Export

For complete data export, combine `--all-pages`, `--output-columns all`, and `--no-truncate`:

```bash
nemo workspaces list -f csv --all-pages --output-columns all --no-truncate > workspaces.csv
```

## Timestamps

Control how timestamps are displayed with `--timestamp-format`.

### Relative (Default)

Shows time relative to now:

```bash
nemo --timestamp-format relative workspaces list
# created_at: 2 hours ago
```

### ISO 8601

Shows full ISO 8601 timestamps:

```bash
nemo --timestamp-format iso8601 workspaces list
# created_at: 2024-01-15T10:30:00Z
```

## Input Methods

Commands that create or update resources accept input in several ways.

### From a File

Create a JSON or YAML file with your resource definition (`workspace.json`):

```json title="workspace.json"
{
  "name": "my-workspace",
  "description": "My workspace for testing"
}
```

Then use `--input-file` to read from it:

```bash
nemo workspaces create my-workspace --input-file workspace.json
```

### From Stdin

Use `--input-file -` to read from stdin. This is useful for piping data from other commands:

```bash
cat workspace.json | nemo workspaces create my-workspace --input-file -
```

### Inline Data

Use `--input-data` to provide JSON or YAML directly on the command line:

```bash
nemo workspaces create my-workspace --input-data '{"description": "My workspace for testing"}'
```

### CLI Options

Many fields can be set directly as command options:

```bash
nemo workspaces create my-workspace
```

### Combining Methods

You can combine a base file with CLI options. CLI options override values from the file:

```bash
# Start with base config, override the name
nemo workspaces create custom-workspace --input-file workspace.json
```
