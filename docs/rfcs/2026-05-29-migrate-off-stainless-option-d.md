# Design: Option D — Reuse existing assets (Stainless migration)

**Status:** Draft
**Author:** Max Dubrinsky
**Linear:** AALGO-216
**Parent RFC:** [2026-05-29-migrate-off-stainless.md](./2026-05-29-migrate-off-stainless.md)

## Why this doc

The parent RFC tentatively lands on **Option D** (drop Stainless, publish server-side
Pydantic types, apply the proven plugin-SDK pattern to thin-core resources). This
follow-up is the deep dive: it validates Option D against the actual code, corrects
one load-bearing misconception in the original framing, and turns "small day-1 cost"
into a concrete work breakdown.

The headline correction: the patterns we planned to reuse (`EntityClient`, the
plugin-SDK resources) are **not** SDK replacements — they are layered *on top of* the
generated SDK's hand-written runtime. So "reproduce the SDK with a good httpx client"
really means **own a thin client runtime and drop the generated resource/type tree on
top of it**, not "publish types and write resource classes." Once that's understood,
Option D gets *smaller*, not larger, than the RFC implied.

## Decisions reached

1. **Own the client runtime, but split it.** The runtime welds together two layers.
   Keep **Layer 1 (transport)**; delete **Layer 2 (typed-casting machinery)**. See
   [Runtime: two layers](#runtime-two-layers).
2. **Types are plain server-side Pydantic models.** No "Stainless-style" base class.
   The runtime currently *enforces* its own base model — we remove that.
3. **Core resources are statically typed**, EntityClient-style, mounted as real client
   attributes. Plugin resources stay dynamically mounted via `nemo.sdk` /
   `__getattr__` (the `Any` cost is acceptable for a handful of plugin namespaces).
   Static typing is the priority; dynamic typing is a bug in potentia.
4. **Retire the CLI generator; hand-author the curated CLI**, and **dogfood** the
   `NemoCLI` contract so core and plugins build CLIs the same way. The generated CLI
   is an artifact of needing to blanket-expose every resource; we already curate
   heavily (e.g. `entities` is deliberately omitted), so generation buys little.
5. **Keep both sync and async surfaces** for now, but implement as **async-core + a
   thin sync shim** rather than two fully hand-maintained clients.
6. **`files` (multipart) and `inference` (streaming) are non-negotiable day-1.** They
   are the two resources that exercise Layer 1's non-CRUD paths, so they anchor the
   runtime work.
7. **Break the `sdk ↔ plugin` dependency cycle** by inverting it into a clean DAG.

## Findings that reshaped the plan

### The reuse patterns sit on the runtime, not beside it

- `EntityClient` (`packages/nmp_common/src/nmp/common/entities/client.py`) wraps
  `AsyncEntitiesResource` and imports `ConflictError`, `NotFoundError`,
  `UnprocessableEntityError`, `omit`, `DeleteResponse`, `Entity` — all from
  `nemo_platform`. It even round-trips through the generic SDK `Entity` and
  re-validates into the real model (`_convert_api_entity_to_model`).
- The plugin pattern (`plugins/nemo-evaluator/src/nemo_evaluator/sdk/resources.py`)
  takes a `NeMoPlatform`/`AsyncNeMoPlatform`, reaches into `platform._client` (the
  httpx transport), does raw `get()` + `Model.model_validate(response.json())`.

Both depend on the SDK *client* for transport, base-url, header injection, and
`.with_options()`. That client is the load-bearing artifact.

### The runtime is already ours

`sdk/python/nemo-platform/src/nemo_platform/_base_client.py` is Apache-2.0,
NVIDIA-copyright, **checked into the repo** (~2.1k LOC, standard httpx-runtime
lineage). Stainless regenerates it but it barely changes. The thing that actually
decays and bloats is the resource/type tree on top: **139,245 LOC across 1,149
files, ~10% ever imported** (per parent RFC).

### The runtime enforces "Stainless-style" types — and we'll delete that

`sdk/python/nemo-platform/src/nemo_platform/_response.py:253-262` raises a hard error
if you hand it a plain Pydantic model:

```python
if (inspect.isclass(origin)
    and not issubclass(origin, BaseModel)          # Stainless's _models.BaseModel
    and issubclass(origin, pydantic.BaseModel)):   # a plain Pydantic model
    raise TypeError("Pydantic models must subclass our base model type, "
                    "e.g. `from nemo_platform import BaseModel`")
```

This is the "maintain Stainless style to reuse the runtime" tax, written into code.
Since we own the runtime, we delete this guard and simplify `_process_response_data`
to `cast_to.model_validate(data)` for the model case.

### CLI generation is the deepest coupling — and avoidable

- CLI commands under `nemo_platform_ext/cli/commands/api/` are **build-time generated**
  by `nemo-platform-sdk-tools generate-cli`, which **introspects the SDK resource
  classes** via `inspect` (`.../cli_generator/sdk_introspector.py`: `importlib`,
  `inspect.getmembers`, `inspect.signature`, `get_type_hints`). Structure follows
  `sdk/stainless.yaml`.
- **Everything else in the CLI is already hand-authored Typer**: `commands/config.py`,
  `commands/use_cases/`, `commands/quickstart/`, and **every plugin CLI** via
  `NemoCLI.get_cli()` (`packages/nemo_platform_plugin/src/nemo_platform_plugin/cli.py`).
- `nemo-platform-plugin` ships `cli.py` as the CLI **contract** (the `NemoCLI` ABC +
  renderers), registers **no `nemo.cli` entry point**, and ships no commands. It is the
  authoring kit plugins import — the same kit core can dogfood.

So generation is load-bearing for exactly one subtree, which exists only to expose
all resources. Curation removes the need for it.

### The dependency cycle

`nemo-platform-sdk` depends on `nemo-platform-plugin` (sdk pyproject) **and**
`nemo-platform-plugin` depends on `nemo-platform-sdk` (plugin pyproject). Bidirectional,
tolerated only because they are co-vendored. Option D is a chance to fix it.

## Target architecture

### Runtime: two layers

| Layer | Contents | Disposition |
|---|---|---|
| **L1 — transport** | httpx wrapper, retry/backoff, timeouts, pooling, `.with_options()` cloning (used everywhere by `sdk_factory` for auth/on-behalf-of), `_prepare_url` service routing, error→exception mapping (round-tripped by `register_sdk_exception_handlers`), streaming, pagination, multipart | **Keep & own.** Net deletion after trimming. |
| **L2 — typed casting** | `cast_to[ResponseT]`, custom `_models.BaseModel` (967 LOC), response-casting (`_response.py`), `*Resource` / `with_raw_response` / `with_streaming_response` scaffolding | **Drop.** Exists so a *generated* client can be generic over arbitrary type trees — which we do not need. |

After the split, resource methods call `self._client.get(..., cast_to=OurServerSideModel)`
and the simplified parser does `OurServerSideModel.model_validate(json)` — full L1
reuse, plain Pydantic types, no Stainless base class.

### Package / dependency graph

Current (cycle + fat hub):

```
nemo-platform (wrapper)
 ├── nemo-platform-sdk   ◄── 139k LOC generated tree + ships `nemo` CLI
 │     └── nemo-platform-plugin ──┐ (depends back on sdk)  ⇅ CYCLE
 │     [vendors ext, models, filesets, data_designer_sdk,
 │      safe_synthesizer_sdk, nemo_evaluator_sdk]
 ├── nemo-platform-plugin ────────┘
 └── nmp-common ── → {plugin, sdk}
```

Target (clean DAG):

```
nemo-platform-types        pure server-side Pydantic models (deps: pydantic)
      ▲
nemo-platform-client       owned L1 runtime + hand-written core resource clients
      ▲                    (deps: httpx, pydantic, nemo-platform-types)
      │                    client→plugin is LAZY/optional (plugin mounting via
      │                    discover_sdk() activates only if the contract is installed)
nemo-platform-plugin       contract: NemoCLI, NemoService, NemoPluginSDKResources,
      ▲                    discovery, EntityBase   (deps: client + types)
      │
 ┌────┴───────────┬──────────────────────┐
nmp-common   nemo-platform-ext         plugins (evaluator, …)
             (ships `nemo` CLI;          (nemo.sdk resources + nemo.cli Typer)
              dogfoods NemoCLI)
      ▲             ▲                          ▲
      └─────────────┴──────────────────────────┘
                nemo-platform (wrapper)
```

The cycle inverts: `plugin → client` is a hard dep; `client → plugin` is the existing
lazy in-method import in `__getattr__`, so the client need not *declare* a dependency
on the contract. Plugin mounting becomes an optional capability.

**Open layering item:** `EntityBase` / `EntityClient` live in
`nemo_platform_plugin.entities` today and import SDK symbols directly. To keep the DAG
acyclic they slide *down* into `client` (or `types`). This is the same "server-side vs
client-importable type boundary" work the parent RFC already flags as Option D's
primary risk — relocated, not new.

### CLI

```
CLI = hand-authored Typer, all of it:
  • core groups dogfood NemoCLI (curated; call the typed resource clients)
  • plugin groups via NemoCLI (nemo.cli)                         ← unchanged
  • shared authoring kit: nemo_platform_plugin.cli + cli/core helpers
Generator (nemo-platform-sdk-tools/cli_generator): deleted.
Stainless: deleted.  OpenAPI: kept as a published contract/docs artifact, off the
                              critical path (still produced by `make refresh-openapi`).
```

Hand-written command bodies are *better*-typed than today's generated ones: each calls
a statically typed resource client, so signature drift surfaces as a `ty` error rather
than a silently-broken generated command.

## Work breakdown & sizing

### (A) Carve out + simplify the runtime — *net deletion*

Extract L1 into `nemo-platform-client`; delete the `_response.py:253-262` guard;
simplify `_process_response_data` to plain `model_validate`; gut most of `_models.py`
(967 LOC) and `_response.py`; drop `*Resource` scaffolding. Focused ~1–2 day edit that
removes more than it adds. Must preserve: retries, streaming, pagination, multipart,
error mapping.

### (B) Hand-write core resource clients — ~2.5–3.5k LOC (or ~1.3–2k async-core)

Replaces **41,084 LOC** of generated core resources. Reference density: evaluator
plugin = 207 LOC for ~8 method bodies; generated `models.py` = 981 LOC for ~5 CRUD
methods. Curated surface (plugin domains — guardrail, safe_synthesizer, evaluation,
audit — leave with their plugins):

| Core resource | ~methods | notes |
|---|---|---|
| entities | — | already done (`EntityClient`) |
| models (+adapters) | ~8 | CRUD + sub-resource |
| files | ~8 | **multipart upload/download — day-1, exercises L1** |
| secrets | ~6 | |
| jobs | ~7 | |
| iam / members / projects / workspaces | ~4 each | mostly CRUD |
| inference (+gateway/providers/virtual-models/deployments) | ~30–45 | **streaming — day-1, exercises L1**; the heavy one |

~80–110 public methods (sync side). Mechanical, templatable. With **async-core + thin
sync shim** the hand-written surface roughly halves vs. two full clients.

### (C) Port + dogfood the CLI

Port the *keepers* from the generated `commands/api/` tree (a free reference) into
hand-authored `NemoCLI`-shaped groups that call the typed resource clients. Add a
core-CLI mount path so core dogfoods the same contract plugins use. Curation continues
as a deliberate act (nothing reaches the CLI unless added).

### Types — ~0 new code, real boundary hygiene

Publish/import the ~270 existing server-side Pydantic models. The work is ensuring no
server-only fields/validators leak into the client-importable surface (the parent RFC's
named risk), not writing types.

## Cutover

Per the parent RFC: run the frozen Stainless artifact as a no-op holdover for
un-migrated domains. Each domain peels off behind the new client + curated CLI at its
own pace. `files` and `inference` must be in the first migrated set (day-1 features).

## Open questions

- **Types packaging:** standalone `nemo-platform-types` dist vs. fold types into
  `nemo-platform-client`. The DAG shape is identical either way; this is a
  publish/versioning call. *Leaning: a thin `nemo-platform-types` layer so the contract
  and runtime share one type source without a cycle.*
- **`EntityBase`/`EntityClient` relocation** target (`client` vs `types`) — see layering
  item above.
- **Runtime ownership flavor:** own-and-simplify L1 (recommended — keeps
  retries/streaming/error-mapping) vs. lighter plugin-style manual validate (less owned
  code, but re-implements those). *Recommended: own-and-simplify.*
- **Sync shim mechanism:** generated from the async core vs. hand-thin-wrapped.
- **Consumer inventory** (carried from parent RFC): who imports `nemo_platform.*` and
  from where, required before freezing the generator for cutover.
