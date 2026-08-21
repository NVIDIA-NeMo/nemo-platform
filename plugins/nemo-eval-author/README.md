<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Eval Author Plugin

Owns the `nemo agents eval-author` command group, registered under `nemo.cli.agents` and
mounted by the agents plugin. `discover` is implemented; `audit`, `propose`, `run`, and
`doctor` are placeholders.

Use `discover` only with a trusted repository, because importing an agent runs
module top-level code.

The Eval Author agent moved into the Experimentalist plugin, at
[`nemo_experimentalist_plugin.eval_author`](../nemo-experimentalist/src/nemo_experimentalist_plugin/eval_author/README.md).
Experimentalist insight mode is its only caller, so the agent sits beside the evaluator,
staging, and trace helpers it depends on.

## Direction of travel

The dependency is one arrow. `discovery/run.py` borrows `make_client` from Experimentalist,
and Experimentalist imports nothing from here, so there is no package cycle for `uv` to
resolve. Install both plugins with:

```bash
uv sync --group experimentalist
```
