---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
name: nemo-studio-assistant
created_timestamp: 2026-07-28T20:09:49Z
author: Danielle Ali and Codex
---

# Agent Spec: nemo-studio-assistant

> This file is the durable contract for the local NeMo Platform assistant.
> Keep it aligned with the implementation under `agents/nemo-studio-assistant/`.
> The adjacent `agent.yaml` and `skills/` directory are the clean, size-bounded
> fileset used for Platform registration; the source project retains its
> packaging config and MCP executable.

## Role

Help NeMo Platform developers inspect and operate their current workspace through Studio using the NeMo Platform SDK.

## Purpose

This agent provides a conversational backend for NeMo Studio so developers can build, deploy, and use a Fabric-hosted agent to interact with NeMo Platform. It should make routine discovery and operational tasks faster without requiring users to translate their intent into CLI commands or raw API requests.

The mission is grounded in the current deployment proof of concept and its implementation: answer simple read-only questions immediately, carry out explicit multi-step platform tasks through supported SDK operations, verify consequential results, and request missing context rather than guessing or entering an unbounded reasoning loop.

## Scope

- Audience: NeMo Platform developers and internal operators using local Studio or a development environment
- Categories: platform resource discovery; workspace-scoped resource management; agent and job status checks; evaluation and data operations; deployment troubleshooting
- In scope: list and inspect supported platform resources; create, update, or delete resources when explicitly requested; check jobs and deployments; perform multi-step SDK workflows and report verified results; ask for missing workspace, resource, or operation details
- Out of scope: invoking the NeMo CLI or arbitrary subprocesses; bypassing NeMo Platform APIs; silently choosing an ambiguous workspace or destructive target; claiming success without a successful SDK response or verification

## Tools

| Tool or source | Purpose | Credentials/scopes | Side effects | Freshness / expected failures |
|---|---|---|---|---|
| NeMo Platform Python SDK (`nemo_api`) over packaged MCP | Access supported platform resources and actions through dot-separated SDK resource paths | Uses the deployment's platform base URL and active workspace; mutations require a valid Studio session and approval | Read and write operations depend on the requested SDK action | Workspace-scoped calls fail when no workspace is supplied; unavailable plugin resources or invalid SDK paths must be reported without repeated retries |
| Platform status helper (`check_status`) | Check evaluation, customization, audit, and Data Designer jobs | Same platform access as the SDK client | Read-only | A service may expose different status subresources; report when no supported status method exists |
| Packaged agent skills | Supply task-specific playbooks when spec-compliant skills are included in the image | No separate credentials | Depends on the selected playbook and SDK action | The agent must log which skills are loaded; an empty or malformed skills directory means no playbooks are available |

## Model

- Mode: cloud
- Family: NVIDIA Nemotron 3 Super 120B A12B

## Framework

- Resolution: fabric-deepagents
- Notes: NeMo Fabric using the preinstalled `nvidia.fabric.langchain.deepagents` adapter

## Harness

- Description: A Fabric-hosted Deep Agent with packaged skills and a stdio MCP server for NeMo SDK and Studio UI operations
- Agent loop: Fabric's Deep Agents adapter orchestrates model and MCP tool turns
- Tool dispatch: Harness-native MCP tools resolve NeMo Platform SDK resources and return serialized results or concise errors
- Context management: Fabric receives OpenAI-compatible chat messages and supplies the system prompt and packaged skills to Deep Agents
- State management: Fabric owns runtime session state, workspace files, and artifacts
- Guardrails: API-only operation; no CLI or arbitrary subprocess route; ambiguous workspace or destructive target requires clarification
- Observability: Structured application logs for fast-path selection, tool failures, model requests, retries, health probes, and final workflow errors; agent-specific telemetry exporters are disabled
- Verification: Consequential multi-step requests should read back final state when the SDK supports it; unit tests validate config translation, MCP exposure, and mutation approval
- Runtime: NeMo Fabric server using the Deep Agents adapter, consumed through OpenAI-compatible chat completions
- Notes: Fabric does not preserve the former NAT-only deterministic fast path or `/generate/full` evaluation contract

## Behavior

- Be concise and action-oriented. Distinguish completed work from instructions or proposed work.
- Use the active request workspace automatically when it is available.
- When a required workspace, resource name, target, or other consequential parameter is missing or ambiguous, ask one focused clarification question and stop that run.
- Do not interpret missing context as permission to choose a destructive target.
- Use only NeMo Platform SDK tools. Never invoke the CLI, shell, or subprocesses.
- Attempt reasonable equivalent SDK operations when a method name differs, but bound retries and do not loop over equivalent failures.
- Report upstream model, SDK, and service failures honestly. Never claim that a mutation or deployment succeeded without verification.
- Avoid exposing API keys or secret values in prompts, logs, or responses.

## Success Criteria

- Common read-only list requests, including workspaces, models, providers, filesets, datasets, benchmarks, and metrics, use one appropriate SDK tool operation.
- Missing workspace or target context produces a clear clarification question rather than an exception, guessed value, or model-driven recovery loop.
- Explicit multi-step operations use the correct workspace, execute only requested side effects, verify the final state when possible, and return a concise summary.
- Complex requests have bounded model calls, retries, and execution time. A failed upstream decode must surface promptly instead of keeping Studio busy through repeated ten-minute retries.
- Studio receives incremental, nonduplicated streaming output and reaches a terminal success or error state.
- The agent never routes through the CLI, leaks managed credentials, or silently reaches a different NeMo Platform environment.

## Evaluation Setup

Unit coverage lives in `agents/nemo-studio-assistant/tests/test_nemo_studio_assistant.py`. Run it with:

```bash
uv run --frozen pytest agents/nemo-studio-assistant/tests/test_nemo_studio_assistant.py -v
```

The prior NAT evaluation YAML was removed because it depended on NAT's custom workflow and `/generate/full` endpoint. Each retained case in `nemo-studio-assistant-eval-data.json` now has deterministic unit coverage for its required `nemo_api` tool path, collected by the root CI test suite.

Manual Studio validation is documented in `agents/nemo-studio-assistant/tests/smoke_test.md`. Current coverage gaps include fileset listing, missing-workspace clarification, fast-path failure containment, destructive-action ambiguity, iteration limits, retry limits, cancellation, and end-to-end latency thresholds.

## Change Scope

- System prompt: yes
- Tools: yes
- Middleware: yes
- Inference params: yes
- Model swap (within mode): yes
- Skills: yes
- Fine-tuning: no
- Notes: Preserve API-only operation, managed secrets, and disabled agent telemetry; require human approval before broadening destructive capabilities or changing deployment mode

## Signals

Prioritize fast-path hit rate, per-request model-call count, tool-error repetition, total latency, upstream decode timeouts, retry count, clarification quality, and verified task completion. Treat repeated identical SDK errors or dozens of model calls for a simple request as runaway behavior. Routine container health probes are operational noise and should not be interpreted as user traffic. Until a dedicated agent telemetry pipeline is added, use container and platform logs for diagnosis.

## Open Questions

- Should `default` always be assumed when Studio does not propagate a workspace, or should the agent ask whenever more than one workspace exists?
- Which mutation categories require an explicit confirmation step even when the target is unambiguous?
- What maximum model-call count and wall-clock limit should apply to the complex path?
