<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Eval Author

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

## Intended Invocation

Until a CLI or platform job is wired, Python callers can invoke the runner
directly:

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

No standalone Eval Author CLI is implemented yet.
