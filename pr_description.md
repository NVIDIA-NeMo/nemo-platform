## Summary

This PR implements the first Platform-managed serving lifecycle for Fabric-backed NeMo Agents as part of AIRCORE-932.

It adds a local FastAPI serving process that creates one Fabric runtime per logical user session and exposes it through the existing agent deployment and gateway flow:

```text
Platform Agent entity
  -> persisted agent.yaml
  -> local Fabric serving process
  -> logical session
  -> translated FabricConfig
  -> FabricRuntime
  -> ordered invoke calls
  -> runtime stop
```

Fabric continues to own harness execution and the runtime `start` / `invoke` / `stop` lifecycle. NeMo Platform owns the multi-user server, logical session identity, runtime registry, request routing, concurrency policy, expiration, and cleanup.

## Changes

- Added an OpenAI-compatible Fabric serving application with:
  - `GET /health`
  - `POST /v1/chat/completions`
  - `DELETE /v1/sessions/{session_id}`
- Added typed request and response models for the chat-completions boundary.
- Added a runtime session registry that maps opaque Platform session IDs to active Fabric runtimes.
- Added a session manager responsible for:
  - Lazy `FabricConfig` translation and runtime startup.
  - Reusing the same runtime for later turns in a logical session.
  - Serializing invocations within one session.
  - Limiting concurrent invocations across independent sessions.
  - Explicit session closure.
  - Idle-session expiration.
  - Draining and stopping all runtimes during server shutdown.
- Added invocation support for an already-active Fabric runtime while retaining the existing one-shot invocation path.
- Added shared local-environment preparation so configured workspaces exist before either one-shot or managed runtime startup.
- Added a shared agent-config format registry/protocol used by agent creation and deployment config resolution.
- Updated the in-memory runner to deploy `nemo-agents-spec-v1` agents by:
  - Persisting a canonical `agent.yaml` under the Platform agent workspace.
  - Running Fabric plan/doctor validation before spawning the server.
  - Starting the Fabric server as a managed local subprocess.
  - Reusing existing port allocation, readiness polling, log handling, process termination, and deployment cleanup behavior.
- Preserved the existing NAT deployment path for `nat-workflow-v1`.
- Added focused tests for format handling, HTTP routing, session lifecycle, concurrency, expiration, runtime cleanup, local deployment, and failure paths.

## Design Choices

### Platform owns sessions; Fabric owns runtimes

A Platform session is a logical conversation rather than an HTTP connection. Platform maintains the `session_id -> FabricRuntime` mapping, while Fabric remains unaware of users, HTTP routing, and other runtimes.

This keeps the integration aligned with Fabric's public lifecycle contract instead of adding lifecycle behavior inside adapters.

### Runtimes are created lazily

Server startup loads and validates the reusable Platform agent definition but does not create a Fabric runtime. A complete `FabricConfig` is translated when the first request opens a logical session, and that config is bound to the resulting runtime.

This avoids allocating harness resources for sessions that never invoke the agent and leaves room for future per-session policy, environment, and profile resolution.

### Session identity uses a response header

The first request may omit `X-Nemo-Session-Id`. Platform generates an opaque session ID and returns it in that response header. Later requests provide the same header to reuse the runtime.

Using a header keeps the request body compatible with the OpenAI chat-completions shape. Supplying an unknown or closed session ID returns `404`; it does not silently create a replacement runtime.

### One runtime processes one turn at a time

Invocations for the same session are serialized with a per-session lock because ordered turns share harness state. Different sessions may run concurrently, subject to a server-wide semaphore. The initial default permits eight concurrent invocations.

### The runtime owns conversation state

Each HTTP request passes the current user message to the existing runtime. Prior turns are not replayed from the HTTP payload because the Fabric runtime and selected harness adapter own the session's conversation state.

### Cleanup is explicit and bounded

Clients can close sessions explicitly. The server also expires idle sessions after 30 minutes, checks every five minutes, and drains all remaining runtimes during shutdown. Runtime registration failures also stop any runtime that was already started.

### Local deployment builds on the existing runner

The first implementation uses the existing in-memory subprocess backend rather than introducing a second process-management system. Fabric and NAT deployments therefore share port allocation, health polling, logs, status transitions, termination, and filesystem cleanup.

Docker/Kubernetes runtime placement and distributed session ownership remain separate follow-up work.

### Agent formats share a small internal protocol

Agent creation and deployment now resolve behavior through config-format handlers. This keeps `nat-workflow-v1` as the default and adds `nemo-agents-spec-v1` without spreading format-specific branches through the API layer.

The registry is intentionally narrow and internal while the RFC 122 entity shapes are still being finalized.

## Error Behavior

- Unknown or closed session: `404`
- Fabric runtime startup failure: `503`
- Fabric invocation failure or failed result: `502`
- Fabric invocation timeout: `504`
- Runtime shutdown failure: `502`

Errors for an existing session preserve the session ID header where appropriate.

## Out of Scope

- Durable session recovery after a Platform/server restart.
- Distributed session registries or routing across replicas.
- Docker/Kubernetes Fabric server deployment and remote runtime placement.
- Authentication and authorization inside the Fabric serving process; those remain Platform gateway concerns.
- Streaming chat completions.
- User-facing cancellation APIs.
- Per-user concurrency quotas or configurable limits through public API fields.
- Final RFC 122 `AgentRun`, input, output, environment, sandbox, and harness entity shapes.

## Validation

Focused branch coverage:

```text
222 passed
```

This includes agent config handling, format dispatch, Fabric translation/validation, one-shot and active-runtime invocation, serving routes, session registry/manager behavior, deployment APIs, controller behavior, and the in-memory runner.

Additional nested NeMo Agents suites:

```text
104 passed
```

Repository Python style and formatting:

```text
All checks passed
2793 files already formatted
```

Manual end-to-end validation:

1. Registered a `nemo-agents-spec-v1` Agent from `agent.yaml`.
2. Deployed it through the Platform API/CLI.
3. Observed `pending -> starting -> running`.
4. Invoked it through the Platform agent gateway.
5. Opened a logical session and received `X-Nemo-Session-Id`.
6. Reused that session for a second turn and confirmed conversation state was preserved.
7. Closed the session and received `204`.
8. Confirmed reuse of the closed session returned `404`.
9. Deleted the deployment and verified its process and prepared base directory were removed.

A broader top-level NeMo Agents unit sweep produced `710 passed` and 16 failures in existing CLI delete/list/optimize tests outside the files changed by this branch.
