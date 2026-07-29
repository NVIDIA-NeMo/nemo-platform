---
name: nooa
description: Build, modify, debug, or optimize agents using NVIDIA-labs OO Agents (NOOA). Use for nooa.Agent subclasses, ellipsis generation methods, CodeAct or Predict strategies, ShellTools, Skill/TextSkill, context and persistence, MCP, tracing, middleware, channels, or trace analysis.
compatibility: Python >= 3.12,<3.14; uv; nooa v0.0.6
metadata:
  upstream: https://github.com/NVIDIA-NeMo/labs-OO-Agents
  revision: v0.0.6
---
<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NVIDIA-labs OO Agents (NOOA)

Use the `nooa` package and namespace pinned in this repository.

For detailed framework guidance, consult the immutable upstream `v0.0.6`
skills:
https://github.com/NVIDIA-NeMo/labs-OO-Agents/tree/v0.0.6/skills

Before changing framework behavior, inspect the pinned implementation or the
matching upstream skill instead of guessing. In Optimizer:

- Call `super().__init__()` before attaching tools or skills.
- Use `GuardedShellTools` where workspace access must remain restricted.
- Hide internal skill registries with `spec(self, "skills", hidden=True)`.
- Keep the explicit `orjson==3.11.9` workaround required by the v0.0.6
  LiteLLM tool-call path.

## Verification

Use the repository root `.venv` and the README's standard `uv` workflow. Run:

```bash
uv run --frozen pytest -q <focused migration tests>
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright
```

Then run the changed agent end to end with its configured model.
