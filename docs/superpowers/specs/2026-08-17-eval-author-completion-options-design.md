# Eval Author completion options

Date: 2026-08-17  
Status: implemented on branch `eval-author-completion-options/akhoury`

## Problem

Eval Author (and other Nooa-backed agents) build `CompletionClient`s through
`nemo_platform_plugin.nooa_model_client` with no way to set `reasoning_effort` or
other LiteLLM/CompletionClient kwargs. On `main`, the field is omitted and the
provider default applies. Smoke Mode 1 evidence shows Author quality is sensitive
to effort; we want Author to default to `medium` without hardcoding it inside
`_completion_client` for every consumer.

## Goals

- Let Eval Author specify OpenAI-style `reasoning_effort` (default **`medium`**).
- Let callers pass arbitrary `completion_params` for non-OpenAI backends (or extra
  OpenAI knobs) without a second one-off API.
- Keep Analyst and Experimentalist behavior unchanged until they opt in.
- `None` / empty params must match today’s omit-the-field behavior for consumers
  that do not set options.

## Non-goals (v1)

- Per-component Experimentalist override map.
- Analyst wiring.
- CLI flags (follow-up).
- Provider-specific translation (e.g. Anthropic `thinking` helpers). Unsupported
  keys continue to rely on existing `drop_params=True`.

## Design

### Shared: `CompletionClientOptions`

In `packages/nemo_platform_plugin/.../nooa_model_client.py`:

```python
@dataclass(frozen=True)
class CompletionClientOptions:
    reasoning_effort: str | None = None
    completion_params: Mapping[str, Any] = field(default_factory=dict)
```

`resolve_model_clients(client, refs=None, options: CompletionClientOptions | None = None)`
threads options into `_completion_client`.

Merge order when constructing `CompletionClient`:

1. Existing base kwargs (`api_base`, `drop_params`, `_skip_responses_api_bridge`, …).
2. Spread `completion_params`.
3. If `reasoning_effort is not None`, set `reasoning_effort=...` **last** so the
   explicit field wins over the same key inside `completion_params`.

If `options` is `None` or both fields are unset, wire behavior matches `main`
today (no `reasoning_effort` kwarg).

Apply the same merge for OpenAI- and Anthropic-shaped clients. No format-specific
branching in v1.

### Eval Author

`EvalAuthorConfig` gains:

```python
reasoning_effort: str | None = "medium"
completion_params: dict[str, Any] = Field(default_factory=dict)
```

`run_eval_author` builds `CompletionClientOptions` from config and passes it to
`resolve_model_clients`. Mode 1 inherits this when Experimentalist invokes Author:
the runner nested-resolves Author-scoped clients from `config.eval_author` (default
`medium`) so Experimentalist's outer default/fast pair stays unchanged.

Setting `reasoning_effort=None` in config restores provider-default omit for a
given run.

### Defaults summary

| Consumer | v1 default |
| --- | --- |
| `resolve_model_clients` (no options) | omit effort (unchanged) |
| Eval Author config | `reasoning_effort="medium"` |
| Analyst / Experimentalist agents | unchanged (no options passed) |

## Tests

- Unit (`test_nooa_model_client`): merge order; `None` omits effort; params
  forwarded; explicit effort overrides duplicate key in params.
- Eval Author: default config resolves with `reasoning_effort="medium"`; explicit
  `None` omits; `completion_params` reach `resolve_model_clients` (mock).

## Follow-ups

- Optional Experimentalist YAML under `eval_author:` for these fields.
- CLI flags for standalone Author runs.
- Run-level + per-role map (design C) for Experimentalist components.
- Anthropic-oriented helpers if silent `drop_params` proves insufficient.
