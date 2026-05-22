<a id="auditor-targets-schema"></a>
# Target Schema

This page lists every field on `AuditTarget`. Defaults match the pydantic definition in `nemo_auditor.entities`; the {{platform_name}} entity store validates writes against this schema.

## `AuditTarget`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Unique target name within the workspace. |
| `workspace` | `str` | Yes | Workspace the target is persisted in. |
| `type` | `str` | Yes | A fully-qualified [garak generator class](https://reference.garak.ai/en/latest/generators.html), such as `nim.NVOpenAIChat`, `openai.OpenAIGenerator`, `rest.RestGenerator`, or `test.Blank`. |
| `model` | `str` | Yes | Provider model identifier (for example, `meta/llama-3.1-8b-instruct`). Some generator types (`test.Blank`) ignore this field but the schema still requires it. |
| `options` | `dict[str, Any]` | No | Nested generator-specific options. The top-level key matches the generator namespace (`nim`, `openai`, `rest`, ...). Defaults to `{}`. |
| `description` | `str \| None` | No | Free-form description shown in listings. Defaults to `None`. |

The entity store adds the standard `NemoEntity` fields on retrieval: `id`, `entity_type` (`"auditor_audit_target"`), `created_at`, `updated_at`, and `project`.

## About `options`

`options` is intentionally opaque to the plugin — its contents are passed through to garak as the generator's `--generator_option_file` payload. Refer to garak's [generator documentation](https://reference.garak.ai/en/latest/generators.html) for the options each generator class accepts.

The plugin recognizes one sentinel inside `options.<generator>`: an `nmp_uri_spec` block is resolved at run time to a concrete `uri` value via the {{platform_name}} Inference Gateway. See [Inference Gateway](inference-gateway.md) for the resolution rules and conflict semantics.
