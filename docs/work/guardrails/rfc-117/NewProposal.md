# RFC: Guardrails Standalone Deployment and Decoupling

**Related**: RFC-117

---

## TL;DR

Cohesity is blocked from upgrading because Guardrails is coupled to the NMP platform (Postgres, IGW, Auth). We also have two inference paths — the service's `/chat/completions` endpoint and the IGW plugin — that are already diverging and will get worse if left alone.

The fix addresses both at once: build a `ChecksService` in-process interface that owns the full inference core (config loading, `LLMRails` lifecycle, caching), using the plugin's superior caching logic as the reference. Both the plugin and the HTTP endpoint become thin adapters over it — one code path. Wire it with a `ConfigStore` protocol (`FilesystemConfigStore` for standalone, `EntityStoreConfigStore` for NMP) and a `ModelResolver` protocol (`DirectUrlModelResolver` for standalone, `NmpIgwModelResolver` for NMP), selected at startup via `GUARDRAILS_STANDALONE=true`.

For Cohesity: add a `/v2/chat/completions` standalone endpoint (no workspace in the path), add K8s health probes. Their upgrade requires updating the endpoint URL and adding `base_url` to their model config YAMLs — ConfigMap structure and NIM router config are unchanged.

Long-term: the decoupling work makes Guardrails pip-installable standalone, consistent with NMP's plugin-based architecture direction, and sets up the Phase 3 gRPC Checks API and schema redesign described in RFC-117.

---

## Background

### NeMo Platform Architecture

NMP has recently shifted from a monolithic platform to a plugin and service-based system. Services are individually installable and run via `nemo services run`. The platform provides shared infrastructure: Entity Store (Postgres-backed generic entity management), the Inference Gateway (IGW), Secrets, Files, and Auth. Services declare dependencies on these and the framework enforces them at startup.

### Guardrails Today

Guardrails consists of two components:

**The Guardrails service** (`services/guardrails/`) — a FastAPI application that:

- Manages `GuardrailConfig` entities (CRUD) via the Entity Store
- Exposes `POST /v2/workspaces/{workspace}/chat/completions` for inference with rails applied
- Loads configs from Postgres at runtime via `EntityClient`
- Resolves model references to IGW routes via `model_routing.py`
- Declares hard platform dependencies on: `entities`, `auth`, `secrets`, `files`, `models`

**The Guardrails plugin** (`plugins/nemo-guardrails/`) — IGW middleware that:

- Intercepts requests passing through IGW virtual models as middleware hooks (`process_request` / `process_response`)
- Also reads `GuardrailConfig` from the Entity Store
- Has a significantly more sophisticated caching layer than the service: a 3-stage pipeline with content-hash-keyed pooled `LLMRails` instances (`LLMRailsCache` + `StabilizedRailsConfigCache`)

In the recommended NMP usage pattern today, customers configure a virtual model with the Guardrails plugin attached. The service's `/chat/completions` endpoint predates the plugin and is no longer the primary supported inference path. These two components have diverged — the plugin's caching layer is substantially more sophisticated — and further investment risks deepening that gap. Unifying them under a shared inference core is a central goal of this proposal.

### Cohesity

Cohesity is an enterprise customer running NMP 25.12. They use Guardrails exclusively — no IGW, no Entity Store, no Postgres. Their deployment:

