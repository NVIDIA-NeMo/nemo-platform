<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# SDK Code — Legacy Generated Code And Vendored Extensions

Stainless generation for `sdk/python/nemo-platform/` is disabled. The legacy
generated resources and types may be maintained manually when compatibility
requires it, but prefer source-owned typed clients for new behavior. No
automated lint can prove semantic compatibility between current OpenAPI and the
legacy Stainless-generated SDK.

Vendored extension code in this package is still maintained from source
packages through the vendoring workflow below.

## How the SDK Is Built

The SDK package is assembled from two historical sources:

1. **Legacy Stainless output** — Low-level SDK code (API clients, types, resources) generated from the OpenAPI spec before Stainless generation was disabled.
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
| `make update-sdk` | Update derived OpenAPI, web SDK, and CLI artifacts without Stainless Python SDK generation |
| `make vendor` | Vendor client extensions into SDK + generate wrapper metadata |
| `make vendor-nemo-platform-ext` | Vendor just the `nemo_platform_ext` package |
| `make refresh-openapi` | Regenerate `openapi/openapi.yaml` from API definitions |
| `make stainless` | Disabled; Python SDK generation no longer uses Stainless |

## Workflow

When API definitions change, update the source API first, then run
`make refresh-openapi`. Manually review any affected legacy SDK behavior and
prefer source-owned typed clients or compatibility adapters for new behavior.

Do not run Stainless to regenerate the Python SDK.

To change SDK behavior that comes from vendored packages:

1. Edit the source in `packages/<package_name>/`
2. Run `make vendor` (or the specific vendor command)
3. Verify the vendored output in `sdk/python/nemo-platform/`

For CLI development specifically, you can run `_nmp` directly from source to test changes without vendoring first:

```bash
uv run _nmp --help
```

`_nmp` uses `packages/nemo_platform_ext` directly, so use vendoring when you need to validate the SDK-vendored copy.

Do not run Stainless for Python SDK generation.
