<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Eval Author Plugin

Owns the `nemo agents eval-author` command group, registered under `nemo.cli.agents` and
mounted by the agents plugin.

The Eval Author agent lives in the Experimentalist plugin, at
[`nemo_experimentalist_plugin.eval_author`](../nemo-experimentalist/src/nemo_experimentalist_plugin/eval_author/README.md).
Experimentalist insight mode is its only caller, so the agent sits next to the evaluator,
staging, and trace helpers it depends on.

## Direction of travel

The dependency is one arrow. Eval Author borrows the platform client factory from
Experimentalist, and Experimentalist imports nothing from here. Prefer duplicating a helper
over adding a second arrow.

| Arrow | Status | Why |
| --- | --- | --- |
| Eval Author → Experimentalist | one import | `discovery/run.py` builds a platform client with `make_client` |
| Experimentalist → Eval Author | none | the agent moved into the Experimentalist plugin |

[`tests/test_plugin_boundary.py`](tests/test_plugin_boundary.py) pins the remaining import so
it can only shrink.

Install the plugin with:

```bash
uv sync --group experimentalist
```

## Discover

`nemo agents eval-author discover` validates one repository-owned Harbor config and writes no repository files.

The command accepts these flags:

- `--repo` selects the repository. The current directory is the default.
- `--agent` sets the name. Without it, a string `agent` in root `optimizer.yaml` takes precedence over the repository directory slug.
- `--dry-run` prints the report and uploads no files.

Discovery does not infer or generate a config. The preflight includes:

- Harbor validates the schema, agent concurrency limits, task directories, and dataset coverage. Harbor also resolves the job.
- Discovery identifies required environment variables. Harbor imports the agent and validates the environment backend.
- `harbor job start --print-config` loads the config file.

The `ETHOS.md` and trace checks are advisory.
Each invocation repeats the preflight and records one `sha256:<digest>` fingerprint plus the input file count. The fingerprint never skips validation.

Without `--dry-run`, the command uploads only `<agent>/discovery.md` to the `nemo-eval-author` fileset.
Only a runnable report includes `cd <repo-root> && harbor job start -c <repo-relative-path>`.

A standard run returns exit code 0 only for a runnable report and a successful upload.
A dry run returns exit code 0 only if the report is runnable.
All other outcomes return exit code 1. The command still uploads a report for an absent or rejected config.

> **WARNING:** Use `discover` only with a trusted repository.
> An agent import executes module top-level code.

## Planned commands

- `nemo agents eval-author audit` will report coverage gaps against `ETHOS.md` and will not change the current Harbor suite.
- `nemo agents eval-author propose` will draft Harbor tasks and verifier patches for review.
- `nemo agents eval-author run` will run `discover`, `audit`, and `propose` as one pipeline.
- `nemo agents eval-author doctor` will check credentials, platform access, and the runtime for the other commands.
