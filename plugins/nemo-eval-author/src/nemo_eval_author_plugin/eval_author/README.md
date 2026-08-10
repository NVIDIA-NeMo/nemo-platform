<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Eval Author

> **Eval Author is in active development and is not intended for external use.**
>
> **WARNING:** Use Eval Author only with a trusted repository.
> An agent import executes module top-level code.

The top-level `nemo_eval_author_plugin.eval_author` package is the canonical Eval Author
implementation. It turns an Experimentalist Insight and its production trace refs into
evaluator dataset changes, creating or augmenting regression signals that
capture the failure mode before optimization begins.

This package hard-depends on Experimentalist for evaluator, staging, and trace
helpers. Experimentalist insight mode imports and runs this Eval Author before
beginning optimization (both packages are installed via the `experimentalist`
uv group).

## Current Files

- `agent.py` defines the canonical `EvalAuthor` agent.
- `materialization.py` stages, validates, and persists Insight suites locally.
- `models.py` defines the lightweight `EvalAuthorConfig` and `EvalAuthorResult` models.
- `REFERENCE.md` documents the Python return contract.
- `run.py` defines `run_eval_author(...)`, a reusable orchestration function for
  Python callers.
- `config.yaml` is a default run preset for future CLI or job wiring.

## Configuration

`config.yaml` is not loaded automatically yet. A future entrypoint should read
the file, overlay caller-provided values, and validate the nested `eval_author`
block with `EvalAuthorConfig`.

The preset includes the run inputs needed by `run_eval_author(...)`:

- `insight`: local Insight file path or platform Insight id.
- `agent`: optional agent source override. If omitted, the Insight's agent is used.
- `train_dataset`: evaluator training dataset URI.
- `validation_dataset`: evaluator validation dataset URI.
- `task_template`: local or `fileset://` evaluator task template URI for production traces.
- `experiment_dir`: local Eval Author working directory.
- `workspace`, `base_url`, `mode`, and `evaluator_type`: platform and evaluator routing.
- `eval_author.max_summary_tokens` and `eval_author.max_traces`: agent tuning parameters.

## Materialized Insight Suite

For an Insight with trace references, Eval Author copies and fills one local Harbor
task template per trace beneath its experiment working directory:

```text
eval-and-optimize/eval_author/<insight-slug>/insight-suite/
```

Each Eval Author invocation fills a fresh candidate suite from the current template
and traces. The complete suite is Harbor-validated locally, promoted to the
experiment-local working copy with backup-and-restore failure handling, and
analyzed for the Insight's root cause. Eval Author then adds normalized
Insight-specific verifier metric keys to every task in the staged train,
validation, and generated Insight datasets while preserving existing task
metrics. All three datasets must pass static Harbor validation before they are
returned.

After authoring and validation, Eval Author hashes every task file and verifier
file and persists deterministic suite and scorer identities in the local suite's
manifest. The returned Insight dataset points at the experiment-local suite.
Eval Author does not split, merge, or evaluate that suite. Experimentalist
currently leaves it unconsumed for downstream integration by its owning team.

Task-template inputs may be local paths, `file://` URIs, or NeMo Platform
`fileset://<workspace>/<fileset>` references. Fileset-backed templates are
downloaded into the experiment-local staging directory before Harbor parses
them. The staged template is refreshed on every invocation rather than reused.

The returned Python contract is documented in the
[Eval Author Python Reference](REFERENCE.md#evalauthorresult).

## Intended Python Invocation

`run_eval_author(...)` remains available to Python callers:

```python
import asyncio
from pathlib import Path

from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig
from nemo_eval_author_plugin.eval_author.run import run_eval_author
from nemo_experimentalist_plugin.entities import DatasetRef


async def main() -> None:
    result = await run_eval_author(
        insight="insight-id",
        train_dataset=DatasetRef(uri="path/to/train"),
        validation_dataset=DatasetRef(uri="path/to/validation"),
        task_template=DatasetRef(uri="path/to/template"),
        experiment_dir=Path("tmp/eval_author"),
        workspace="default",
        base_url="http://localhost:8080",
        config=EvalAuthorConfig(),
    )
    print(result.summary)


asyncio.run(main())
```

## Discovery CLI

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

## Planned Commands

- `nemo agents eval-author audit` will report coverage gaps against `ETHOS.md` and will not change the current Harbor suite.
- `nemo agents eval-author propose` will draft Harbor tasks and verifier patches for review.
- `nemo agents eval-author run` will run `discover`, `audit`, and `propose` as one pipeline.
- `nemo agents eval-author doctor` will check credentials, platform access, and the runtime for the other commands.
