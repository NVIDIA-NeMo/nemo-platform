# NemoClient — Design Notes & TODOs

Tracking file for the typed HTTP client work in `nemo_platform_plugin/client/`.

## What we built

A typed endpoint/client system where:
- **`Endpoint[PathT, RequestT, ResponseT]`** — frozen dataclass linking a URL template to typed path params, request body, and response body. Classmethods `get`, `post`, `patch`, `delete` for construction.
- **`PreparedRequest[ResponseT]`** — frozen dataclass produced by calling `.request()` on an endpoint with a payload + path params. Carries the resolved path, method, body, and response type.
- **`NemoResponse[ResponseT]`** — frozen dataclass wrapping the full `httpx.Response` and a parsed Pydantic body. `.data()` for the common "give me the body or raise" case.
- **`BaseNemoClient`** — shared logic: URL construction, workspace default injection, JSON serialization, response parsing.
- **`NemoClient` / `AsyncNemoClient`** — sync/async subclasses that own an httpx client and implement `send()`.
- **Path params are typed via `TypedDict` + `Unpack`** — the type checker enforces correct kwargs at the call site.
- **Workspace** can be set on the client and auto-injected into `{workspace}` in paths. Explicit per-call values override.
- **Endpoint naming convention** — PascalCase (e.g. `CreateItemEndpoint`), not UPPER_SNAKE. They're callable objects, not constants.

## File layout

```
packages/nemo_platform_plugin/src/nemo_platform_plugin/client/
├── endpoint.py     # Endpoint, PreparedRequest
├── client.py       # BaseNemoClient, NemoClient, AsyncNemoClient
└── response.py     # NemoResponse, NemoHTTPError

plugins/example-plugin/src/nemo_example_plugin/
├── types/
│   ├── payloads.py   # Plain Pydantic request/response models
│   └── endpoints.py  # Endpoint definitions + path TypedDicts
├── schema.py         # Server-side filters only
└── sdk.py            # ExampleClient(NemoClient), AsyncExampleClient(AsyncNemoClient)
```

## Key type decisions

- `RequestT` bound is `BaseModel | None` — allows `None` for body-less endpoints (GET, DELETE) without type ignores.
- `ResponseT` is currently `bound=BaseModel | None` — will need to be widened to support streaming (see below).
- `PathT` is unbound — it's a TypedDict, not a BaseModel.
- Generic order is `Endpoint[PathT, RequestT, ResponseT]` — path first since it's always present.
- Classmethods use `Endpoint(...)` not `cls(...)` — `ty` infers `cls(...)` as `Self` which doesn't match the concrete return type.
- `path_type` is always required on classmethods — no `EmptyPath` default.

## Streaming design (spike results)

### The three response kinds

1. **JSON** — parse into a Pydantic model. What we have today. (`ResponseT` is a `BaseModel`)
2. **Binary stream** — raw bytes, iterate chunks. File downloads. (`ResponseT` is `BinaryStream`)
3. **SSE/NDJSON stream** — a stream of typed JSON objects. Chat completions, function streaming. (`ResponseT` is `Stream[SomeModel]`)

### Planned approach

Declare response kind in the endpoint's `ResponseT`, then overload `send()` to return the right type:

```python
class BinaryStream: ...              # Marker: raw bytes
class Stream(Generic[ModelT]): ...   # Marker: stream of parsed models

# Endpoints declare their response kind:
GetItemEndpoint = Endpoint.get(..., response_type=ExampleItem)          # JSON
DownloadEndpoint = Endpoint.get(..., response_type=BinaryStream)        # Binary
ChatEndpoint = Endpoint.post(..., response_type=Stream[ChatChunk])      # SSE/NDJSON

# Client overloads on ResponseT:
@overload
def send(self, request: PreparedRequest[BinaryStream]) -> NemoBinaryResponse: ...
@overload
def send(self, request: PreparedRequest[Stream[ModelT]]) -> NemoStreamResponse[ModelT]: ...
@overload
def send(self, request: PreparedRequest[None]) -> NemoResponse[None]: ...
@overload
def send(self, request: PreparedRequest[ModelT]) -> NemoResponse[ModelT]: ...
```

### What we validated

- **Overload resolution works in `ty`** when `PreparedRequest` is constructed with an explicit type parameter:
  - `PreparedRequest[UserResponse]` → `NemoResponse[UserResponse]` ✓
  - `PreparedRequest[BinaryStream]` → `NemoBinaryResponse` ✓
  - `PreparedRequest[None]` → `NemoResponse[None]` ✓

### Known `ty` limitation

- When the generic flows through chained calls (`Endpoint.get(...)` → `.request()` → `PreparedRequest[ResponseT]`), `ty` resolves to `Unknown` instead of propagating the concrete type. This is a `ty` inference gap with multi-hop generic propagation, not a problem with our design. The overloads themselves are correct.
- The Delete/None case works because `None` is a literal type, not a generic resolution.
- This may improve in future `ty` versions. For now, explicit type annotations on endpoint variables can help if needed.

### Upload considerations

Upload is the inverse — the *request* body is binary, not the response. Options:
- A `BinaryUpload` marker for `RequestT`
- A separate `content: bytes | BinaryIO` field on `PreparedRequest` alongside `body: BaseModel | None`
- A dedicated `upload()` method on the client

Stainless handles this by passing `content=` instead of `json=` and setting `Content-Type: application/octet-stream`. The response is still a normal JSON model (`FilesetFile`).

### `ResponseT` bound change needed

To support streaming, `ResponseT` must be widened from `bound=BaseModel | None` to unbound (or `bound=object`), since `BinaryStream` and `Stream[T]` aren't BaseModel subclasses. The classmethods on `Endpoint` will constrain what's valid for each HTTP method.

## TODOs

### Near-term
- [ ] Wire `ExampleClient` into the plugin SDK registration system (`NemoPluginSDKResources` currently expects a `NeMoPlatform`-taking constructor — needs updating or replacing)
- [ ] Add server-side helpers that derive FastAPI routes from the same `Endpoint` definitions (shared contract)
- [ ] Validate that `ty` enforces path param kwargs correctly at call sites (e.g. missing `workspace` is an error)
- [ ] Consider whether `NemoPluginSDKResources` should be replaced entirely now that clients own their own httpx

### Streaming & binary
- [ ] Implement `BinaryStream` and `Stream[ModelT]` marker types
- [ ] Implement `NemoBinaryResponse` and `NemoStreamResponse[ModelT]` response types
- [ ] Add overloaded `send()` that dispatches based on `ResponseT`
- [ ] Widen `ResponseT` bound to support the marker types
- [ ] Add `Endpoint.get_binary()` / `Endpoint.put_binary()` classmethods (or just use the existing ones with `BinaryStream` as response_type)
- [ ] Handle upload (binary request body) — decide on approach
- [ ] Handle pagination — list endpoints return `NemoListResponse[T]` with page/page_size/total; client should support iterating pages or auto-paginating

### Medium-term
- [ ] Migrate core service clients (Files, Entities, etc.) to use `NemoClient` instead of raw `platform._client`
- [ ] Eventually replace `NeMoPlatform` with `NemoClient` as the primary SDK entry point

### Open questions
- How do we handle auth? Currently `default_headers` is the escape hatch — should there be first-class token/auth support?
- Will `ty` improve chained generic inference? If not, do we need explicit type annotations on all endpoint definitions?
