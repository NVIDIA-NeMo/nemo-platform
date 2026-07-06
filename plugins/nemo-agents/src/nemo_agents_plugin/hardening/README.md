<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Agent Hardening loop (Phase 1, behavioral surface)

Red-teams an agent with garak through the Auditor, produces a reviewable NeMo
Guardrails remediation for the behavioral weaknesses, verifies it, and records
each round to the experiments API. Behavioral surface only; no network arm.

## What each round does

1. **Attack.** `AuditorAttacker` runs a garak scan through `client.auditor.run`
   (live), or replays a saved hitlog for a deterministic run (`auditor_attack.py`,
   `hitlog.py`).
2. **Analyze.** `extract_behavioral_findings` routes hits to behavioral reasons
   (prompt injection, unsafe tool invocation, sensitive disclosure, recon,
   untrusted content) via keyword matching (`attack_analysis.py`).
3. **Remediate.** A suggestor/grader loop generates one block instruction per new
   finding (`defender.py`), and `build_rails_config` aggregates them into a
   managed `self check input` guardrail config (`guardrail_config.py`).
4. **Verify.** The config is applied (created once, then updated in place) and
   each attack and benign request is replayed through the guardrail check
   endpoint (`verify.py`, `_wiring.py`). A blocked attack passes; a blocked
   benign request is an over-block regression.
5. **Record.** Per-round `attack_success_rate` and `benign_pass_rate` land on a
   per-round Experiment in a shared group (`publish.py`).

The loop stops when the post-defense attack-success-rate hits zero or `rounds`
is reached. It never runs against a production agent and never auto-applies the
config; the output is a reviewable managed `GuardrailConfig` plus the recorded
rounds.

## Running it

```
# Deterministic replay (default): replay a saved garak hitlog.
nemo agents harden run --spec '{"probe_spec": "promptinject,dan.DanInTheWild", "judge_model": "<workspace>/<model>", "mode": "replay", "replay_hitlog": "/abs/path.hitlog.jsonl"}'

# Live: garak attacks an agent-under-test served at aut_base_url via the Auditor.
nemo agents harden run --spec '{"probe_spec": "promptinject", "judge_model": "<workspace>/<model>", "mode": "live", "aut_base_url": "http://127.0.0.1:8000/v1"}'
```

`submit` dispatches the same job to the platform; results appear in
`nemo jobs list` and Studio. `judge_model` is the platform model id used for both
the defender's suggestor/grader and the guardrail self-check judge.

## Design note (Phase 1 scope)

The remediation is a managed NeMo Guardrails config using `input`/`output` rails,
not NAT `pre_tool_verifier` middleware (NAT is being retired). Input/output rails
cover prompt injection, indirect injection, and jailbreaks. True pre-tool
tool-call blocking needs the `nemo-guardrails` plugin to dispatch `tool_output`
rails (it currently dispatches only `input`/`output`); that is the fast-follow
that upgrades this loop from input/output rails to tool-call verification.

The Studio "round over round" view is the experiment-group leaderboard table (one
row per round, `Avg attack_success_rate` column), not a line chart; a line chart
would be net-new Studio UI.
