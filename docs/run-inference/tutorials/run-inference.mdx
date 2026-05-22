<!-- @nemo-nb: process -->
<!-- @nemo-nb: download -->
<a id="tutorial-run-inference"></a>
# Run Inference

Route inference requests through the gateway using model entity routing, provider routing, or OpenAI-compatible routing.

!!! note
    This tutorial assumes you have an external provider registered. The platform pre-configures a `system/nvidia-build` provider on startup, which most of the examples below use. To register your own provider, see [About Models and Inference](../about.md#model-providers).

--8<-- "_snippets/tutorials/cli-sdk-setup.md"

---

## Listing Models

There are two distinct ways to list models, depending on what you need:

| Command | What it returns |
|---|---|
| `nemo models list` | All **model entities** registered in the platform, regardless of whether they have an active deployment. |
| `nemo inference models list` | Only models **currently reachable via the Inference Gateway**, in OpenAI-compatible format. Model IDs use the format `workspace/model_entity_name`. |

Use `nemo models list` to manage model configurations. Use `nemo inference models list` to discover what's ready to serve requests right now.


=== "CLI"

    ```bash
    # All registered model entities (may include models without active deployments)
    nemo models list

    # Models available for inference via the gateway (OpenAI-compatible IDs)
    nemo inference models list
    ```

=== "Python SDK"

    ```python
    # All registered model entities
    for model in client.models.list():
        print(model.name)

    # Models available for inference via the gateway
    models = client.inference.models.list()
    for model in models.data:
        print(model.id)  # format: workspace/model_entity_name
    ```

---

## Route by Model Entity

Route requests using the model entity name. The gateway selects an available provider automatically.

Find available model entities:


=== "CLI"

    ```bash
    nemo models list
    ```

=== "Python SDK"

    ```python
    for model in client.models.list():
        print(model.name)
    ```

Run inference by passing the Model Entity.


=== "CLI"

    ```bash
    # Model entities are auto-discovered from deployments
    # Use the model entity name from 'nemo models list'
    nemo chat meta-llama-3-2-1b-instruct 'Hello!' --max-tokens 100
    ```

=== "Python SDK"

    ```python
    # Model entities are auto-discovered from deployments
    response = client.inference.gateway.model.post(
        "v1/chat/completions",
        name="meta-llama-3-2-1b-instruct",  # Model entity name
        body={
            "model": "meta/llama-3.2-1b-instruct",
            "messages": [{"role": "user", "content": "Hello!"}],
            "max_tokens": 100,
        },
    )
    ```

---

## Route by Provider

Route to a specific provider instance. Use for A/B testing or targeting specific deployments.

Find available providers:


=== "CLI"

    ```bash
    nemo inference providers list

    # List models available on a provider if its API is OpenAI compliant
    nemo inference gateway provider get v1/models --name llama-3-2-1b-deployment
    ```

=== "Python SDK"

    ```python
    for provider in client.inference.providers.list():
        print(f"{provider.name}: {provider.status}")

    # List models available on a provider if its API is OpenAI compliant
    models = client.inference.gateway.provider.get(
        "v1/models",
        name="llama-3-2-1b-deployment",
    )
    print(models)
    ```

Pass inference request using provider routing.


=== "CLI"

    ```bash
    # Provider name matches deployment name for auto-created providers
    nemo chat meta/llama-3.2-1b-instruct 'Hello!' \
    --provider llama-3-2-1b-deployment \
    --max-tokens 100
    ```

=== "Python SDK"

    ```python
    # Provider name matches deployment name for auto-created providers
    response = client.inference.gateway.provider.post(
        "v1/chat/completions",
        name="llama-3-2-1b-deployment",  # Provider name
        body={
            "model": "meta/llama-3.2-1b-instruct",
            "messages": [{"role": "user", "content": "Hello!"}],
            "max_tokens": 100,
        },
    )
    ```

---

## Route using OpenAI SDK

Use the OpenAI-compatible endpoint for drop-in SDK replacement. The model field uses the format `{workspace}/{model_entity}`.

!!! note "Model entity naming"
    The `{model_entity}` segment is validated against a strict regex
    (lowercase letters, digits, and hyphens; 2–63 characters; **no slashes**).
    Vendor-style IDs such as `meta/llama-3.3-70b-instruct` are rejected with
    HTTP 422 — register them as a hyphen-only entity (for example
    `meta-llama-3-3-70b-instruct`) and reference them as
    `{workspace}/meta-llama-3-3-70b-instruct` in the request body. Run
    `nemo inference models list` to see the IDs the gateway accepts.

### List Available Models

List models currently reachable via the Inference Gateway. Returns results in OpenAI-compatible format; each `id` is `workspace/model_entity_name`.


=== "CLI"

    ```bash
    nemo inference models list
    ```

=== "Python SDK"

    ```python
    models = client.inference.models.list()
    for model in models.data:
        print(model.id)  # format: workspace/model_entity_name
    ```

### Using SDK

Make requests to the OpenAI-compatible Inference Gateway route with the {{platform_name}} SDK.

```python
response = client.inference.gateway.openai.post(
    "v1/chat/completions",
    body={
        "model": "default/meta-llama-3-2-1b-instruct",  # workspace/model-entity
        "messages": [{"role": "user", "content": "Hello!"}],
        "max_tokens": 100,
    },
)
```

### Using OpenAI Python SDK

Models service provides a convenient helper method `client.models.get_openai_client()` that can generate an OpenAI SDK client for the configured workspace. The SDK also offers helper methods for generating OpenAI-compatible URL strings for Inference Gateway. Refer to [SDK Helper Methods](../about.md#sdk-helper-methods) for more info.

```python
# Get pre-configured OpenAI client
oai_client = client.models.get_openai_client()

response = oai_client.chat.completions.create(
    model="default/meta-llama-3-2-1b-instruct",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=100,
)
```

### Using Common OpenAI-Compatible Clients

If you construct third-party clients manually, pass the headers returned by `client.models.get_client_default_headers()` so auth and identity headers are preserved when authorization is enabled.


=== "OpenAI (manual client)"

    ```python
    from openai import OpenAI

    base_url = client.models.get_openai_route_base_url()
    headers = client.models.get_client_default_headers()

    oai_client = OpenAI(
        base_url=base_url,
        api_key="not-needed",
        default_headers=headers,
    )

    response = oai_client.chat.completions.create(
        model="default/meta-llama-3-2-1b-instruct",
        messages=[{"role": "user", "content": "Hello!"}],
    )
    ```

=== "LiteLLM"


    ```bash
    # make sure litellm is installed
    pip install litellm
    ```

    <!-- @nemo-nb: skip-type-check -->
    ```python
    from litellm import completion

    base_url = client.models.get_openai_route_base_url()
    headers = client.models.get_client_default_headers()

    response = completion(
        model="openai/meta-llama-3-2-1b-instruct",
        messages=[{"role": "user", "content": "Hello!"}],
        api_base=base_url,
        api_key="not-needed",
        extra_headers=headers,
    )
    ```

### Using curl

The OpenAI-compatible chat-completions endpoint is reachable directly over HTTP.
The canonical path is
`/apis/inference-gateway/v2/workspaces/{workspace}/openai/-/v1/chat/completions`
— resolve the base URL with the CLI rather than hand-assembling it:

```bash
BASE_URL=$(nemo inference get-url)

curl -s "$BASE_URL/chat/completions" \
  -H 'content-type: application/json' \
  -d '{
    "model": "default/meta-llama-3-2-1b-instruct",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }' | jq
```

If authorization is enabled on your platform, also forward the auth headers
the CLI is configured with (`nemo config view` shows the configured base URL
and token).

### Streaming

The OpenAI compatible Inference Gateway endpoint also supports streaming.

```python
oai_client = client.models.get_openai_client()

stream = oai_client.chat.completions.create(
    model="default/meta-llama-3-2-1b-instruct",
    messages=[{"role": "user", "content": "Write a haiku about coding."}],
    max_tokens=100,
    stream=True,
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```
