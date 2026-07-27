<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Eval Author

The top-level `nemo_experimentalist_plugin.eval_author` package is the canonical Eval Author
implementation. It turns an Experimentalist Insight and its production trace refs into
evaluator dataset changes, creating or augmenting regression signals that
capture the failure mode before optimization begins.

Experimentalist is a consumer of this package: its insight mode imports and
runs the top-level Eval Author before beginning optimization.

## Current Files

- `agent.py` defines the canonical `EvalAuthor` agent.
- `materialization.py` stages, validates, and persists Insight suites locally.
- `models.py` defines the lightweight `EvalAuthorConfig` and `EvalAuthorResult` models.
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
Insight-specific verifier metric keys to every materialized task while
preserving the template's existing task metrics. The metric authoring step is
scoped to the Insight suite; the user's train and validation datasets remain
unchanged. The authored verifiers must pass static Harbor validation before the
local suite is returned to the optimization loop.

After authoring and validation, Eval Author hashes every task file and verifier
file, derives deterministic suite and scorer identities, and freezes the exact
content beneath:

```text
eval-and-optimize/eval_author/<insight-slug>/artifacts/<sha256>/insight-suite/
```

The returned dataset points at this immutable artifact and carries a portable
`nemo-experimentalist-insight-suite://.../sha256/...` reference. Candidate Insight
results persist the same suite identity and artifact reference. Resume reuses
those results only when the identity still matches; changed task or verifier
content is re-evaluated.

Task-template inputs may be local paths, `file://` URIs, or NeMo Platform
`fileset://<workspace>/<fileset>` references. Fileset-backed templates are
downloaded into the experiment-local staging directory before Harbor parses
them. The staged template is refreshed on every invocation rather than reused.

`EvalAuthorResult.insight_suite` contains the finalized content-addressed
`Dataset` for immediate evaluation by the optimization loop. Its identity and
portable artifact reference are also available as
`EvalAuthorResult.insight_suite_identity` and
`EvalAuthorResult.insight_suite_artifact_ref`.

Insight metrics remain adaptive development feedback. They may steer round
analysis, goal-tree updates, and proposals, but validation remains the direct
Pareto and winner-selection criterion. Promotion suggestions require complete
repeated baseline-to-winner improvement evidence, remain advisory, and never
mutate the canonical validation dataset.

## Intended Invocation

Until a CLI or platform job is wired, Python callers can invoke the runner
directly:

```python
import asyncio
from pathlib import Path

from nemo_experimentalist_plugin.eval_author.models import EvalAuthorConfig
from nemo_experimentalist_plugin.eval_author.run import run_eval_author
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef


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
