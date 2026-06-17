# NemoClient — Design Notes & TODOs

Tracking file for the typed HTTP client work in `nemo_platform_plugin/client/`.

## What we built

A typed endpoint/client system where:
- **`BodyEndpoint[PathT, RequestT, ResponseT]`** / **`BinaryBodyEndpoint[PathT, ResponseT]`** / **`NoBodyEndpoint[PathT, ResponseT]`** — endpoint classes that are also descriptors. When assigned as class attributes on a `NemoClient`/`AsyncNemoClient` subclass, accessing them returns sync/async bound callables with the right `__call__` signature.
- **`PreparedRequest[ResponseT]`** — frozen dataclass carrying path template, path params, content, content type, and response type. Path interpolation is deferred to `send()`.
- **`NemoResponse[ResponseT]`** — frozen dataclass wrapping `httpx.Response` and parsed body. `.data()` for unwrap-or-raise.
- **`NemoBinaryResponse`** / **`AsyncNemoBinaryResponse`** — streaming binary responses. Context managers with `read()` and `__iter__`/`__aiter__`.
- **`NemoStreamResponse[ModelT]`** / **`AsyncNemoStreamResponse[ModelT]`** — streaming NDJSON responses. Context managers with model-parsing iteration.
- **`BinaryContent`** — marker type for binary request/response (unified, used in both positions).
- **`Stream[ModelT]`** — marker type for NDJSON streaming responses.
- **`BasePath(TypedDict)`** — base for all path TypedDicts. `PathT` is `bound=BasePath`.
- **`BaseNemoClient`** — shared logic: path resolution (merging client defaults + explicit params + `format_map` with `ValueError` on missing params), stream/binary detection.
- **`NemoClient` / `AsyncNemoClient`** — sync/async subclasses with overloaded `send()` that dispatches return type based on `ResponseT`.
- **Descriptor pattern** — endpoints have `__get__` overloaded on `NemoClient` vs `AsyncNemoClient`. Returns `SyncBound*Call` or `AsyncBound*Call`. No metaclass, no plugin — just the standard descriptor protocol.
- **Endpoint mixin pattern** — define endpoints once in a mixin class, then sync/async client classes inherit the mixin + client base.
- **Adapter** — `from_platform()` / `async_from_platform()` bridge `NeMoPlatform` to `NemoClient` for backward compatibility with `NemoPluginSDKResources`.
- **Path params typed via `TypedDict` + `Unpack`** with `NotRequired[str]` for workspace (client default fills it in).

## File layout

```
packages/nemo_platform_plugin/src/nemo_platform_plugin/client/
├── types.py        # BasePath, BinaryContent, Stream, PreparedRequest, TypeVars
├── endpoint.py     # BodyEndpoint, BinaryBodyEndpoint, NoBodyEndpoint, bound callables, factory functions
├── client.py       # BaseNemoClient, NemoClient, AsyncNemoClient
├── response.py     # NemoResponse, NemoBinaryResponse, AsyncNemoBinaryResponse, NemoStreamResponse, AsyncNemoStreamResponse, NemoHTTPError
└── adapter.py      # from_platform(), async_from_platform()

plugins/example-plugin/src/nemo_example_plugin/
├── types/
│   ├── payloads.py   # Plain Pydantic request/response models
│   └── endpoints.py  # Endpoint definitions + path TypedDicts
├── schema.py         # Server-side filters only
└── sdk.py            # _ExampleEndpoints mixin, ExampleClient, AsyncExampleClient, NemoPluginSDKResources registration
```

## Key type decisions

- `RequestT` bound is `BaseModel` — payload is required on `BodyEndpoint`, absent on `NoBodyEndpoint`.
- `ResponseT` bound is `BaseModel | BinaryContent | Stream | None` — covers all four response kinds.
- `PathT` bound is `BasePath` — enforces TypedDict subclasses.
- Generic order is `[PathT, RequestT, ResponseT]` for body endpoints, `[PathT, ResponseT]` for no-body.
- Factory functions (`get`, `post`, `put`, `patch`, `delete`) instead of classmethods — `ty` can't infer class-level TypeVars from classmethods ([astral-sh/ty#541](https://github.com/astral-sh/ty/issues/541)). See [astral-sh/ty#541](https://github.com/astral-sh/ty/issues/541).
- Shared types in `types.py` to break circular import between `endpoint.py` and `client.py`.
- Streaming responses own the httpx stream context manager — `send()` passes it through, caller enters/exits via `with`/`async with`.
- Content-based request model: `PreparedRequest` carries `content: bytes | Iterable[bytes] | AsyncIterable[bytes] | None` and `content_type: str | None`. JSON endpoints serialize at `request()` time. Binary endpoints pass through. `send()` always sends `content` — no branching on body type.

## Overloaded `send()` dispatch

| `ResponseT` | `NemoClient.send()` returns | `AsyncNemoClient.send()` returns |
|---|---|---|
| `BaseModel` subclass | `NemoResponse[T]` | `NemoResponse[T]` |
| `None` | `NemoResponse[None]` | `NemoResponse[None]` |
| `BinaryContent` | `NemoBinaryResponse` | `AsyncNemoBinaryResponse` |
| `Stream[T]` | `NemoStreamResponse[T]` | `AsyncNemoStreamResponse[T]` |

Runtime dispatch: `_is_binary()` checks `response_type is BinaryContent`, `_is_stream()` uses `get_origin(response_type) is Stream` + `get_args()` for `ModelT`.

## Descriptor-based resource pattern

Endpoints have `__get__` overloaded on `NemoClient` vs `AsyncNemoClient`:
- Accessed on `NemoClient` → returns `SyncBound*Call` (sync `__call__`)
- Accessed on `AsyncNemoClient` → returns `AsyncBound*Call` (async `__call__`)

Usage:
```python
class _ExampleEndpoints:
    create = CreateItemEndpoint
    get_item = GetItemEndpoint

class ExampleClient(_ExampleEndpoints, NemoClient):
    pass

class AsyncExampleClient(_ExampleEndpoints, AsyncNemoClient):
    pass
```

## TODOs

### Near-term
- [ ] Consider whether `NemoPluginSDKResources` should be replaced entirely now that clients own their own httpx
- [ ] Handle pagination — list endpoints return `NemoListResponse[T]` with page/page_size/total; client should support iterating pages or auto-paginating

### Medium-term
- [ ] Add server-side helpers that derive FastAPI routes from the same endpoint definitions (shared contract)
- [ ] Migrate core service clients (Files, Entities, etc.) to use `NemoClient` instead of raw `platform._client`
- [ ] Eventually replace `NeMoPlatform` with `NemoClient` as the primary SDK entry point
- [ ] Make the client agnostic to the underlying HTTP library — abstract the transport so we can swap httpx for aiohttp, pyreqwest, etc. Punting for now — significant scope.

### Open questions
- How do we handle auth? Currently `default_headers` is the escape hatch — should there be first-class token/auth support?