- A standalone Guardrails container
- `GuardrailConfig` YAML files mounted via a Kubernetes ConfigMap
- Inference to their own NIM router (not NVIDIA's IGW)
- Calling `POST /v1/chat/completions` directly

They want to upgrade to receive security patches and bug fixes, but are blocked because Guardrails is no longer independently deployable.

### Two Distinct Problems

This RFC addresses two related but distinct problems:

**Problem 1 — Unblocking Cohesity without fundamental rearchitecture**: Cohesity cannot upgrade because Guardrails is no longer independently deployable. The solution must not require them to fundamentally change their deployment model — same endpoint, same ConfigMap approach, no new platform dependencies. On our side, this is achieved by properly decoupling Guardrails from NMP through the ChecksService work, not by building a temporary shim. Cohesity's upgrade path falls out naturally from doing the architecture right.

**Problem 2 — Guardrails as a standalone product**: Beyond Cohesity, customers want to integrate Guardrails into their own inference stacks without adopting NMP. This requires a stable, gateway-agnostic API contract that integrates with Envoy ext_proc, LiteLLM, and other gateways. This is the long-term vision described in RFC-117.

These are addressed in sequence. Problem 1 is solved by the ChecksService decoupling and standalone deployment requirements in this document. Problem 2 is addressed by Phase 3 (gRPC Checks API and schema redesign). The design here is explicitly shaped so that Phase 3 can follow without redesign.

---

## Design Principle: One Artifact, One-Way Dependency

This is the governing constraint for all implementation decisions in this proposal. It has two concrete implications:

**Same artifact.** There is one Guardrails package and one image. Standalone and NMP customers use identical software. Wiring is injected via configuration (`GUARDRAILS_STANDALONE`, `CONFIG_STORE_PATH`, `NIM_ENDPOINT_URL`, etc.), not baked into separate builds or images. This aligns with NMP's direction of distributing services as Python packages — the package is the artifact; the image is just a Python base plus `pip install`.

**No platform service calls in standalone mode.** The one-way dependency is enforced at the instantiation level, not the import level. `nmp.common` is a Python library — importing it doesn't require platform services to be running, and it is present in the image in both modes. The constraint is that `ChecksService` core never calls platform service APIs directly. Only the NMP-specific protocol implementations — `EntityStoreConfigStore` and `NmpIgwModelResolver` — call `EntityClient` or IGW routing APIs, and those are never instantiated when `GUARDRAILS_STANDALONE=true`. The standalone test is: start the container with `GUARDRAILS_STANDALONE=true` and no platform services running — the service must come up and serve requests successfully.

---

## Problem Breakdown

### P1 — No standalone deployment story

The service cannot start without the platform's Entity Store, Auth, and Models services. There is no Dockerfile or Helm chart for deploying Guardrails independently.

### P2 — Config loading requires Postgres

`GuardrailConfig` entities are stored in and fetched from Postgres at runtime. There is no supported path for loading configs from a filesystem or ConfigMap without a database. The existing `populate_config_store()` utility reads from disk at startup but writes to Postgres — the database dependency is not removed.

### P3 — Model routing is hardwired to IGW

`model_routing.py` resolves model references to IGW routes via `sdk.models.get_openai_route_base_url()`. Customers with their own NIM router have no first-class way to configure a direct model URL. (A literal `base_url` in the model's `parameters` block technically bypasses IGW resolution today, but this is undocumented and untested.)

### P4 — Two diverging inference paths

The service's `/chat/completions` endpoint and the plugin both implement the same core operation: load a config, build/retrieve an `LLMRails` instance, execute rails, return a response. They have separate caching layers — the plugin's is substantially better. If we extend the service endpoint to work standalone, these two paths will diverge further with each future feature investment.

---

## Non-Goals

The following are explicitly out of scope for this proposal:

- **Config hot-reload**: configs load at startup; updating a ConfigMap requires a pod restart.
- **Auth in standalone mode**: access control in standalone deployments is the operator's responsibility at the network layer (ingress rules, mTLS). The service has no built-in auth when `GUARDRAILS_STANDALONE=true`.
- **Per-request credential forwarding to guard models**: `X-Model-Authorization` passthrough is not extended to guard model endpoints (content safety, jailbreak detector, etc.). Deferred to the `SecretResolver` work in Phase 3.
- **gRPC Checks API and streaming support**: the bidirectional `CheckStream` RPC and the full gRPC service boundary are Phase 3 scope.
- **Schema redesign**: replacing the `nemoguardrails.RailsConfig` YAML mirror (`_private.py`) with a platform-owned schema is Phase 3 scope. This proposal must not break configs written to the current schema.
- **Additional ConfigStore backends**: S3, external databases, and other storage backends are Phase 3 scope. The only new backend introduced here is `FilesystemConfigStore`.
- **Published container images**: NVIDIA will not publish a standalone Guardrails image to nvcr.io or GHCR. Users build and push to their own registries from the reference Dockerfile.

---

## Proposed Approach

### Do we need an interim shim?

To make this choice legible, it helps to be explicit about the current state. Guardrails has two inference paths today:

- **The service endpoint** (`POST /v2/workspaces/{workspace}/chat/completions` in `services/guardrails/`) — the legacy path. Loads configs from Entity Store (Postgres) and resolves models via IGW. Has its own config registry and caching layer, both tightly coupled to platform services.
- **The IGW plugin** (`plugins/nemo-guardrails/`) — the current primary path. Intercepts requests passing through IGW virtual models. Also loads from Entity Store, but has a substantially more sophisticated caching layer (`LLMRailsCache`, `StabilizedRailsConfigCache`).

Neither path works standalone today. Cohesity's 25.12 deployment used a `/v1/chat/completions` endpoint that no longer exists in the codebase.

The choice is whether to patch the service endpoint as an interim step, or unify both paths properly before shipping standalone support:

**Option A — Patch the service endpoint**: Add filesystem config loading, direct model URL support, and a `/v2/chat/completions` standalone endpoint to the existing service endpoint. The plugin is left untouched. Faster to ship, but the two inference paths continue to diverge and the patched code is throwaway — it gets replaced when the ChecksService work happens anyway.

**Option B — Unify first via ChecksService**: Extract the shared inference core into a `ChecksService` in-process interface. Both the service endpoint and the plugin become thin adapters over it. Standalone deployment falls out naturally by wiring `FilesystemConfigStore` and `DirectUrlModelResolver` at startup. No throwaway code; both paths are unified; Cohesity gets the plugin's superior caching from day one.

**Recommendation: skip the shim.** Option A makes sense only if Cohesity has a hard deadline that cannot wait for the ChecksService work. The cost is real: the shim is throwaway, the path divergence deepens in the interim, and the ChecksService work happens regardless. If Cohesity's timeline is the deciding factor, the shim approach is documented in the appendix.

The remainder of this section describes Option B in full.

---

### Option B — Implementation

This is the core change. It unifies the two inference paths, addresses all four problems, and is the foundation for Phase 3.

#### What is the ChecksService?

A Python class (not a network service — that is Phase 3 scope) that owns:

- **Config resolution**: load and cache `RailsConfig` objects from the injected `ConfigStore`
- **LLMRails lifecycle**: build, cache, and pool `LLMRails` instances — using the plugin's `LLMRailsCache` as the reference implementation
- **Request execution**: run input rails, optionally run inference, run output rails, return a structured result

It accepts injected dependencies at construction time:

- `ConfigStore` — where configs come from
- `ModelResolver` — how model references are resolved

Both the plugin and the service HTTP endpoint become thin adapters over this interface. The plugin's `LLMRailsCache`, `StabilizedRailsConfigCache`, and `rails.py` move into `ChecksService`. The service's `CompletionRequestHandler`, `RailsRegistry`, and `ConfigRegistry` are replaced.

#### `ChecksService.check()` interface

`ChecksService` exposes a single `check()` method. Whether it runs input rails or output rails is determined by the presence of an optional `response` field on `CheckInput` — no response means input check, response present means output check. This mirrors the plugin's `process_request` / `process_response` split without requiring two separate methods.

```python
@dataclass
class CheckInput:
    request: ChatCompletionRequest   # the incoming messages and model context
    config: ConfigRef                # which GuardrailConfig to apply; in standalone mode, identified by name only
    response: ChatCompletionResponse | None  # absent → input check; present → output check
    context: RequestContext          # credentials and headers to forward to guard models

@dataclass
class CheckOutput:
    # oneof: either the check passed (with optional modifications) or it was blocked
    status: Literal["allow", "block"]
    messages: list[Message]          # modified messages if status=allow
    triggered_rails: list[str]       # which rails fired
    refusal: str | None              # populated if status=block
```

**Responsibilities of `check()`**:
1. Resolve `config` to a `RailsConfig` via the `ConfigStore`
2. Obtain a `Guardrails` instance for the resolved config (built on demand, cached by config content hash)
3. Use the `ModelResolver` to inject concrete guard model endpoints into the config
4. Run input or output rails via the `Guardrails` facade, which dispatches internally to `IORails` (optimized fast path for productized rails: content safety, topic safety, jailbreak detection) or `LLMRails` (for Colang-based custom flows) — the caller does not choose
5. Return `CheckOutput` indicating pass, modification, or block

**`ChecksService` does not call the main model.** The orchestration of a full chat request lives in the caller:

```
# Chat completions endpoint
input_result  = await checks_service.check(CheckInput(request, config, response=None))
if input_result.status == "block": return blocked_response
model_response = await call_nim(request)
output_result = await checks_service.check(CheckInput(request, config, response=model_response))
if output_result.status == "block": return blocked_response
return model_response

# Plugin
process_request()  → checks_service.check(CheckInput(request, config, response=None))
process_response() → checks_service.check(CheckInput(request, config, response=igw_response))
```

**Phase 3 constraint**: all types in `CheckInput` and `CheckOutput` must be plain data — no FastAPI `Request` objects or raw HTTP constructs — so the interface can be promoted to a gRPC service boundary in Phase 3 without redesign. The field shapes above are intentionally close to what would become proto message definitions.

#### Why the plugin's caching logic is the reference

The plugin's `LLMRailsCache` is substantially better than the service's `RailsRegistry`:

- Content-hash-keyed pooling: multiple `LLMRails` instances per config for safe concurrency
- 3-stage pipeline: discriminated source → stabilization → pool
- Proper instance lifecycle: lease, clear shared state, return
- `StabilizedRailsConfigCache` memoizes by `(workspace, name, updated_at)` for coherent cache invalidation on config update

The service's `RailsRegistry` is simpler and has known concurrency limitations. When extracting `ChecksService`, the plugin's caching logic becomes canonical.

#### `ConfigStore` protocol

```python
class ConfigStore(Protocol):
    def get(self, workspace: str, name: str) -> RailsConfig | None: ...
    def list(self, workspace: str) -> list[RailsConfig]: ...
```

**Implementations:**

- `FilesystemConfigStore` — at startup, scans `CONFIG_STORE_PATH` for flat `.yaml` / `.yml` files and loads each by filename (without extension) as the config name. There is no workspace directory structure — workspace is not a concept in standalone mode, and `FilesystemConfigStore` ignores the workspace parameter in `get()` and `list()`. Configs are loaded into memory at startup; no runtime database access. Config changes require a pod restart — consistent with the ConfigMap model Cohesity already uses.
- `EntityStoreConfigStore` — wraps current `EntityClient` behavior; preserves all existing NMP functionality
- `InMemoryConfigStore` — for tests

**Schema compatibility**: the underlying `nemoguardrails.RailsConfig` schema has changed since 25.12 but is backwards compatible. Cohesity's existing ConfigMap YAML files load without modification. The Phase 3 schema redesign (which replaces the `nemoguardrails` mirror entirely) is a separate concern and must not break files written to the current schema.

#### `ModelResolver` protocol

```python
class ModelResolver(Protocol):
    def resolve(self, model_ref: str, workspace: str) -> str: ...  # returns base_url
```

**Implementations:**

- `DirectUrlModelResolver` — reads `base_url` directly from the config YAML; falls back to `NIM_ENDPOINT_URL`. Also injects `NIM_API_KEY` from the environment as the `Authorization` header on guard model calls (see credential flow below). If `NIM_API_KEY` is unset, no auth header is added — works for NIMs behind network-level auth, which covers Cohesity's current setup.
- `NmpIgwModelResolver` — current `model_routing.py` behavior; calls `sdk.models.get_openai_route_base_url()`. Auth to guard models is handled by IGW, not by this resolver.

**Guard model credential flow (standalone)**: API keys for guard model NIM endpoints must not be embedded in the `GuardrailConfig` YAML — configs appear in ConfigMaps, API responses, and potentially version control. Instead, credentials are supplied via environment variables backed by Kubernetes Secrets in production. `DirectUrlModelResolver` reads `NIM_API_KEY` at call time and injects it as the bearer token. In Phase 3, a `SecretResolver` protocol replaces this env-var convention and can back to Vault, the K8s Secrets API, or other credential stores.

#### Impact on the plugin

The plugin's `middleware.py` is simplified to:

1. On startup: construct `ChecksService(config_store=EntityStoreConfigStore(...), model_resolver=NmpIgwModelResolver(...))`
2. On request: call `checks_service.check(input, config_ids, ...)`

The plugin's own `LLMRailsCache`, `StabilizedRailsConfigCache`, and `rails.py` are removed — they live in `ChecksService`. The plugin becomes ~200 lines of translation code between IGW middleware hooks and `ChecksService`.

**Extraction risk**: the plugin is production code on the NMP inference path today. Moving its caching and rail execution logic into `ChecksService` risks behavioral regression in that path, which is higher-stakes than anything on the standalone side. Two constraints follow from this:

- **Atomic change**: the `ChecksService` extraction and the plugin's refactor to a thin adapter must ship as a single change, not sequential PRs. A window where the plugin is partially migrated is a fragile intermediate state on a production path.
- **Plugin integration tests are the acceptance criteria for Phase 2**: if the plugin's existing integration tests pass after extraction, the core inference logic in `ChecksService` is correct. These tests should be treated as the primary validation bar, not a post-hoc check.

#### Impact on the service

The service's `CompletionRequestHandler`, `RailsRegistry`, and `ConfigRegistry` are replaced by:

1. On startup: construct `ChecksService` with the appropriate backends based on configuration
2. On request: call `checks_service.check(input, ...)`
3. All three HTTP callers — `/v2/chat/completions` (standalone), `/v2/workspaces/{workspace}/chat/completions`, and `/v2/checks` — become thin adapters over the same `ChecksService` instance

#### Selecting backends at startup

`GUARDRAILS_STANDALONE` selects implementations at service startup:


| `GUARDRAILS_STANDALONE` | `ConfigStore`            | `ModelResolver`          |
| ----------------------- | ------------------------ | ------------------------ |
| `false` (default)       | `EntityStoreConfigStore` | `NmpIgwModelResolver`    |
| `true`                  | `FilesystemConfigStore`  | `DirectUrlModelResolver` |


The service code itself has no `if standalone` branches — wiring is injected at construction time.

#### Standalone decoupling: three distinct concerns

Inspecting the current import structure surfaces three concerns that need to be handled independently. All platform interactions go through `nmp.common` — there are no direct imports from other service packages — but the concerns are not all solved the same way.

**1. Inference path — handled by the protocol layer**

`model_routing.py`, `config_store.py`, and `registry.py` all import `EntityClient` and `get_platform_sdk` from `nmp.common` at the module level. These imports succeed unconditionally since `nmp.common` is present in the image. The actual *calls* to platform services — `EntityClient.get()`, `sdk.models.get_openai_route_base_url()` — are what must not execute in standalone mode. The `ConfigStore` and `ModelResolver` protocols isolate these calls inside `EntityStoreConfigStore` and `NmpIgwModelResolver`, which are only instantiated in NMP mode. `ChecksService` itself makes no platform API calls.

**2. Service startup framework — conditional dependency list**

`service.py` extends `nmp.common.service.Service`, which enforces platform dependency declarations (`["entities", "auth", "secrets", "files", "models"]`) and waits for them to be ready at startup. In standalone mode, none of those services exist and the startup loop will hang.

`Service.__init__` already accepts a `dependencies` override; when `dependencies=[]` is passed, the wait loop is skipped entirely. No new entry point or parallel infrastructure is needed — we reuse the existing `Service` framework for app creation, router mounting, `on_startup()`, OpenAPI spec, and health routes unchanged.

The change is a one-liner in `GuardrailsService.__init__`:

```python
def __init__(self) -> None:
    standalone = os.getenv("GUARDRAILS_STANDALONE", "").lower() in ("1", "true")
    super().__init__(
        name="guardrails",
        module_name="nmp.guardrails",
        dependencies=[] if standalone else None,  # None → use class-level declaration
    )
    apply_langchain_patch()
```

**3. Config CRUD endpoints — not registered in standalone mode**

`api/v2/configs/endpoints.py` imports `EntityClient` and `get_entity_client` from `nmp.common.service.dependencies` and uses them directly in the config CRUD handlers. These endpoints don't make sense in standalone mode — config management is done by editing YAML files in the ConfigMap, not via API. Write endpoints (`POST/PATCH/DELETE`) are not registered when `GUARDRAILS_STANDALONE=true`. Read endpoints (`GET`) can optionally be registered against `FilesystemConfigStore` for observability.

**4. Inference endpoint — `/v2/chat/completions` registered in standalone mode only**

The workspace-free `/v2/chat/completions` endpoint is registered only when `GUARDRAILS_STANDALONE=true`. Config lookup is by name only — `FilesystemConfigStore` ignores the workspace parameter entirely. The workspace-scoped `/v2/workspaces/{workspace}/chat/completions` endpoint is not registered in standalone mode; workspace is an NMP concept with no meaning in a single-tenant deployment.

---

### Phase 3 — Protocol Layer and Schema Redesign

Detailed in the existing RFC-117 documents (`docs/work/guardrails/rfc-117/`). Summarized here for completeness.

**Extended protocol layer**: Formalize additional protocols beyond `ConfigStore` and `ModelResolver` — `PrincipalProvider` (identity extraction), `AuthorizationPolicy` (access control), `SecretResolver` (credential resolution). Add implementations for S3, Postgres, OIDC, Vault, etc. to broaden standalone deployment options.

**gRPC + Connect Checks API**: Promote `ChecksService` from an in-process Python interface to a network-exposed gRPC service. Enables Guardrails as a separately-deployed pod, integration with Envoy ext_proc, LiteLLM, and other gateways. The Phase 2 in-process interface becomes the gRPC service implementation — callers swap to a generated stub; `ChecksService` code itself does not change.

**Schema redesign**: Replace the ~1700-line upstream `nemoguardrails.RailsConfig` mirror (`_private.py`) with a ~300-400 line platform-owned schema and a `compile_to_llmrails_config()` compiler. Eliminates recurring upstream-mirror upgrade debt; reduces public API surface from ~50 classes to ~25.

Phase 3 is not required to unblock Cohesity or eliminate the inference path divergence.

---

## Deployment Story

This section defines Guardrails' requirements on the platform deployment infrastructure. The platform team owns Dockerfiles, Helm charts, observability wiring (OTEL, tracing), and release pipelines. What follows expresses what Guardrails needs from that infrastructure — what a standalone deployment must support, not how to build it.

> **Platform team dependency**: Extending the deployment solution to support standalone Guardrails is a non-trivial ask with real platform team scope. The requirements below are inputs to that work, not a complete implementation spec.

### Artifact Distribution

**Primary requirement**: the NMP deployment infrastructure must support a Guardrails-only deployment mode — bringing up the Guardrails service without any other NMP services (Inference Gateway, Entity Store, Auth) or Postgres. Customers like Cohesity use the same deployment tooling as a full NMP installation, configured to deploy only Guardrails.

For this to work, Guardrails must be independently installable as a Python package — the ChecksService decoupling work (described below) ensures the package can be installed without pulling in the full NMP platform dependency tree. This is a prerequisite that must land before a standalone deployment is viable.

NVIDIA does not publish a standalone Guardrails container image. Consistent with NMP's distribution model, customers build from the reference Dockerfile and push to their own registries.

### Kubernetes Deployment Topology

```
┌─────────────────────────────────────────────────────┐
│  Kubernetes namespace                               │
│                                                     │
│  ConfigMap: guardrail-configs                       │
│   └── content-safety.yaml                          │
│   └── self-check.yaml                              │
│                                                     │
│  Deployment: guardrails                             │
│   └── container: guardrails                        │
│       env: GUARDRAILS_STANDALONE=true              │
│       env: CONFIG_STORE_PATH=/configs              │
│       env: NVIDIA_API_KEY=<from Secret>            │
│       volumeMount: /configs ← guardrail-configs    │
│                                                     │
│  Service: guardrails (ClusterIP or LoadBalancer)    │
│   └── port 8080 → container port 8080              │
└─────────────────────────────────────────────────────┘
         │
         ▼
  Customer's NIM router (external)
```

No Postgres, Entity Store, Auth service, or IGW is required. The only external dependency is the NIM endpoint(s) referenced in the config YAMLs.

### Config YAML Format

Each file in the ConfigMap follows the existing `RailsConfig` YAML schema. The key standalone-specific field is `parameters.base_url` on each model, pointing directly at the NIM endpoint.

```yaml
# content-safety.yaml
models:
  - type: main
    engine: nim
    model: meta/llama-3.1-8b-instruct
    parameters:
      base_url: https://nim-router.internal/v1
  - type: content_safety
    engine: nim
    model: nvidia/nemo-guard-content-safety
    parameters:
      base_url: https://nim-router.internal/v1

rails:
  input:
    flows:
      - check input content safety
  output:
    flows:
      - check output content safety
```

Config files are flat `.yaml` files at the root of `CONFIG_STORE_PATH`, named by config name (e.g. `content-safety.yaml`). There is no workspace directory structure — workspace is not a concept in standalone mode.

### NIM Credential Flow

**Client → Guardrails**: No service-level auth in standalone mode. The operator is responsible for access control at the network layer (ingress rules, mTLS, etc.).

**Guardrails → NIM**: When nemoguardrails executes a config, it makes multiple LLM calls — the main model and any guardrail-specific models (content safety classifier, jailbreak detector, etc.). Each is a separate `langchain-nvidia-ai-endpoints` LLM client. Today, `X-Model-Authorization` only flows to the main model; guard model credentials are not handled by the same mechanism.

In standalone mode, credentials are supplied via environment variables backed by Kubernetes Secrets — raw API keys must not be embedded in `GuardrailConfig` YAML files, which appear in ConfigMaps, API responses, and potentially version control.

`DirectUrlModelResolver` reads `NIM_API_KEY` from the environment and injects it as the `Authorization` bearer token on all guard model calls. If unset, no auth header is added — sufficient for NIMs behind network-level auth (Cohesity's current setup). The long-term solution — a `SecretResolver` protocol that can back to Vault, the K8s Secrets API, or other credential stores — is a Phase 3 item.

### Health Probes

The platform runner currently provides `/health/live` and `/health/ready` (`nmp_platform_runner/health.py`). These are absent from the Guardrails service itself and need to be added for standalone K8s deployments:

- `GET /health/live` — returns `200 OK` unconditionally
- `GET /health/ready` — returns `200 OK` when configs are loaded; `503` during startup

The Helm chart configures both with appropriate `initialDelaySeconds` to account for `LLMRails` warm-up time.

### Config Updates and Scaling

**Config updates**: Configs load into memory at startup. Updating the ConfigMap requires a rolling pod restart (`kubectl rollout restart deployment/guardrails`). Hot-reload is explicitly out of scope for this phase.

**Horizontal scaling**: Fully supported. Replicas each load configs independently from the same immutable ConfigMap. No shared mutable state between replicas.

### Deployment Configuration Requirements

The Helm chart must expose configuration for the following parameters. Exact chart value names are owned by the platform team; this table specifies what must be configurable and why.

| Parameter               | Required | Description                                                                      |
| ----------------------- | -------- | -------------------------------------------------------------------------------- |
| Container image         | Yes      | User-supplied registry path and tag; no image is published by NVIDIA             |
| `GUARDRAILS_STANDALONE` | Yes      | Must be settable to `true` to enable standalone mode at startup                  |
| `CONFIG_STORE_PATH`     | Yes      | Path inside the container where the config ConfigMap is mounted (default `/configs`) |
| `NIM_ENDPOINT_URL`      | No       | Global NIM endpoint fallback used when `base_url` is absent from a config YAML   |
| ConfigMap mount         | Yes      | A named ConfigMap must be mountable at `CONFIG_STORE_PATH`                       |
| NIM credentials         | No       | `NVIDIA_API_KEY` must be injectable from a Kubernetes Secret                     |
| Replica count           | No       | Must support >1; no shared mutable state between replicas                        |
| CPU/memory limits       | No       | Standard resource requests and limits                                             |
| Readiness probe delay   | Yes      | Must allow sufficient time (≥30s) for config loading and LLMRails warm-up        |


---

## Cohesity Upgrade Guide

The goal is a near-drop-in upgrade: same ConfigMap approach, minimal YAML changes, one URL update.

### What changes


|                 | 25.12                       | New standalone                                   |
| --------------- | --------------------------- | ------------------------------------------------ |
| Container image | 25.12 Guardrails image      | New image (built from reference Dockerfile)      |
| Endpoint        | `POST /v1/chat/completions` | `POST /v2/chat/completions`                      |
| Config loading  | Filesystem via volume mount | Same                                             |
| Config format   | `RailsConfig` YAML          | Same schema; `base_url` must be explicit         |
| Database        | None                        | None                                             |
| Auth            | None                        | None                                             |


### Step 1 — Update config YAMLs

Add `parameters.base_url` to each model entry, pointing at Cohesity's NIM router. Alternatively, set `NIM_ENDPOINT_URL` as a global env var and omit `base_url` from the YAML.

```yaml
# Before
models:
  - type: main
    engine: nim
    model: meta/llama-3.1-8b-instruct

# After
models:
  - type: main
    engine: nim
    model: meta/llama-3.1-8b-instruct
    parameters:
      base_url: https://cohesity-nim-router.internal/v1
```

Config files sit at the root of the ConfigMap — no subdirectory needed:

```
config-store/
  content-safety.yaml
  self-check.yaml
```

### Step 2 — Build and push the image

Using the reference Dockerfile, build a container image and push it to Cohesity's internal registry.

```bash
docker build -t <cohesity-registry>/guardrails:<version> .
docker push <cohesity-registry>/guardrails:<version>
```

### Step 3 — Deploy via Helm

Deploy using the platform's Helm chart, configured with the following:

- **Standalone mode enabled** — sets `GUARDRAILS_STANDALONE=true`
- **Image** — the registry path and tag from Step 2
- **Config source** — mount the `guardrail-configs` ConfigMap at `CONFIG_STORE_PATH`
- **NIM credentials** (if NIM auth is required) — inject `NVIDIA_API_KEY` from a Kubernetes Secret

### Step 4 — Verify

```bash
curl -X POST http://guardrails/v2/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta/llama-3.1-8b-instruct",
    "messages": [{"role": "user", "content": "Hello"}],
    "guardrails": {"config_id": "content-safety"}
  }'
```

### What does not change

- Request and response format (only the URL changes)
- ConfigMap structure (beyond adding `base_url`)
- Any Kubernetes resources other than the Guardrails deployment
- NIM router configuration

---

## Open Questions

1. **Cohesity timeline**: If they have a fixed near-term deadline, Option A may be necessary. Otherwise Option B is the right call. Confirm before committing to an implementation path.
2. **Cohesity NIM auth**: Does their NIM router require credentials? If not, the credential flow section is moot for the initial cut. If yes, confirm whether a single `NVIDIA_API_KEY` covers all model endpoints.
3. **Per-request credential rotation for guard models**: `X-Model-Authorization` passthrough is not extended to guard models in this proposal. If customers require this, it should be scoped separately — likely as part of the `SecretResolver` work in Phase 3.
4. **Default config seeding in standalone mode**: The service seeds three default configs into Entity Store at startup. In standalone mode, these should be bundled as YAML defaults that `FilesystemConfigStore` falls back to when the user's ConfigMap doesn't override them. Exact behavior TBD.
5. **Helm chart publishing**: Maintain in this repo (`deploy/helm/guardrails/`) or publish to a separate chart repo? Keeping it here is simpler for now.

---

## References

- RFC-117 documents (long-term vision): `docs/work/guardrails/rfc-117/` (files prefixed `117_`)
- Guardrails service: `services/guardrails/`
- Guardrails plugin: `plugins/nemo-guardrails/`
- Config store utility: `services/guardrails/src/nmp/guardrails/app/utils/config_store.py`
- Model routing: `services/guardrails/src/nmp/guardrails/app/utils/model_routing.py`
- Plugin caching: `plugins/nemo-guardrails/src/nemo_guardrails_plugin/llmrails_cache.py`

---

## Appendix: Phase 1 — Standalone Deployment Shim (Option A only)

> This section applies only if Option A is chosen. Skip if Option B is the implementation path.

Phase 1 makes targeted changes to the existing service endpoint to work standalone, deferring the inference path unification to a follow-on phase. The individual changes are:

**`/v2/chat/completions` standalone endpoint**: A route registered only when `GUARDRAILS_STANDALONE=true`, mapping to the `default` workspace handler. No workspace in the path — reflects that standalone is single-tenant.

`**GUARDRAILS_STANDALONE` mode**: Env var that skips platform dependency checks at startup, wires a `FilesystemConfigStore` in place of `EntityClient`, and disables platform auth middleware.

**`FilesystemConfigStore`**: Scans `CONFIG_STORE_PATH` at startup and loads flat `.yaml` files into an in-memory dict keyed by filename. Workspace is not a concept in standalone mode — `get()` and `list()` ignore the workspace parameter. No database involvement.

**Direct model URL support**: `model_routing.py` is modified to resolve models in priority order: (1) literal `base_url` in the config YAML, (2) `NIM_ENDPOINT_URL` env var, (3) IGW entity resolution. Steps 1 and 2 bypass IGW entirely.

**Deployment artifacts**: Reference `Dockerfile` and Helm chart at `deploy/helm/guardrails/`.

The Phase 1 `FilesystemConfigStore` and model URL resolution are replaced when Phase 2 lands — they become `FilesystemConfigStore` (implementing `ConfigStore`) and `DirectUrlModelResolver` (implementing `ModelResolver`) respectively, with no behavioral change for users.