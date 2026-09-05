# Evaluation Shapes

## Difference summary
Choose the evaluation shape from what produces the scored output. Metrics are
shared scorers; the input and evidence differ.

| Question | Dataset-driven | Task-driven | Retrieval-driven |
| --- | --- | --- | --- |
| What is the input? | Fixed dataset rows | Tasks with intent, inputs, and metrics | A BEIR corpus, queries, and qrels |
| What is scored? | One output per row | One or more trials per task | Ranked corpus IDs for every query |
| Which metrics apply? | The same metric set applies to every row | Each task can define its own metrics | Corpus retrieval metrics such as nDCG and recall |
| What evidence is available? | Row fields, row scores, and aggregates | Final output, trajectory, tool calls, other trial evidence, per-task rewards, and summary | Per-query rankings and corpus aggregates |
| Platform job | `evaluate submit` | `agent-evaluate submit` | `retrieve-eval submit` |

## Dataset-driven evaluation

Use dataset-driven evaluation for a fixed set of examples where the same
scoring rules apply to every row. Typical uses include model quality checks
and labeled-set benchmarks.

Each row contains the fields consumed by the metric, for example:

```python
{"question": "Capital of France?", "expected": "Paris", "output": "Paris"}
```

Then choose the scorer, validate its field mapping with the standalone SDK,
and submit only after the pass/fail smoke case behaves as expected.

## Task-driven evaluation

Use task-driven evaluation when the system performs work and the process can
matter as much as the final answer. A model, agent, or runner produces a trial
containing the final output and available execution evidence. Tasks can carry
different metrics, so one taskset can grade heterogeneous work.

Choose this shape for agent behavior, tool use, multi-step work, runner-based
benchmarks, or rescoring precomputed trials.

Define tasks, trials or a target, concurrency, and result handling before
submitting the task-driven job. Read the Agent Evaluation reference for details.

## Retrieval-driven evaluation

Use retrieval-driven evaluation when an embedding model ranks a corpus for a
set of queries. The dataset must use the BEIR test layout:
`corpus.jsonl`, `queries.jsonl`, and `qrels/test.tsv`. The evaluator calls the
target's `/v1/embeddings` endpoint with query and passage input types, then
computes corpus nDCG and recall.

This is not row-based RAG answer scoring. Do not convert qrels into artificial
answer rows or use an LLM judge for deterministic retrieval quality.

Submit the fileset and embedding target as references:

```bash
uv run nemo evaluator retrieve-eval submit --spec \
  '{"dataset":"default/eval-beir","target":"default/embed-nim","k":[1,5,10,100]}'
```

The `eval_results.json` artifact contains nDCG, recall, precision, and MAP at
each cutoff. An optional `baseline` model reference adds relative nDCG@10 and
Recall@10 to the job output.
