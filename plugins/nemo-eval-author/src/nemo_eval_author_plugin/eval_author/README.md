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
- `eval_author.*`: agent tuning — see below.

### `EvalAuthorConfig` (model and completion options)

**Use `reasoning_effort` of `medium` or higher** (`high`, and any stronger
provider value your model accepts). Below `medium` — including `minimal`,
`low`, `none`, or omitting the field so the provider picks a weak default —
Eval Author often authors flat, non-discriminating metrics that look fine on a
broken baseline. The default is `"medium"` for that reason. Prefer raising
effort over lowering it when Author quality is inconsistent.

| Field | Default | Meaning |
| --- | --- | --- |
| `max_summary_tokens` | `80000` | Token budget for the fast-model summarizer. |
| `max_traces` | `10` | Insight `trace_refs` to analyze in depth. |
| `max_validation_repair_attempts` | `5` | Repair attempts after Insight verifier validation fails. |
| `reasoning_effort` | `"medium"` | OpenAI-shaped effort for Author clients. Keep at `medium` or higher for consistent metric authoring; do not set `null` / `minimal` / `low` unless you are deliberately testing failure modes. |
| `completion_params` | `{}` | Extra kwargs forwarded to `CompletionClient` (non-OpenAI backends or other OpenAI knobs). An explicit `reasoning_effort` wins over the same key here. |

Standalone `run_eval_author(...)` builds clients with these options. In
Experimentalist Insight mode, the runner nested-resolves Author-scoped clients
from the run config's `eval_author` block (same defaults), then restores the
outer Experimentalist default/fast pair for the optimization loop.

Example override in Experimentalist `--config` YAML:

```yaml
eval_author:
  max_traces: 5
  reasoning_effort: medium   # required floor for consistent Author metrics; use high if needed
  # completion_params:
  #   thinking:
  #     type: enabled
  #     budget_tokens: 2048
```

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
