<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# SDK Maintenance Tools

## Prerequisites

Run these commands from the repository root in a Git worktree with the project
toolchain available. The commands expect `uv`, `git`, and `make` to be on
`PATH` and use the checked-in `uv.lock`.

This package contains repo-local commands for keeping generated CLI, vendored
packages, and license metadata in sync without Stainless. No command in this
package proves semantic compatibility between current OpenAPI and the legacy
Stainless-generated Python SDK.

## Generated CLI

Regenerate the API-backed NeMo Platform CLI commands:

```sh
uv run --frozen nemo-platform-sdk-tools generate-cli
```

The generator still reads `sdk/stainless.yaml` as resource/method metadata for
the legacy SDK shape.

## SDK Vendoring

Vendor configured platform packages into the Python SDK wrapper:

```sh
uv run --no-sync nemo-platform-sdk-tools vendor all-from-configs \
  nemo_platform_ext models filesets nemo_evaluator_sdk
```

Run post-generation updates:

```sh
uv run --no-sync nemo-platform-sdk-tools post-generation update-license-headers
uv run --frozen nemo-platform-sdk-tools post-generation update-pyproject
```

Prefer the Makefile targets (`make generate-cli-commands`, `make vendor`, and
`make update-sdk`) for normal repo workflows. `make update-sdk` does not
regenerate the Python SDK with Stainless.

## Next Steps

For the Stainless-free SDK maintenance policy, see
[`sdk/README.md`](../../../../../sdk/README.md). For migrating client behavior
to source-owned typed clients, see
[`nemo_platform_plugin/client/MIGRATION.md`](../../../../../packages/nemo_platform_plugin/src/nemo_platform_plugin/client/MIGRATION.md).
