# NeMo Setup Configuration

Load this reference when the user asks about local data paths, coding-agent skill installation, or setup configuration details outside the fast path.

## Local Data Directory

Local platform state includes the entity-store DB, encryption key, and files-service uploads.

Resolution order:

1. `NMP_DATA_DIR` exactly as set
2. `$XDG_DATA_HOME/nemo`
3. `~/.local/share/nemo`

If the user picks a custom path, export it before starting services:

```bash
export NMP_DATA_DIR=/custom/path/to/state
```

`nemo setup` persists the choice to `~/.config/nmp/config.yaml` under `local_services.data_dir`.

## Skill Install

`nemo skills list` lists platform-provided skills, but coding agents need those skills installed into their own skill directories. `nemo setup` normally handles this. To refresh manually:

```bash
nemo skills install --agent <claude|cursor|codex|opencode>
```

Install a single skill when only one follow-up workflow is needed:

```bash
nemo skills install --agent claude --skill nemo-agents-optimize
```
