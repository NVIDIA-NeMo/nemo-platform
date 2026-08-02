---
name: iron-swarm
description: >
  NeMo Iron Swarm CLI reference for red-teaming and hardening NAT agents.
  Use when the task involves attacking, red-teaming, hardening, or running a security
  war-game against an agent, or any `nemo iron-swarm` CLI command.
---

# NeMo Iron Swarm CLI Reference

Iron Swarm runs a security war-game against a NAT agent: garak attackers probe a sandboxed copy
of the agent, defenders harden it (OpenShell policy + workflow guardrails), and validators replay
the attacks plus benign traffic to confirm the fix. Point it at an agent registered in NeMo Platform
(it does not have to be deployed) or at a local NAT project — no manual manifest editing either way.

## Prerequisites

Iron Swarm needs Docker and an OpenShell gateway, and runs in its own isolated venv. Provision
once per host, then verify:

```bash
# Provision iron-swarm's dedicated venv and check host prerequisites
nemo iron-swarm setup

# Read-only preflight: venv present, Docker daemon up, OpenShell gateway connected
nemo iron-swarm doctor
```

`setup` provisions the Python venv for you. Host-level prerequisites (Docker, the OpenShell
gateway) are checked and the exact install command is printed if missing — they are never
silently installed (they need sudo/brew/systemd).

## Typical flow

Three steps, in this order. **`synth-benign` is not optional** — see below.

```bash
# 1. Save a target. It prints the manifest id every later command takes.
nemo iron-swarm init --agent <agent-name>
nemo iron-swarm init --agent <agent-name> --egress <host>      # if the agent calls the internet

# 2. Generate the benign suite (required, cached on the manifest)
nemo iron-swarm synth-benign --manifest-id <id> --yes

# 3. Run the war-game, then inspect it
nemo iron-swarm run --manifest-id <id>
nemo iron-swarm status --limit 5

# Later: the agent changed and you want the manifest to catch up
nemo iron-swarm refresh --manifest-id <id>
```

For agent source, the agent must already be registered in NeMo Platform — confirm with
`nemo agents list`. It does not need to be deployed; the war-game builds its own victim.

### Targeting a local NAT project instead

```bash
nemo iron-swarm init --project-dir <path>          # asks about workflow, port, secrets
nemo iron-swarm init --project-dir <path> --yes    # CI: accept detected answers
```

This runs iron-swarm's own interactive `init` in the terminal, then uploads the project and saves
the result. From there the flow is identical — same `--manifest-id`. The project supplies its own
dependencies, so its `pyproject.toml`/`requirements.txt` must include `nvidia-nat`.

Secrets and credentials are never uploaded: the victim's secrets come from the platform secret
store, resolved by the names in the manifest.

## `synth-benign` is required

The war-game validates two things: that attacks are blocked, **and** that ordinary requests still
work. Those ordinary requests are the *benign suite*, and `run` is a pure consumer of it — it never
generates one. Without a suite the run fails immediately with
`smart-benign validation requires an explicit benign suite`.

Generate it once and it is cached on the manifest for every later run:

```bash
nemo iron-swarm synth-benign --manifest-id <id>                  # interview, you answer
nemo iron-swarm synth-benign --manifest-id <id> --yes            # interview, defaults accepted
nemo iron-swarm synth-benign --manifest-id <id> --no-interactive # CI: rules only
```

## Two ways to run

- **`run --manifest-id <id>`** — the normal path. Looks up the cached benign suite by id.
- **`run --config <file>`** — a hand-authored `iron-swarm.yaml` against a local project. There is no
  cache to look up, so it also needs `--benign-suite <csv>`.

`init -o` writes a *rendering* of the manifest for reading; editing that file changes nothing, since
the run uses the saved manifest.

## Manifests are frozen targets

`init` resolves the agent once and stores the result, so every run war-games the same thing — which
is what makes two runs comparable. Editing the agent afterwards does **not** change an existing
manifest. Take the change deliberately:

```bash
nemo iron-swarm refresh --manifest-id <id>
```

Egress, secrets, models, defenders and the cached benign suite are preserved; only the target is
rebuilt. Not needed after `apply-mitigation`, which refreshes the manifest itself so
`run → harden → apply → run` measures the change just applied.

Do not report a manifest as picking up an agent edit without a `refresh` (or an `apply`) between them.

## Egress: the silent-failure trap

The sandbox drops outbound traffic that is not allow-listed, and a blocked host **hangs** rather
than erroring. The agent's LLM then answers from its own knowledge, so the run looks like it passed
while the tool path — the thing Iron Swarm exists to attack — was never exercised.

Pass `--egress <host>` at `init` for every external host the agent reaches. A bare host opens
**443 only**; write `host:80` for plain HTTP. Hosts cannot be auto-discovered for a config-only
agent, because its tool code lives in an installed package rather than in the project.

## Environment variables vs secrets

`--env KEY=VALUE` (repeatable) sets non-secret env vars on the victim; only the first `=` splits.
Values are stored in plaintext on the manifest, so credentials must use `--secrets` instead, which
stores only the names and resolves values from the platform Secrets store at run time. Never suggest
putting an API key in `--env`.

## Notes

- Models default to iron-swarm's built-ins and the victim's own LLM resolves through the platform
  Inference Gateway. Three overridable groups: **attack** (garak red-team + detector), **analysis**
  (defenders + the benign validator's synth suite-generation and judge), and **agent** (the victim's
  own LLM). Set them as the manifest's stored default or per-run; a custom endpoint's key is supplied
  by name from the Secrets store. A chosen model is preflighted before the sandbox spins up, and the
  run fails fast (listing the reachable models) on a bad name/key/URL.
- Workflow `model_name` values must be entity names the platform knows (lowercase letters, digits,
  hyphens) — a provider id like `vendor/model-name` is rejected for the slash.
- After a run produces mitigations, freeze a chosen subset and replay the recorded attacks:
  `nemo iron-swarm sanity-check --manifest-id <id> --mitigations <json> --replay-hitlog <ref> --keep <id>`
- A war-game makes many LLM calls and bills a real key. Say so before starting long or repeated runs.
- The war-game requires a host with Docker + OpenShell; the run job fails preflight with a clear
  message otherwise. Do not report a run successful without verifying its status.
