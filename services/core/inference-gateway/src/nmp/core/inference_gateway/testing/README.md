# IGW Middleware Plugin Test Harness

Integration test infrastructure for `NemoInferenceMiddleware` plugins.

Tests exercise the real IGW + Models request pipeline against a single
`pytest_httpserver` socket that stands in for the upstream NIM. Plugin
code (`process_request`, `process_response`, `process_post_response`)
runs with its production implementation — the only mock is the upstream
model provider itself, which every offline test needs.

The heavy ASGI stack (FastAPI app, SQLite-backed entity store, dependency
wiring, `/health/ready` polling, default workspace + project seeding) is
**module-scoped**: it is built once per test file and shared across every
test in the module. Per-test concerns (global-cache resets,
`MockChatCompletionsHandler` mount, post-response task list re-init,
entity teardown) still run per test. See [Module scope and xdist](#module-scope-and-xdist)
for the constraints this imposes on the pytest command line.

## Quick start

### 1. Re-export the fixtures in your plugin's `conftest.py`

```python
# plugins/<your-plugin>/tests/integration/conftest.py
from nmp.core.inference_gateway.testing.fixtures import (
    _igw_app_context,
    _igw_extra_services,
    igw_plugin_harness,
)

__all__ = ["_igw_app_context", "_igw_extra_services", "igw_plugin_harness"]
```

`_igw_app_context` and `_igw_extra_services` are the module-scoped
helpers `igw_plugin_harness` depends on; pytest needs them in the same
conftest scope to resolve the dependency chain. If you use
`igw_loopback_harness`, additionally re-export `_igw_loopback_context`.

#### Mounting extra services

To mount additional services on the module-scoped app (e.g.
`GuardrailsService` for entity-backed guardrail-config tests), override
`_igw_extra_services` in your conftest:

```python
@pytest.fixture(scope="module")
def _igw_extra_services() -> tuple[ServiceFactory, ...]:
    return (GuardrailsService,)
```

This is module-scoped because the app context itself is module-scoped —
the service list cannot change mid-module.

### 2. Write a test

```python
from nmp.core.inference_gateway.testing.harness import IGWPluginHarness
from nmp.testing.mock_chat_completions import ChatCompletion, chat_completion


def test_safe_input_reaches_backend(igw_plugin_harness: IGWPluginHarness) -> None:
    h = igw_plugin_harness

    # Queue a canned response for the upstream model.
    h.mock_chat_completions("my-model", responses=[ChatCompletion(body=chat_completion(content="Hello!"))])

    # Create a provider whose host_url points at the mock NIM.
    h.add_provider(workspace="default", served_models={"my-model": "my-model"})

    # Register your plugin and create a VirtualModel that uses it.
    with h.load_plugin("nemo-my-plugin"):
        h.add_virtual_model(
            workspace="default",
            name="my-vm",
            default_model_entity="default/my-model",
            request_middleware=[{"name": "nemo-my-plugin", "config_type": "...", "config": {}}],
        )

        response = h.chat_completions(
            workspace="default",
            body={"model": "my-vm", "messages": [{"role": "user", "content": "hi"}]},
        )

    h.assert_called_once("my-model")
    assert response["choices"][0]["message"]["content"] == "Hello!"
```

### 3. Choose a fixture

| Fixture | When to use |
|---|---|
| `igw_plugin_harness` | Default. No real port for IGW; plugin outbound HTTP goes directly to the mock NIM via `nim_base_url`. |
| `igw_loopback_harness` | Factory for tests where plugin outbound HTTP needs to traverse IGW (e.g. the plugin calls `get_openai_compatible_inference_url_and_model` and the resulting URL must be reachable). Call `h = igw_loopback_harness()`. Extra service classes are accepted for source compatibility but ignored — mount them via `_igw_extra_services` instead. Costs a (module-scoped) uvicorn thread + per-test `aiohttp.ClientSession` override. The `per_request_http_client` dependency override is scoped per-loopback-test so plain `igw_plugin_harness` tests in the same module don't pay the per-request session cost. |

### 4. Choose a plugin registration method

| Method | When to use |
|---|---|
| `load_plugin(name)` | Plugin is pip-installed. Discovers via the `nemo.inference_middleware` entry-point group — same path as production. **Preferred.** |
| `use_plugin(name, instance)` | Plugin is not installable (workspace-only), or you need a `MagicMock(spec=...)`. |

Both default to `call_lifecycle=True` (runs `on_startup` / `on_shutdown`).
Async variants: `aload_plugin`, `ause_plugin`.

## What is real

These run the same code as production:

1. **IGW + Models FastAPI apps** — same constructors, routers, dependency wiring.
2. **Full IGW request pipeline** — `virtual_model_proxy` → request middleware → proxy step → response middleware → post-response fire-and-forget.
3. **Plugin code** — `process_request` / `process_response` / `process_post_response` are the production methods.
4. **Real HTTP from IGW to the upstream** — `aiohttp` connects to `pytest_httpserver` over a real socket. Header dropping, body framing, content-length all behave as in production.
5. **Real HTTP from plugin outbound calls** — plugin-originated requests (e.g. Guardrails' rail calls) terminate at the same socket.
6. **SDK clients** — `NeMoPlatform` (sync) and `AsyncNeMoPlatform` (async) via `httpx.ASGITransport`.
7. **Entity store** — in-memory; entities created via the SDK persist and are read back during cache refreshes.
8. **Cache refresh** — `refresh_virtual_model_cache` and `refresh_model_cache` with real implementations.
9. **Middleware config pre-resolution** — `validate_middleware_config` runs for every VM with middleware entries.

## What is mocked or substituted

1. **The upstream NIM** — `MockChatCompletionsHandler` serves canned responses. The only unavoidable mock.
2. **SDK transport** — `httpx.ASGITransport` (no real port for IGW). The loopback variant adds a real port.
3. **Plugin discovery** — bypassed when using `use_plugin`. Use `load_plugin` for production parity.
4. **`get_platform_config()`** — patched in the loopback variant so the resolver returns the loopback URL.
5. **`global_http_client`** — replaced with per-request sessions in the loopback variant (loop-binding workaround).
6. **Passthrough VM auto-creation** — the `provider_reconciler` doesn't run. Tests needing the resolver must create passthrough VMs manually.
7. **Background cache-refresh task** — explicitly disabled in the module-scoped app context (`refresh_model_cache_interval_sec=0`). Tests refresh synchronously inside `add_provider` / `add_virtual_model`. Without this, the 3-second background loop would re-list providers cross-workspace between tests in the same module and re-populate the cache with stale rows.
8. **Authorization** — disabled by default (`auth_enabled=False`).

## What cannot be tested

- **Multi-worker cache consistency** — caches are process-local globals.
- **Production-typical timings** — cache cold-start, background refresh races.
- **Real upstream error shapes** — real NIMs return varying error envelopes; the mock returns controlled shapes.
- **OPA / authz** — disabled by default; no integration test exercises it.
- **Rate limiting, retries, circuit breaking** — none of these layers exist in the harness.

## API reference

### Setup

| Method | Description |
|---|---|
| `add_provider(workspace, served_models, ...)` | Register a `ModelProvider` routed at the mock NIM. Call **before** `add_virtual_model`. Tracked for entity-store cleanup. |
| `add_virtual_model(workspace, name, ...)` | Create a `VirtualModel` and refresh caches so it routes immediately. Tracked for entity-store cleanup. |
| `create_secret(workspace, name, value, ...)` | Create a Secret via the SDK and track it for harness cleanup. Use this instead of `harness.sdk.secrets.create(...)` so the secret is deleted between tests in a module-scoped fixture. |
| `mock_chat_completions(model, responses)` | Queue mock responses for a model. Responses are consumed in order; the last is reused if drained. |
| `load_plugin(name)` / `use_plugin(name, instance)` | Register a plugin (context manager). |
| `refresh_caches()` | Full model + VM cache refresh. Needed when `api_key_secret_name` is set on a provider. |

### Workspace

`harness.workspace` — the workspace name the module-scoped fixture
seeded (`"default"` today). Reach for it instead of a literal
`"default"` so test bodies stay portable if the harness ever migrates
to per-test workspaces. Today it's a constant; tomorrow a per-test
fixture change is all that's needed.

### Inference

| Method | Description |
|---|---|
| `chat_completions(workspace, body)` | Non-streaming chat completion via the SDK. |
| `stream_chat_completions(workspace, body)` | Streaming chat completion. Returns parsed SSE chunks (`list[dict]`) for `text/event-stream` responses, or the raw JSON body (`dict`) when a plugin short-circuits with an immediate response. |
| `achat_completions(workspace, body)` | Async sibling of `chat_completions`. |

### Assertions

| Method | Description |
|---|---|
| `assert_called_once(model)` | Model received exactly one request. |
| `assert_call_count(model, n)` | Model received exactly `n` requests. |
| `assert_no_calls_to(model)` | Model received zero requests. |
| `assert_call_order([m1, m2, ...])` | Models were called in this exact sequence. |
| `assert_request_messages_contain(model, substring, *, index=0)` | The `index`-th request's messages contain `substring`. |
| `assert_request_body_for(model, predicate, *, index=0)` | `predicate(body)` is true for the `index`-th request. |
| `assert_request_path_for(model, path, *, index=0)` | The `index`-th request arrived on `path`. |
| `assert_request_headers_contain(model, header, value=None, *, index=0)` | The `index`-th request carries `header` (optionally matching `value`). |
| `requests_for(model)` | Return all `RecordedRequest` objects for `model`. |

### Post-response

| Method | Description |
|---|---|
| `aflush_post_response()` | Await all fire-and-forget post-response tasks scheduled so far. Must be called from an async test after `achat_completions`. |

### Mock response types

Defined in `nmp.testing.mock_chat_completions`:

| Type | Description |
|---|---|
| `ChatCompletion(body, status_code=200)` | Non-streaming JSON response. |
| `ChatCompletionStream(chunks, status_code=200)` | Streaming SSE response. |
| `ErrorResponse(status_code, body)` | Error response (status >= 400). |
| `chat_completion(content, model, ...)` | Builder for a non-streaming response body. |
| `chat_completion_chunk(content, model, ...)` | Builder for a single SSE chunk body. |

## Module scope and xdist

The expensive ASGI stack (FastAPI app, IGW + Models services, SQLite
entity store, dependency wiring, default workspace + project seeding)
is wrapped in `_igw_app_context`, which is `scope="module"`. Without
this, every parametrised test pays the full `~3–10s` build cost; with
it, the build amortises across the module and only the cheap per-test
concerns (cache resets, mock NIM handler mount, entity teardown) run
per test.

**xdist requirement.** Module scope is preserved under
`--dist=loadfile` (one file per worker) and `--dist=loadscope` (one
fixture scope per worker). The default `--dist=load` distributes
**individual tests** across workers, which means each worker rebuilds
the module-scoped app from scratch — defeating the optimization. Run
integration tests with:

```bash
uv run --frozen pytest plugins/<plugin>/tests/integration --dist=loadfile -n auto
```

or

```bash
uv run --frozen pytest plugins/<plugin>/tests/integration --dist=loadscope -n auto
```

`loadfile` is the safer default — it also forces every test in a file
to run on the same worker, which matches the fixture lifecycle exactly.

## Entity teardown across tests

`IGWPluginHarness` tracks every entity it creates and deletes them
via the SDK on test teardown, in dependency order: virtual models →
providers → secrets. Each delete is `try/except`-guarded with
`logger.warning` so a single failure can't mask the test's own
failure.

**This is only true for entities created through the harness.** If a
test calls `harness.sdk.secrets.create(...)` directly (or any other
entity-store API not mediated by the harness), the entity will leak
across tests in a module-scoped fixture and may be picked up by the
next `refresh_model_cache` — triggering plugin `notify_upserted` on a
dead VM, or causing `add_provider` to see stale `ModelProviderInfo`
rows.

If you need to create an entity outside the harness's create methods,
add tracking yourself (`harness._secrets.append((workspace, name))`)
or delete the entity explicitly in a `try/finally` around the test
body. For Secrets specifically, use `harness.create_secret(...)` —
it tracks for you.

After deletion, the runtime caches are also rebuilt: middleware
registry entries for deleted VMs are evicted, the VM cache is rebuilt
without them, and the model cache's `workspace_name_provider_map` is
pruned of deleted providers and the entity map rebuilt. This guards
against the in-process caches getting out of sync with the entity
store and keeps the next test's `add_provider` fast-path from seeing
ghost `ModelProviderInfo` rows.

## Plugin lifecycle and shared SDK clients

`use_plugin` / `load_plugin` (and their async siblings) run the
plugin's `on_startup` on enter and `on_shutdown` on exit. When the
harness fixture was function-scoped, the entire test client and its
shared SDK HTTP client were rebuilt per test, so a plugin's
`on_shutdown` could safely call `await sdk.close()` — closing the
shared client was a no-op for the next test (which got a fresh
client).

With the module-scoped app, the shared SDK HTTP client lives across
tests. A plugin's `on_shutdown` calling `await sdk.close()` (as
`nemo-guardrails` does) would close the shared client and break every
subsequent test in the module, including the periodic
`refresh_model_cache_task`'s SDK calls.

The module-scoped app context monkey-patches the shared client's
`aclose` to a no-op for the lifetime of the module. The `ASGITransport`
uses in-process connections, so skipping `aclose` has no real-resource
leak. Plugin authors don't need to do anything special — `on_shutdown`
still runs, its other side effects still take effect, only the close
call is short-circuited.

If you're writing a plugin that owns resources separate from the
shared SDK (custom connection pools, background tasks, on-disk
caches), close those in `on_shutdown` as you normally would. Only the
shared SDK's close is intercepted.

## Limitations under module scope

A few patterns that worked under the previous function-scoped
fixture quietly stop working — or stop working *correctly* — when the
ASGI stack is module-scoped. Avoid these:

* **Function-scoped autouse `monkeypatch` fixtures that need to
  affect service startup.** The module-scoped `_igw_app_context`
  builds the FastAPI app — including every service's `on_startup` —
  before any function-scoped fixture runs, so a `monkeypatch.setenv`
  in a per-test autouse fixture lands after the service has already
  observed the env var. If you need a value in place before service
  startup, set it at conftest import time
  (`os.environ.setdefault(...)` at module level) or in a
  `scope="module", autouse=True` fixture that depends on
  `_igw_app_context` indirectly (so pytest orders it after the env
  var is set but before the harness is built). The `nemo-guardrails`
  conftest's `HF_HUB_OFFLINE` setup is the worked example.
* **Direct `harness.sdk.<entity>.create(...)` calls.** Anything
  created outside the harness's track-and-delete methods leaks across
  tests in the module. See [Entity teardown across tests](#entity-teardown-across-tests).
* **Per-test extra services to `igw_loopback_harness`.** Previously
  `harness = igw_loopback_harness(GuardrailsService)` would mount
  extras per call; that now raises `TypeError` because the
  module-scoped app is already built. Override the
  `_igw_extra_services` module fixture in your conftest instead.
* **Plugins registered persistently at app startup** (via the
  `nemo.inference_middleware` entry-point group) won't receive
  `on_virtual_model_destroyed`-style callbacks on test teardown —
  only `registry.evict(...)` runs. Plugins that need cleanup
  notifications between tests should be registered per-test via
  `harness.use_plugin(...)` / `harness.load_plugin(...)` so the
  plugin instance itself is discarded with the test.
* **Module-shared state in plugin instances under `load_plugin`.**
  `load_plugin` instantiates a fresh plugin class per test, so
  *instance* state is per-test, but class-level state (singletons,
  caches stored on the class) is shared across the module. Keep
  caches on the instance.

## File layout

```
nmp.core.inference_gateway.testing/
├── harness.py        # IGWPluginHarness, IGWLoopbackHarness
├── fixtures.py       # igw_plugin_harness, igw_loopback_harness (pytest fixtures)
├── _loopback.py      # serve_app_in_thread, per_request_http_client, override_platform_base_url
└── README.md         # this file

nmp.testing/
└── mock_chat_completions.py   # MockChatCompletionsHandler, ChatCompletion, ChatCompletionStream, etc.
```
