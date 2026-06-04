# NeMo Memory plugin

Triage, evaluate, and extract fine-tune training data from durable agent
memory stores (pi-hermes-memory format today; other adapters welcome).

## Status

Phase 1 + 2 of bd `mdubrinsky-7au` have shipped. Three NemoJobs:

- `nemo memory triage` — run the judge council against a corpus, emit a
  staged-proposal artifact (one JSON + Markdown pair).
- `nemo memory eval` — diff two triage artifacts (baseline vs candidate),
  emit an agreement report.
- `nemo memory export` — build a labeled SFT corpus from a triage
  artifact, ready for fine-tuning a smaller judge model.

See `src/nemo_memory_plugin/triage/DESIGN.md` for the Phase 0 mutation
contract, council architecture, and phasing.

See `src/nemo_memory_plugin/triage/RESULTS.md` for Phase 1 smoke
results, judge calibration findings (Sonnet 4.6 vs the Nemotron family),
and the v1-to-v4 prompt evolution.

## CLI quickstart

Triage a pi-hermes USER.md corpus against the locked Sonnet 4.6 baseline:

```bash
nemo memory triage run \
    --spec-file examples/triage/baseline-sonnet-4-6-fileset.triage.yml
```

Diff a candidate run against the baseline:

```bash
nemo memory eval run \
    --spec-file examples/triage/sonnet-vs-self-omnistation.eval.yml
```

Extract the v1 Sonnet-vs-Nano disagreement set as SFT training data:

```bash
nemo memory export run \
    --spec-file examples/triage/export-v1-disagreements.export.yml
```

## Python usage

The core primitives are pure data extractors with no LLM calls:

```python
from nemo_memory_plugin.triage.eval import compare_runs
from nemo_memory_plugin.triage.finetune import build_finetune_corpus

report = compare_runs(baseline_json, candidate_json)
print(f"strict agreement: {report.strict_rate * 100:.1f}%")

records, summary = build_finetune_corpus(
    triage_artifact_json,
    corpus_md,
    reference_judge="azure-anthropic-claude-sonnet-4-6",
    candidate_judge="nvidia-nvidia-nemotron-3-nano-30b-a3b",
    only_disagreements=True,
)
```

## Why this is a separate plugin

Memory-triage is independent of the agent build / evaluate / optimize
flow that `nemo-agents` exists for. Splitting it out means anyone who
just wants to ship and evaluate agents doesn't drag the council deps
(judge prompts, OpenAI + Anthropic clients, eval primitives) into their
installation. The reverse is true too: someone tuning agent memory
doesn't need NAT or LangGraph.

`nemo.services` and `nemo.sdk` entry points are intentionally absent
today. Those land when bd `mdubrinsky-7au.5` (Intake annotations +
Studio review surface) ships and there's a concrete HTTP consumer to
design routes against. Until then, the offline NemoJobs run through the
platform's generic jobs scheduler.
