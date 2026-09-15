<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Stage 0+1: generate and prepare retrieval data

Stage 0 (`retrieval-generate`) turns a document corpus into judged Q&A pairs.
Stage 1 (`retrieval-prepare`) converts those pairs into `training.jsonl` plus a
BEIR `eval_beir/` split, and optionally mines hard negatives on GPU.

## Resolve the base URL first

```bash
BASE_URL="${NMP_BASE_URL:-http://localhost:8080}"
curl -fsS "${BASE_URL%/}/health/ready"
```

`NMP_BASE_URL` is only an override for a remote platform. Empty or non-JSON CLI
output means the platform is unreachable; recheck health and retry rather than
treating it as a missing entity.

## Point Stage 0 at the corpus

`corpus` takes a fileset ref (`workspace/fileset`, optionally `#subdir`) or an
`hf://` URI. Pin a revision for anything reproducible:

```bash
nemo files filesets create my-docs --workspace default --purpose dataset --exist-ok
nemo files upload /path/to/docs/ my-docs --workspace default
```

Corpus reach and chunking: `file_extensions`, `min_text_length`,
`sentences_per_chunk`, `num_sections`, and `max_artifacts_per_type`. Leave
`num_files` unset to use the whole corpus; setting it to 1 is a plumbing check
only, because a single document can place every query in the test split and
leave train empty.

## Control generation volume

`num_pairs` (default 7) is queries per artifact. `query_counts` and
`reasoning_counts` must use their exact key sets **and each sum to `num_pairs`**,
which is validated at submit:

| Field | Keys | Default |
|---|---|---|
| `query_counts` | `multi_hop`, `structural`, `contextual` | `3 / 2 / 2` |
| `reasoning_counts` | `factual`, `relational`, `inferential`, `temporal`, `procedural`, `causal`, `visual` | `1` each |

Raising `num_pairs` without rebalancing both dicts fails the spec. Other knobs:
`min_hops` / `max_hops`, `min_complexity`, `similarity_threshold`, `buffer_size`.

## Wire the model roles

All four roles go through Inference Gateway. Use `provider` plus optional
`chat_provider` / `embed_provider` overrides; never `NVIDIA_API_KEY` on the job.
Read `model_provider_id` from a READY deployment instead of assuming the
deployment name is the provider name.

```bash
nemo inference deployments get <deployment> --workspace default -f json
```

## Iterate with preview, then generate

`retrieval-preview` runs the same two providers without a fileset job. Use it to
sanity-check extraction and judging before paying for a full Stage 0 run.

```bash
nemo data-designer retrieval-preview --spec '{
  "generate": {
    "corpus": "default/my-docs",
    "provider": "default/nvidia-build",
    "artifact_extraction_model": "nvidia/nemotron-3-nano-30b-a3b",
    "qa_generation_model": "nvidia/nemotron-3-nano-30b-a3b",
    "quality_judge_model": "nvidia/nemotron-3-nano-30b-a3b",
    "embed_model": "nvidia/nemotron-3-embed-1b"
  },
  "num_records": 1
}'
```

Stage 0 writes `generation_result.json` plus Q&A JSONL to its fileset.

## Shape the Stage 1 split

Stage 1 defaults: `quality_threshold: 7.0`, `train_ratio: 0.8`, `val_ratio: 0.0`,
`seed: 42`, `max_pos_docs: 5`, `split_strategy: random`. Raise `train_ratio` on a
small corpus; lower `quality_threshold` when the judge rejects too much. Prefer
`retrieval-run` to chain both stages in one job.

```bash
nemo data-designer retrieval-run --workspace default --spec '{
  "generate": {
    "corpus": "default/my-docs",
    "provider": "default/nvidia-build",
    "artifact_extraction_model": "nvidia/nemotron-3-nano-30b-a3b",
    "qa_generation_model": "nvidia/nemotron-3-nano-30b-a3b",
    "quality_judge_model": "nvidia/nemotron-3-nano-30b-a3b",
    "embed_model": "nvidia/nemotron-3-embed-1b"
  },
  "prepare": {"enable_mining": false}
}'
```

Hard-negative mining (`enable_mining: true`) is a GPU step and needs `model` to
be a model entity with an attached encoder fileset; it loads that staged
directory with Hugging Face networking disabled. Never mine after conversion
produced an empty train split.

## Reuse an existing Stage 0 dump

Point `sdg_input` at a fileset or `hf://` URI. Live generate writes
`generation_result.json`, which is the default, so most runs set nothing extra.
A published dump under another name needs the filename on the ref or in
`generation_file`:

```bash
nemo data-designer retrieval-prepare --workspace default --spec '{
  "sdg_input": "hf://nvidia/Retrieval-Synthetic-NVDocs-v1@<revision>/nv_pp_dd_sdg.json",
  "enable_mining": false
}'

nemo data-designer retrieval-prepare --workspace default --spec '{
  "sdg_input": "default/retrieval-synthetic-nvdocs-v1",
  "generation_file": "nv_pp_dd_sdg.json",
  "enable_mining": false
}'
```

## Stage 1 output

One `artifacts` fileset per job, containing `training.jsonl`, `eval_beir/`
(`corpus.jsonl`, `queries.jsonl`, `qrels/test.tsv`), and the wrapped `train.json`
that mining consumes. Pass that fileset straight to Automodel as
`dataset.training` and to `retrieve-eval` as `dataset`: Automodel ignores the
non-JSONL siblings, and the BEIR loader accepts a root containing `eval_beir`.

```bash
nemo jobs get-status <prepare-job> -f json
nemo files list <artifacts-fileset> --workspace default
```
