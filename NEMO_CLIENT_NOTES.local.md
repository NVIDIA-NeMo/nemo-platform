# NemoClient — Design Notes & TODOs

Tracking file for the typed HTTP client work in `nemo_platform_plugin/client/`.

## What we built

A typed endpoint/client system where:
- **`BodyEndpoint[PathT, RequestT, ResponseT]`** / **`NoBodyEndpoint[PathT, ResponseT]`** — frozen dataclasses linking a URL template to typed path params, request body (if any), and response body. `BodyEndpoint.request(payload, **path_params)` requires payload; `NoBodyEndpoint.request(**path_params)` has no payload parameter. `Endpoint` is a union alias of both. Constructed via standalone factory functions `get()`, `post()`, `patch()`, `delete()`.
- **`PreparedRequest[ResponseT]`** — frozen dataclass produced by calling `.request()` on an endpoint. Carries the path template, path params dict, method, body, and response type. Path interpolation is deferred to `send()`.
- **`NemoResponse[ResponseT]`** — frozen dataclass wrapping the full `httpx.Response` and a parsed Pydantic body. `.data()` for the common "give me the body or raise" case.
- **`NemoBinaryResponse`** / **`AsyncNemoBinaryResponse`** — streaming binary response. Context manager, iterable over byte chunks.
- **`NemoStreamResponse[ModelT]`** / **`AsyncNemoStreamResponse[ModelT]`** — streaming NDJSON response. Context manager, iterable over parsed Pydantic models.
- **`BinaryStream`** — marker type for endpoints that return raw bytes.
- **`Stream[ModelT]`** — marker type for endpoints that return a stream of typed JSON objects.
- **`BasePath(TypedDict)`** — base class for all path TypedDicts. `PathT` is `bound=BasePath`.
- **`BaseNemoClient`** — shared logic: path resolution (merging client defaults + explicit params + format_map), JSON serialization, stream/binary detection.
- **`NemoClient` / `AsyncNemoClient`** — sync/async subclasses that own an httpx client and implement overloaded `send()`.
- **Path params are typed via `TypedDict` + `Unpack`** — the type checker enforces correct kwargs at the call site.
- **Workspace** can be set on the client and auto-injected into `{workspace}` in paths. Path TypedDicts use `NotRequired[str]` for workspace so it's optional at the call site. Explicit per-call values override the client default.
- **Path interpolation happens in `_resolve_path()` at `send()` time** — client defaults are merged with explicit params, then `format_map` runs. Missing params raise `ValueError` with a clear message.
- **Endpoint naming convention** — PascalCase (e.g. `CreateItemEndpoint`), not UPPER_SNAKE.

## File layout

```
packages/nemo_platform_plugin/src/nemo_platform_plugin/client/
├── endpoint.py     # BasePath, BinaryStream, Stream, PreparedRequest, BodyEndpoint, NoBodyEndpoint, get/post/patch/delete
├── client.py       # BaseNemoClient, NemoClient, AsyncNemoClient
└── response.py     # NemoResponse, NemoBinaryResponse, AsyncNemoBinaryResponse, NemoStreamResponse, AsyncNemoStreamResponse, NemoHTTPError

plugins/example-plugin/src/nemo_example_plugin/
├── types/
│   ├── payloads.py   # Plain Pydantic request/response models
│   └── endpoints.py  # Endpoint definitions + path TypedDicts
├── schema.py         # Server-side filters only
└── sdk.py            # ExampleClient(NemoClient), AsyncExampleClient(AsyncNemoClient)
```

## Key type decisions

- `RequestT` bound is `BaseModel` — payload is required on `BodyEndpoint`, absent on `NoBodyEndpoint`.
- `ResponseT` bound is `BaseModel | BinaryStream | Stream | None` — covers all four response kinds.
- `PathT` bound is `BasePath` — enforces that path types are TypedDict subclasses.
- Generic order is `[PathT, RequestT, ResponseT]` — path first since it's always present.
- Factory functions instead of classmethods — `ty` can't infer class-level TypeVars from classmethod/staticmethod args ([astral-sh/ty#541](https://github.com/astral-sh/ty/issues/541)). Standalone functions infer correctly. Repro in `ty_classmethod_repro.py`.
- `path_type` is always required on factory functions.

## Overloaded `send()` dispatch

The `send()` method is overloaded based on `ResponseT`:

| `ResponseT` | `send()` returns (sync) | `send()` returns (async) |
|---|---|---|
| `BaseModel` subclass | `NemoResponse[T]` | `NemoResponse[T]` |
| `None` | `NemoResponse[None]` | `NemoResponse[None]` |
| `BinaryStream` | `NemoBinaryResponse` | `AsyncNemoBinaryResponse` |
| `Stream[T]` | `NemoStreamResponse[T]` | `AsyncNemoStreamResponse[T]` |

Runtime dispatch uses:
- `_is_binary()` — checks `response_type is BinaryStream`
- `_is_stream()` — checks `get_origin(response_type) is Stream`, extracts `ModelT` via `get_args()`
- Binary/stream responses use httpx's `stream()` context manager for lazy iteration
- Binary/stream response objects are context managers — caller uses `with`/`async with` to close the connection

## Known `ty` limitation

`ty` cannot infer class-level TypeVars from classmethod/staticmethod arguments on generic classes ([astral-sh/ty#541](https://github.com/astral-sh/ty/issues/541)). Standalone factory functions work correctly. This is why we use `get()`, `post()`, etc. instead of `Endpoint.get()`, `Endpoint.post()`.

## TODOs

### Near-term
- [ ] Wire `ExampleClient` into the plugin SDK registration system (`NemoPluginSDKResources` currently expects a `NeMoPlatform`-taking constructor — needs updating or replacing)
- [ ] Add server-side helpers that derive FastAPI routes from the same endpoint definitions (shared contract)
- [ ] Consider whether `NemoPluginSDKResources` should be replaced entirely now that clients own their own httpx

### Streaming & binary
- [ ] Handle upload (binary request body) — decide on approach
- [ ] Handle streaming uploads — request body is a stream (e.g. large file upload), not just bytes
- [ ] Handle pagination — list endpoints return `NemoListResponse[T]` with page/page_size/total; client should support iterating pages or auto-paginating

### Medium-term
- [ ] Migrate core service clients (Files, Entities, etc.) to use `NemoClient` instead of raw `platform._client`
- [ ] Eventually replace `NeMoPlatform` with `NemoClient` as the primary SDK entry point
- [ ] Make the client agnostic to the underlying HTTP library — abstract the transport so we can swap httpx for aiohttp, pyreqwest, etc. without changing endpoint definitions or consumer code

### Open questions
- How do we handle auth? Currently `default_headers` is the escape hatch — should there be first-class token/auth support?
