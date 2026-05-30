---
name: nemo-setup
description: Set up or start a local NeMo Platform with `make bootstrap` and `nemo setup`; use for install, bootstrap, local services, provider setup, skill install, or demo-agent deployment.
version: "0.1"
metadata:
  owner: nemo-platform
  maturity: active
license: Apache-2.0
---

# NeMo Platform Setup

Get a local NeMo Platform running on `localhost:8080`. Optimize for completing setup, not for stopping at preflight questions. Use safe defaults unless the user asks for a destructive reset or a running process blocks startup.

This is the canonical setup guide at `skills/nemo-setup/SKILL.md`. It is not installed by `nemo skills install` because agents need it before the platform is bootstrapped.

## Purpose

Use this skill when the user asks to install, bootstrap, set up, run, start, or repair a local NeMo Platform checkout. The expected successful outcome is:

1. dependencies are bootstrapped,
2. local services are reachable at `http://localhost:8080`,
3. provider/skills/demo-agent setup is attempted when credentials are available, and
4. the user receives concise next-step options.

## Prerequisites

- Python 3.11-3.13, Git, GNU Make, and `uv`.
- Node.js and `pnpm` matching `web/package.json` for Studio assets. If Studio asset bootstrap fails, the API can still run.
- Optional provider credential for non-interactive provider setup. Supported env vars include `NVIDIA_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, and `NEMO_DEFAULT_INFERENCE_KEY`.

Do not print secret values. Do not run broad environment dumps such as `env`, `printenv`, or `set`. To check whether a key exists, print only presence:

```bash
test -n "${NVIDIA_API_KEY:-}" && echo "NVIDIA_API_KEY is set"
```

## Default Policy

- Data directory: use the CLI default, usually `~/.local/share/nemo`.
- Existing local DB: preserve it by default.
- `NMP_BASE_URL`: set `http://localhost:8080` before local CLI verification so a remote config file cannot hijack commands.
- Destructive actions: ask before deleting the data directory or killing a running platform process.
- Completion: setup is not complete until local services are verified and next-step options are offered.

Do not ask the user to choose a data directory or DB reset for the normal fresh setup path. Ask only when the user requested a custom path/reset, or when an existing process or corrupted state requires a choice.

## Fast Path

Run from the repo root.

1. Check for an existing local platform or port conflict:

```bash
lsof -iTCP:8080 -sTCP:LISTEN || true
ps -ef | grep "nemo services run" | grep -v grep || true
```

If a healthy NeMo Platform is already running, keep it and go straight to verification. If a stale `nemo services run` process or a non-NeMo process owns port 8080, show the PID/command and ask before killing it.

2. Bootstrap dependencies:

```bash
make bootstrap
```

3. Activate the environment and force the CLI to target the local platform:

```bash
source .venv/bin/activate
export NMP_BASE_URL=http://localhost:8080
```

4. Run setup.

If a provider credential is present, prefer the non-interactive completion path:

```bash
nemo setup --auto --start-services --install-skills --deploy-agent
```

If no provider credential is present, still start local services and install skills where possible:

```bash
nemo setup --start-services --install-skills --no-deploy-agent
```

If that command becomes interactive and blocks for provider input, stop the interactive prompt, report that services can run but provider registration needs a key, and tell the user which env vars are supported.

## Verification

Verify local reachability before reporting success:

```bash
nemo workspaces list
nemo services status
```

Do not use `curl /v1/workspaces`; that path can return 404 even when the platform is healthy.

If the demo agent was deployed, verify it:

```bash
nemo agents list
nemo agents invoke --agent calculator-agent --input "What is 12 * 8?"
```

When verification passes, state that the platform is running at `http://localhost:8080`.

## Reset Path

Use this only when the user explicitly asks to reset local state, accepts a fresh setup, or a concrete stale-state error requires it.

1. Ask for confirmation before deleting data. Warn that this removes local platform state, secret metadata, and the local encryption key.
2. Stop any running `nemo services run` process first. Deleting files while the process is alive can leave macOS with an unlinked open DB file.
3. Delete the selected data directory contents only after confirmation. The default target is `~/.local/share/nemo`, unless `NMP_DATA_DIR` or `XDG_DATA_HOME` changes the active path.
4. Rerun the fast path from bootstrap/setup through verification.

## Troubleshooting

For custom data paths or coding-agent skill install details, read [Configuration](references/configuration.md). For service-only startup, read [Manual Startup](references/manual-start.md). For Switchyard routing, middleware, or VirtualModel plugin loading, read [Switchyard](references/switchyard.md). For stale DB/encryption-key failures, port conflicts, and default-model 422s, read [Troubleshooting](references/troubleshooting.md). Do not load any reference during the normal fast path unless one of those issues appears.

## What's Next

After setup is verified, offer a short menu based on the user's goal:

- optimize an agent: use `nemo-agents-optimize`
- secure an agent: use `nemo-agents-secure`, `nemo-guardrails`, or `nemo-auditor`
- run inference or choose a model: use `inference`
- evaluate a model or agent: use `nemo-evaluator` or `nemo-evaluator-plugin`
- generate synthetic data: use `nemo-data-designer-plugin`
- deploy or invoke an agent: use the agent build/deploy skills

If the user has not stated a next goal, ask: "The platform is up. What would you like to do next: optimize an agent, deploy one, run inference, evaluate, generate data, or something else?"
