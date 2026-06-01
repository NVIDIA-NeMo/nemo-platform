# SDK Code — Do Not Edit Directly

Code in `sdk/python/nemo-platform/` is **generated and vendored**. Do not edit it directly — your changes will be overwritten.

## How the SDK Is Built

The SDK is assembled from two sources:

1. **Stainless** — Generates low-level SDK code (API clients, types, resources) from the OpenAPI spec.
2. **Vendored client-side extensions** — Code from `packages/` is copied into the SDK with import rewriting (`nemo_platform_ext.X` → `nemo_platform.X`, etc.).

Only 6 client-side extension packages are file-vendored into the SDK. Runtime/server packages (services, `nmp_common`, `nemo_platform_plugin`, etc.) are **not** vendored into the SDK — they are bundled into the `nemo-platform` wrapper wheel via force-include from source.

## Vendored Client-Side Extensions

| Package | Source Location |
|---|---|
| `nemo_platform_ext` | `packages/nemo_platform_ext/` |
| `data_designer_sdk` | `packages/data_designer_sdk/` |
| `models` | `packages/models/` |
| `filesets` | `packages/filesets/` |
| `nemo_evaluator_sdk` | `packages/nemo_evaluator_sdk/` |

## Build Commands

| Command | What It Does |
|---|---|
| `make update-sdk` | Full SDK update (regenerate OpenAPI spec + Stainless + vendor) |
| `make vendor` | Vendor client extensions into SDK + generate wrapper metadata |
| `make vendor-nemo-platform-ext` | Vendor just the `nemo_platform_ext` package |
| `make refresh-openapi` | Regenerate `openapi/openapi.yaml` from API definitions |
| `make stainless` | Push spec to Stainless and pull generated code |

## Workflow

To change SDK behavior that comes from vendored packages:

1. Edit the source in `packages/<package_name>/`
2. Run `make vendor` (or the specific vendor command)
3. Verify the vendored output in `sdk/python/nemo-platform/`

For CLI development specifically, you can run `_nmp` directly from source to test changes without vendoring first:

```bash
uv run _nmp --help
```

`_nmp` uses `packages/nemo_platform_ext` directly, so use vendoring when you need to validate the SDK-vendored copy.

See `sdk/stainless.sh` for the Stainless generation flow.
