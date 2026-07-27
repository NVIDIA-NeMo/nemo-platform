---
name: iron-swarm
description: >
  NeMo Iron Swarm CLI reference for red-teaming and hardening deployed NAT agents.
  Use when the task involves attacking, red-teaming, hardening, or running a security
  war-game against an agent, or any `nemo iron-swarm` CLI command.
---

# NeMo Iron Swarm CLI Reference

Iron Swarm runs a security war-game against a NAT agent: garak attackers probe a sandboxed copy
of the agent, defenders harden it (OpenShell policy + workflow guardrails), and validators replay
the attacks plus benign traffic to confirm the fix. This plugin lets you point Iron Swarm at an
agent you already deployed in NeMo Platform — no project discovery, no manual manifest editing.

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

```bash
# 1. Scaffold a manifest from an already-deployed agent (resolves name -> target automatically)
nemo iron-swarm init --agent <agent-name>
nemo iron-swarm init --agent <workspace>/<agent-name>      # qualified
nemo iron-swarm init --agent <agent-name> -o iron-swarm.yaml

# 2. Run the war-game (preflights first, then runs the iron-swarm.run job)
nemo iron-swarm run --config iron-swarm.yaml

# 3. Inspect the latest run
nemo iron-swarm status
```

The agent must already be deployed and running in NeMo Platform — confirm with
`nemo agents deployments list` before `init`.

## Notes

- Models default to iron-swarm's built-ins and the victim's own LLM resolves through the platform
  Inference Gateway (no raw API keys needed). You can override the models per war-game — three groups:
  **attack** (garak red-team + detector), **analysis** (defenders + the benign validator's synth
  suite-generation and judge), and **agent** (the victim's own LLM). Set them as the manifest's stored
  default or per-run; a custom endpoint's
  key is supplied by name from the Secrets store. Before the sandbox spins up, a chosen model is
  preflighted against its endpoint and the run fails fast (listing the reachable models) on a bad
  name/key/URL.
- The war-game requires a host with Docker + OpenShell; the run job fails preflight with a clear
  message otherwise. Do not report a run successful without verifying its status.
