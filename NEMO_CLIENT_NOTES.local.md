# NemoClient — Design Notes & TODOs

Tracking file for the typed HTTP client work in `nemo_platform_plugin/client/`.

## What we built

A typed endpoint/client system where:
- **`Endpoint[PathT, RequestT, ResponseT]`** — one unified endpoint class that is also a descriptor. Self-type overloads on `request()` handle body/binary/no-body variants. `__get__` dispatches `SyncBoundCall` or `AsyncBoundCall` based on the client type.
- **`SyncBoundCall[PathT, RequestT, ResponseT]`** / **`AsyncBoundCall[PathT, RequestT, ResponseT]`** — bound callables with 9 self-type overloads (3 request × 3 response variants) that cover all calling conventions.
- **`PreparedRequest[ResponseT]`** — frozen dataclass carrying path template, path params, content, content type, and response type. Path interpolation is deferred to `send()`.
- **`NemoResponse[ResponseT]`** — frozen dataclass wrapping `httpx.Response` and parsed body. `.data()` for unwrap-or-raise.
- **`NemoBinaryResponse`** / **`AsyncNemoBinaryResponse`** — streaming binary responses. Context managers with `read()` and `__iter__`/`__aiter__`.
- **`NemoStreamResponse[ModelT]`** / **`AsyncNemoStreamResponse[ModelT]`** — streaming NDJSON responses. Context managers with model-parsing iteration.
- **`BinaryContent`** — marker type for binary request/response (unified, used in both positions).
- **`Stream[ModelT]`** — marker type for NDJSON streaming responses.
- **`PathParams(TypedDict)`** — base for all path TypedDicts. `PathT` is `bound=PathParams`.
- **`BaseNemoClient`** — shared logic: path resolution (merging client defaults + explicit params + `format_map` with `ValueError` on missing params), stream/binary detection.
- **`NemoClient` / `AsyncNemoClient`** — sync/async subclasses with overloaded `send()` that dispatches return type based on `ResponseT`.
- **Descriptor pattern** — `Endpoint.__get__` is overloaded on `NemoClient` vs `AsyncNemoClient`. Returns `SyncBoundCall` or `AsyncBoundCall`. The bound call stores `endpoint.request` as a `Callable[..., PreparedRequest[ResponseT]]`, avoiding any coupling to the endpoint type.
- **Endpoint mixin pattern** — define endpoints once in a mixin class, then sync/async client classes inherit the mixin + client base.
- **Adapter** — `client_from_platform()` bridges `NeMoPlatform` to `NemoClient` for backward compatibility with `NemoPluginSDKResources`.
- **Path params typed via `TypedDict` + `Unpack`** with `NotRequired[str]` for workspace (client default fills it in).

## File layout

```
packages/nemo_platform_plugin/src/nemo_platform_plugin/client/
├── types.py        # PathParams, BinaryContent, Stream, PreparedRequest, TypeVars
├── endpoint.py     # Endpoint class, factory functions (get/post/put/patch/delete)
├── bound.py        # SyncBoundCall, AsyncBoundCall
├── client.py       # BaseNemoClient, NemoClient, AsyncNemoClient
├── response.py     # NemoResponse, NemoBinaryResponse, AsyncNemoBinaryResponse, NemoStreamResponse, AsyncNemoStreamResponse, NemoHTTPError
└── adapter.py      # client_from_platform()

plugins/example-plugin/src/nemo_example_plugin/
├── types/
│   ├── payloads.py   # Plain Pydantic request/response models
│   └── endpoints.py  # Endpoint definitions + path TypedDicts
├── schema.py         # Server-side filters only
└── sdk.py            # _ExampleEndpoints mixin, ExampleClient, AsyncExampleClient, NemoPluginSDKResources registration
```

## Key type decisions

- `RequestT` is unbound — encodes `BaseModel` (JSON body), `BinaryContent` (binary upload), or `None` (no body). The self-type overloads on `request()` and `__call__` dispatch based on the concrete type.
- `ResponseT` bound is `BaseModel | BinaryContent | Stream | None` — covers all four response kinds.
- `PathT` bound is `PathParams` — enforces TypedDict subclasses.
- Generic order is `[PathT, RequestT, ResponseT]`.
- Factory functions (`get`, `post`, `put`, `patch`, `delete`) instead of classmethods — `ty` can't infer class-level TypeVars from classmethods ([astral-sh/ty#541](https://github.com/astral-sh/ty/issues/541)).
- Shared types in `types.py` to break circular imports.
- Bound calls store `endpoint.request` as `Callable[..., PreparedRequest[ResponseT]]` — no coupling to the endpoint class, no `ty` errors in the implementation body.
- Streaming responses own the httpx stream context manager — `send()` passes it through, caller enters/exits via `with`/`async with`.
- Content-based request model: `PreparedRequest` carries `content` and `content_type`. JSON endpoints serialize at `request()` time. Binary endpoints pass through. `send()` always sends `content`.

## Overloaded `send()` dispatch

| `ResponseT` | `NemoClient.send()` returns | `AsyncNemoClient.send()` returns |
|---|---|---|
| `BaseModel` subclass | `NemoResponse[T]` | `NemoResponse[T]` |
| `None` | `NemoResponse[None]` | `NemoResponse[None]` |
| `BinaryContent` | `NemoBinaryResponse` | `AsyncNemoBinaryResponse` |
| `Stream[T]` | `NemoStreamResponse[T]` | `AsyncNemoStreamResponse[T]` |

## Descriptor-based resource pattern

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
