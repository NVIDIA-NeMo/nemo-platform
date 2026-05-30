# NeMo Setup Troubleshooting

Load this reference only when the fast path in `../SKILL.md` fails or the user asks for failure recovery.

## Existing Service Or Port Conflict

Before starting services:

```bash
lsof -iTCP:8080 -sTCP:LISTEN || true
ps -ef | grep "nemo services run" | grep -v grep || true
```

If a healthy NeMo Platform is already running, keep it and verify with `nemo workspaces list`. If the process is stale or the user wants a fresh run, ask before killing exact PIDs.

Safe stop sequence:

1. `kill <pid> [<pid>...]`
2. wait about 10 seconds
3. re-check that each PID still belongs to `nemo services run`
4. use SIGKILL only for those exact still-running PIDs

## Stale DB Or Encryption-Key Errors

If the database and encryption key get out of sync, later runs can fail with errors such as `cryptography.exceptions.InvalidTag`.

Reset only after explicit user confirmation. Warn that reset deletes local platform state, secret metadata, and the local encryption key. Stop `nemo services run` first; on macOS, deleting files while the process is alive can unlink the visible file while the running process keeps writing to the old inode.

## Default Model 422

`NEMO_DEFAULT_MODEL` must be a hyphenated model entity ID from `nemo models list`, for example `default/nvidia-llama-3-3-nemotron-super-49b-v1-5`. The upstream catalog form with slash and dots, such as `nvidia/llama-3.3-nemotron-super-49b-v1-5`, is display-oriented and can be rejected by the gateway.

If `nemo agents invoke ...` fails with HTTP 422 in under a second, check:

```bash
echo "${NEMO_DEFAULT_MODEL:-}"
nemo models list
```

Then choose the entity ID via the `inference` skill.
