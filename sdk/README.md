<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Platform SDK

## Stainless-Free Python SDK Maintenance

Stainless generation for the Python SDK is disabled. The legacy SDK under
`sdk/python/nemo-platform` can still be maintained manually when compatibility
requires it, but contributors should prefer source-owned typed clients for new
or changed service behavior. No automated lint can prove semantic compatibility
between current OpenAPI and the legacy Stainless-generated SDK.

`make update-sdk` regenerates derived OpenAPI, web SDK, and CLI artifacts
without running Stainless. If an API change affects legacy Python SDK behavior,
manually review compatibility and update source-owned typed clients or
compatibility adapters as needed.

Do not run Stainless to regenerate the Python SDK.

Run the maintained update flow whenever you modify API endpoints, request or
response schemas, data models, `packages/nmp_common/src/nmp_common/api/`,
`packages/nmp_common/src/nmp_common/datamodel/`, or service API files under
`services/*/src/*/api/`. OpenAPI generation also runs as a manual-stage
pre-commit hook when API files change.

## Folder Structure

- `sdk/stainless.yaml`: legacy Stainless config still used as CLI-generation
  metadata by `make generate-cli-commands`.
- `sdk/python/nemo-platform/src/nemo_platform/resources/`: legacy generated
  resource clients.
- `sdk/python/nemo-platform/src/nemo_platform/types/`: legacy generated request
  and response types.
- `sdk/python/nemo-platform/src/nemo_platform/{cli,client,config,...}`:
  vendored or source-owned extension code that is still maintained through
  `make vendor`.

## Maintained Commands

Use these commands for non-Stainless generated or vendored artifacts:

```bash
make refresh-openapi
make update-web-sdk
make update-cli
make vendor
make update-sdk
make audit-stainless
```

Use `make audit-stainless` when planning or reviewing Stainless removal work.
By default, it reports Python imports from the legacy `nemo_platform` SDK
grouped by owner, including `service:<name>`, `plugin:<name>`,
`package:<name>`, and `e2e:<area>`. Use `ARGS='--show-lines'` to include exact
file and line details. Use `ARGS='--show-adjacent --show-references'` to
include symbols, adapters, package dependencies, and Stainless metadata
references. Pass `ARGS='--limit <n>'` only when you want to trim the printed
report.

The following commands are intentionally disabled:

```bash
make stainless
./sdk/stainless.sh sync
uv run --frozen nemo-platform-sdk-tools openapi-stainless --help
```
