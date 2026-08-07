<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Eval Author

> **Active development. Not intended for external use.**
>
> This plugin is incomplete and its interfaces will change without notice. It also
> runs code from the repository you point it at: validating a config imports that
> repository's agent module into the running process, which executes that module's
> top level. Treat pointing Eval Author at a repository as equivalent to running that
> repository's code yourself, and only do it for code you already trust. Sandboxing is
> not implemented yet.

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

`nemo agents eval-author discover` is the only implemented CLI command. It
answers whether Harbor can run a repository's evals and records the answer.

The command assembles a candidate Harbor `JobConfig` from the strongest source
the repository offers: a Harbor config file it already maintains, a `config.json`
from a prior job Harbor resolved and ran, an Experimentalist `optimizer.yaml`
profile plus the agent wrapper, or the Harbor task directory layout alone.

It validates that candidate through a ladder of Harbor's own calls rather than
reimplemented rules: schema, job resolution, task validity and coverage,
required host variables, the agent class, the environment backend, and a round
trip of the persisted bytes through `harbor job start --print-config`.
[`discovery/validate.py`](../discovery/validate.py) names the Harbor API behind
each rung. Findings that Harbor returned carry a `harbor_call`; the two checks
that are discovery's own carry none and can only warn. Whether each test script
names a reward file is read from the repository, because a script that builds
the path in a variable is indistinguishable from one that writes nothing.
Whether the agent subclasses `BaseAgent` is a judgement Harbor deliberately
does not make — it is strict for verifiers and not for agents — so failing it
would block a repository Harbor's own gate accepts.

The result is recorded to the `nemo-eval-author` fileset as
`<agent>/discovery.md`. A `<agent>/harbor-job.yaml` is published alongside the
report only when discovery authored the config; when the repository maintains
its own valid config file, the report points at that file instead. Nothing is
written into the repository under inspection.

When the config's agent is a `harbor_wrapper.py` in the repository, the run
command carries the wrapper's directory as `PYTHONPATH`:

```bash
PYTHONPATH=src/myagent harbor job start -c harbor-job.yaml
```

This is not a convenience. Harbor imports an agent with plain
`importlib.import_module` and never adds the working directory to `sys.path`, so
a config naming `harbor_wrapper:WrappedAgent` fails at the first trial with
`No module named 'harbor_wrapper'` without it. A Harbor `JobConfig` has no field
for a module search path, so it is recorded beside the config as
`run_config.pythonpath` in the report's front matter, repo-relative like every
other path in the artifact — `.` for a wrapper at the repository root. The agent
rung imports with exactly that search path and nothing else, so a rung that
passes is a rung the recorded command will pass too.

A dataset the profile declares as a registry ref alongside a `registry_url` is
recorded as a ref Harbor downloads rather than as a local directory, and
reported as a warning because resolving it needs the registry to be reachable.

Every run revalidates from scratch. The report is a record of what was true when
it was written, not a cache that a later run consults.

Exit code 0 means a config was validated and recorded. Every other outcome exits
non-zero, including a config Harbor accepted but that could not be uploaded,
which is what makes the command usable as a gate.

`discover` takes these flags:

- `--repo`: agent repository to inspect. Defaults to the current directory.
- `--agent`: name the artifacts are stored under. Defaults to the agent named in
  `optimizer.yaml`, else a slug of the directory name.
- `--dry-run`: print the findings and the config without uploading anything.

There are no flags for platform state. The workspace and cluster come from the
active `nemo` context, `NMP_WORKSPACE` still overrides the workspace, and the
Harbor environment backend comes from the repository's own config or Harbor's
default.

The other verbs are registered in [`cli.py`](../cli.py) so the command tree is
discoverable. Each one exits non-zero with a not-implemented message.

## Planned Commands

- `nemo agents eval-author audit`: report coverage gaps in an existing Harbor suite
  against `ETHOS.md`, without changing the suite.
- `nemo agents eval-author propose`: draft reviewable Harbor tasks and verifier
  patches for the gaps the audit found.
- `nemo agents eval-author run`: run `discover`, `audit`, and `propose` as one
  pipeline.
- `nemo agents eval-author doctor`: check the credentials, platform access, and
  runtime the other commands need.
