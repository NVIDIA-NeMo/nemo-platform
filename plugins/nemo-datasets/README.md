<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Datasets Plugin

The dataset profiler. Reads a fileset of dataset files and produces a `DatasetProfile`: what
partitions and splits are there, what the row schema is, per-column statistics, and a classification
of what kind of training data this is.

## What it produces

One artifact, described by `nemo_platform_plugin.files.dataset_profile.DatasetProfile`:

| Block | Answers |
|---|---|
| `coverage` | how much of the dataset the profile is based on — rows scanned vs present, files read vs present, bytes |
| `partitions[].splits[]` | the splits, their exact row counts, and a glob that selects each one's files |
| `partitions[].features[]` | the row schema, with a `semantic_role` assigned per column |
| `partitions[].stats{}` | per-column measurements — length distributions, numeric ranges, chat structure, null rates |
| `partitions[].classification` | `dataset_type`, `format`, `prompt_form`, `modality`, `verifiability`, plus the evidence for each |
| `file_errors[]` | every file the profiler could not use, named, with a reason |

The profile is designed to be a **substitute for having the data**. A consumer picking a
`max_seq_len`, or deciding whether a dataset can drive a verifiable-reward RL run, should be able to
answer that from a few hundred bytes of profile rather than a pass over the fileset.

## Usage

The profiler runs as a job task, not a `nemo` CLI command:

```bash
python -m nemo_datasets_plugin.tasks.profile
```

Directly, against a directory:

```python
from nemo_datasets_plugin.profiler.file_source import LocalFileSource
from nemo_datasets_plugin.profiler.pipeline import profile

result = profile(LocalFileSource("/path/to/dataset"))
print(result.model_dump_json(indent=2))
```

`profile()` takes three optional arguments:

- `row_budget` — rows per *partition*, divided across its files. Defaults to `None`, which reads
  everything. See [Why reading everything is the default](#why-reading-everything-is-the-default).
- `column_roles` — `{"q": "prompt"}`, for datasets whose column names the role table does not
  recognise. Hints take precedence over name detection but still have to pass the dtype gates; a
  rejected hint is reported as evidence rather than dropped.
- `created_at` — injectable so a profile can be made byte-reproducible in tests.

Supported formats: **parquet** and **jsonl / ndjson**. A file that plainly holds records but has no
reader (`.csv`, `.json`, `.arrow`, `.avro`, `.orc`, …) is reported as a `FileError` rather than
ignored — otherwise a directory of CSV shards would profile as an exhaustively-scanned *empty*
dataset, which is indistinguishable from a dataset that really is empty.

## How the measurement works

The diagrams under [Architecture](#architecture) are the formal version of this. Read this section
first — `stats.py` is genuinely hard to read top-to-bottom, because `RowFold` is the first class in
the file and depends on almost everything below it.

### The rule that causes all of it

> You are standing at a conveyor belt. Boxes go past. You may not keep any box. You have a notepad.
> At the end, someone asks you questions about all the boxes.

A dataset can be tens of gigabytes. It is read once and cannot be held. So every question the
profile answers has to be answerable from a notepad whose size never grows, however many rows go by.

That is all a **fold** is — belt, notepad, rule:

```
update(batch)   # some rows just went past; make your marks
finalize()      # the belt is empty; answer the questions
```

Everything that looks strange in `stats.py` is a consequence of that one constraint.

### A notepad is an accumulator

One notepad per column. A dataset with `messages` and `score` means two notepads, both marked as
each row goes by. The marks are tallies:

```
rows seen    ||||||||   8
nulls                   0
non-empty    ||||||||   8
```

Different columns want different questions asked, so there are four kinds:

| Notepad | For | What it marks |
|---|---|---|
| `StringAccumulator` | text | length distribution, distinct values |
| `NumericAccumulator` | numbers | min, max, mean, distinct values |
| `BoolAccumulator` | true/false | how many of each |
| `MessageAccumulator` | chat logs | turns, roles seen, whether it ends on the assistant |

### Which notepad answers

**JSONL says nothing about its columns.** It is lines of text with no header. What the `messages`
column *is* cannot be known until the last row has gone by — row 900,000 may hold a number and make
the whole column mixed. Three options, two of them bad:

- read the file twice — too slow;
- decide from the first N rows and hope — wrong sometimes, and silently;
- **mark each value on whichever notepad fits it, and decide at the end which notepad answers.**

**Parquet does say in advance** — its footer declares that `messages` is a list of `{role, content}`,
read before the belt starts. That does not call for a different mechanism, only for skipping the
guess: the same notepads are used, and the declared dtype picks which one answers instead of the
observed types picking.

→ one `RowFold`, driving one `RoutedAccumulator` per column. `RoutedAccumulator` is not clever —
it is a notepad per shape, plus a `SchemaFold` (inferred columns only) tracking which types have
been seen.

A notepad is opened **the first time a value needs it**, so a column of one type pays for one. That
matters more as shapes are added: building all of them up front billed every column for every shape
the profiler knows, whether or not its values ever reached them.

It also costs less per value than it sounds. A string is only ever marked on the string notepad, an
int only on the numeric one — the same work, just filed by shape. State stays flat whether the file
holds 10,000 rows or 1,000,000.

### The histogram: how to answer "median length" without keeping the lengths

Writing down 40 million lengths and sorting them is a notepad that weighs as much as the dataset.
So the page comes **pre-printed with buckets** and lengths are tallied into them.

Below 32, every length has its own line and is recorded **exactly**. Above it the buckets widen with
the magnitude — 32 slices per doubling — so the width stays a roughly constant *fraction* of the
value rather than a constant amount:

| value | its bucket | width | relative |
|---:|---|---:|---:|
| 31 | `[31, 32)` | 1 | exact |
| 1,000 | `[992, 1008)` | 16 | 1.6% |
| 1,000,000 | `[999424, 1015808)` | 16,384 | 1.6% |

Measured against exact quantiles on real shards: ~2%. And the page never grows.

For a `messages` column holding six 2-turn chats, one 3-turn and one 4-turn, the entire notepad is:

```python
_turns._counts == {2: 6, 3: 1, 4: 1}
```

which is enough to answer "median 2, max 4". Turn counts are small enough to land in the exact
region, so the buckets are legible by hand; a `content_chars` histogram over real text is the same
structure with wider buckets at the top end.

The trade is deliberate. The **count** is exact, because every row was tallied and none sampled;
only the **value** is rounded. `max` is tracked exactly and separately, since it is the one number a
reader may treat as a hard bound.

→ `_LengthHistogram`. See also [Why a histogram and not a reservoir](#why-a-histogram-and-not-a-reservoir).

### The vocabulary: a list that erases itself

Counting distinct values exactly means *remembering* them. For a `label` column of
`{safe, unsafe}` that is two words. For a column of reasoning traces it is the whole dataset —
the rule broken. So the notepad watches itself and gives up when the column stops looking like a
short list:

| Bound | Value |
|---|---|
| distinct values | 1,024 |
| characters in any one value | 256 |
| total bytes | 64 KB |

Giving up means **erasing the page and stopping**, permanently:

```
1,024 distinct values ->  84,548 bytes retained
1,025 distinct values ->     658 bytes retained, values gone
```

The 256-character bound is the one doing the real work. It does not ask *how many* values there are,
it asks **what kind of column this is** — a category name is short by nature, so one
paragraph-length value settles it on sight and free-text columns bail out immediately rather than
after 1,024 rows.

→ `_Vocabulary`.

### Probes: the yes/no tallies

Stats measure *how much*. Probes count *whether the tell-tale sign was there*:

```
rows                 8
non_empty            8
texts                8    values readable as text
extractable_answer   0    contained "####" or "\boxed{}"
transcript_marker    0    looked like "\n\nHuman:" / "\n\nAssistant:"
```

These are what later decides whether a dataset is *verifiable* — whether a grading answer is
embedded that a model's output could be checked against. They are tallied on the **same pass** as
the stats, because opening the row is the expensive part; once it is open, look for everything.

→ `ColumnProbes`.

### Reading the notepad

When the belt is empty, `classify()` reads **only the notepad** and says what the shipment was:

```
dataset_type  = "messages"
format        = "conversational"
verifiability = None            # checked; there is nothing to auto-grade
```

It never sees a row. That is the payoff of the rule — the rows are long gone and the partition can
still be described. See [Why absence is a claim](#why-absence-is-a-claim) for why `None` there is an
answer rather than a gap.

### The one exception, and why the order looks backwards

For a few roles — `label`, `provenance`, `meta`, `rank` — the actual values are worth putting in the
report. Knowing a label column is exactly `{safe, unsafe}` is useful.

But which columns those are is not known until the classifier has spoken. So:

1. during the pass, `_Vocabulary` quietly keeps the values it has seen;
2. `classify()` assigns roles;
3. **then** `quote_enumerations` writes the values for quotable roles and drops the rest.

That is why quoting runs *after* classification rather than during the pass — and it only works
because the values were held back, since the belt cannot be rewound.

→ `quote_enumerations`, gated on `_QUOTABLE_ROLES`. See also
[Why the profile almost never contains row content](#why-the-profile-almost-never-contains-row-content).

### Reading `stats.py`

Not top to bottom. In this order:

1. `ColumnAccumulator` — the base notepad. Everything else is this plus specifics.
2. `StringAccumulator` — the simplest real one, barely 20 lines.
3. `_LengthHistogram` and `_Vocabulary` — the two tricks above.
4. `_MEASUREMENTS` and `_measurement_for` — five lines, and the only place a dtype becomes a
   measurement.
5. `RoutedAccumulator` — one column, measured by shape.
6. `RowFold` — the columns of a partition, declared or discovered.

## Architecture

### Pipeline

```mermaid
flowchart TD
    START(["profile(source, row_budget, column_roles)"]) --> LIST["source.list_files()<br/><i>FileEntry: path, size_bytes</i>"]
    LIST --> DET{"detect_format<br/>by extension"}

    DET -->|".parquet / .jsonl"| DATA["data_entries"]
    DET -->|".csv .json .arrow …<br/>is_unsupported_data"| UNSUP["FileError:<br/>'no reader for X'"]
    DET -->|"README, LICENSE"| IGNORE["ignored:<br/>not data, counted nowhere"]

    DATA --> GRP["group_partitions<br/><i>by top-level dir; split dirs excluded</i>"]
    GRP --> LOOP{{"for each partition"}}
    LOOP --> PEEK["_peek_files<br/><i>footers only, no rows</i>"]
    PEEK --> BRANCH{"every file<br/>declared a schema?"}

    BRANCH -->|"yes — parquet"| UNI["_unify_schemas<br/><i>order-independent across shards</i>"]
    UNI --> DERIVE["derive_features<br/><i>arrow types to dtypes</i>"]
    DERIVE --> CF["RowFold(features)<br/><i>columns named up front</i>"]
    BRANCH -->|"no — jsonl"| ICF["RowFold(None)<br/><i>columns discovered as they appear</i>"]

    CF --> SPLITS
    ICF --> SPLITS["resolve_splits<br/><i>from paths, format-agnostic</i>"]
    SPLITS --> READ["read + fold"]
    READ --> GLOB["infer_data_files<br/><i>verified against full listing</i>"]
    GLOB --> MEASURE["folds.measure()"]
    MEASURE --> PP["PartitionProfile"]

    PP --> LOOP
    LOOP -->|"done"| ASM["DatasetProfile<br/>coverage + partitions + file_errors"]
    UNSUP --> ASM
```

### The fold

Batches are measured and released. Nothing retained grows with the file.

```mermaid
flowchart LR
    subgraph FILES["for each split, for each file"]
        direction TB
        OPEN["reader.batches(source, entry, row_cap)"]
        OPEN --> B1["batch of 1024 rows"]
    end

    B1 -->|"folds.update(batch)"| FOLD

    subgraph FOLD["_PartitionFolds — state constant in rows"]
        direction TB
        COL["<b>RowFold</b><br/>one RoutedAccumulator per column"]
        PRE["<b>PrefixPairFold</b><br/>relational: chosen vs rejected<br/><i>same row, two columns</i>"]
    end

    B1 -.->|"dropped — no reference kept"| GONE(["discarded"])

    FOLD --> ACC

    subgraph ACC["inside one accumulator"]
        direction TB
        CNT["counters<br/>rows, nulls, non_empty"]
        HIST["_LengthHistogram<br/><i>magnitude buckets, no RNG seed</i>"]
        VOC["_Vocabulary<br/><i>1024 distinct / 256 chars / 64KB</i><br/>past the bound: discards, counts on"]
        PROBE["ColumnProbes<br/><i>run on every column, no role gate</i>"]
    end
```

### The measure stage

Ordering is load-bearing: quoting a column's values is gated on its **role**, and roles do not exist
until classification assigns them.

```mermaid
flowchart TD
    FIN["RowFold.finalize() → (features, measured)"]
    FIN --> M["measured:<br/>stats · probes · vocabularies · errors<br/><i>features: declared, de-duplicated — or folded</i>"]

    M --> CLS["classify(features, stats, probes, prefix_pair)<br/><i>reads no rows</i>"]
    CLS --> ROLES["assigns semantic_role onto features"]
    ROLES --> AXES["dataset_type · candidates · format<br/>prompt_form · modality · verifiability"]

    AXES --> QUOTE["quote_enumerations(features, stats, vocabularies)"]
    QUOTE --> GATE{"role in _QUOTABLE_ROLES?<br/><i>label, provenance, meta, rank</i>"}
    GATE -->|"yes"| VALS["categorical.values<br/><b>the only path row content<br/>reaches the stored profile</b>"]
    GATE -->|"no"| NONE["values = None"]

    GUARD["wide try/except wraps all of this<br/>failure → dataset_type='unknown' + error Evidence"]
    GUARD -.->|"guards"| CLS
```

## Module map

| Module | Responsibility |
|---|---|
| `profiler/file_source.py` | the `FileSource` seam — `list_files()` + `open()`, the only way the core touches storage. `LocalFileSource` covers a directory on disk; a ranged-read source over the Files API is a later drop-in behind the same two methods |
| `profiler/readers/` | one stateless handler per format, resolved by extension. `peek()` for what a file declares, `batches()` for its rows |
| `profiler/partition.py` | groups files into partitions by top-level directory |
| `profiler/splits.py` | resolves splits from paths, and rebuilds a `data_files` glob per split |
| `profiler/schema.py` | derives the `features` tree, from a declared arrow schema or folded out of rows |
| `profiler/stats.py` | the per-column accumulators and the content probes |
| `profiler/classify.py` | interprets schema + stats + probes into roles and classification axes |
| `profiler/pipeline.py` | drives all of the above and assembles the envelope |

## Design decisions

### Why reading everything is the default

`DEFAULT_ROW_BUDGET = None`. Every partition is **folded**: batches are measured and let go, and
nothing kept grows with the file, so an exhaustive read costs what a short one costs in memory. What
the budget bounded was never really rows — it was risk.

`row_budget` survives as a way to ask for a shorter run, and it is a *target* rather than a ceiling:
`MIN_ROWS_PER_FILE = 10` is the floor every file is read to, however thin its share gets. A file
sampled below that cannot contribute the columns it alone witnesses, and file-level sampling would
reintroduce the same coverage hole from the other direction.

### Why every file is opened

Sampling a *subset of files* hides columns that appear only in later shards. Schemas are unified
across every file in a partition (`_unify_schemas`), so a column introduced by shard 47 is in the
profile. Taking the first file's schema would make the result depend on which shard happens to sort
first.

### Why quantiles instead of mean

Mean and max cannot tell "uniformly medium-length" apart from "mostly short with a long tail", and
those call for opposite sequence budgets. Measured on two synthetic sets with near-identical means:

```
             mean     p50     p95     p99     max
uniform       999    1000    1040    1040    1050
tailed        936     103    8320    8832    8994

uniform  budget from mean -> 49.4% of rows truncated | from max ->  5% of window wasted
tailed   budget from mean -> 10.0% of rows truncated | from max -> 90% of window wasted
```

`p50` read against `p99` is what distinguishes them. `max` is exact and is the only number safe to
treat as a hard bound; `p50`/`p95`/`p99` are read off magnitude-bucketed counters and are accurate
to within a couple of percent. Every row is counted, so the *rank* is exact — only the value is
rounded, to a bound that does not grow with the dataset.

### Why a histogram and not a reservoir

A reservoir sample would give exact quantiles, but it needs an RNG seed, and a seed in a stored
contract is a number a consumer can come to depend on. Bucketed counters trade ~2% quantile error
for a profile whose reproducibility does not rest on a random draw.

### Why the profile almost never contains row content

`categorical.values` is the single exception, and it is gated on a column's **role** — `label`,
`provenance`, `meta`, `rank` — not on its cardinality. Cardinality inverts on small data: in a
three-row dataset every column holds few distinct values, free text included, so a cardinality gate
stored prompts verbatim. A role says what a column *is*, at any size.

### Why absence is a claim

`verifiability: null` means "not verifiable", not "not measured". `data_files: null` means "these
files are not expressible as one glob", which a consumer can handle — an approximate glob is not a
smaller version of the right answer, it silently pulls a README or a sibling split into a training
set. Every candidate pattern is verified against the **entire** file listing before it is emitted.

### Why failures are isolated per column and per file

Two guards. A narrow one per column per batch: a value no detector anticipated costs that column its
measurements and nothing else. A wide one around the whole measure stage for anything structural
that no single column owns. An unreadable file is named in `file_errors`, contributes no rows, flips
`rows_complete` off, and never aborts the profile.

## Worked examples

Verified against real Hugging Face datasets. Reproduce with:

```python
from huggingface_hub import snapshot_download
from nemo_datasets_plugin.profiler.file_source import LocalFileSource
from nemo_datasets_plugin.profiler.pipeline import profile

d = snapshot_download("openai/gsm8k", repo_type="dataset",
                      local_dir="gsm8k", allow_patterns=["*.parquet"])
print(profile(LocalFileSource(d)).model_dump_json(indent=2))
```

> **Note:** `snapshot_download` writes a `.cache/huggingface/` tree alongside the data, and the
> profiler does not skip dotted directories. Its bookkeeping `.json` files are reported as
> `FileError`s, which makes `coverage.rows_present` unknown for the whole dataset. Delete `.cache/`
> or point `LocalFileSource` at the data subdirectory.

### `openai/gsm8k` — verifiable reasoning, two configs

```
rows_present=17,584   bytes=5,889,887   partitions=['main', 'socratic']

partition 'main'
  split test   canonical=test   n=1319  glob='main/test*.parquet'
  split train  canonical=train  n=7473  glob='main/train*.parquet'
  features: question->prompt (string), answer->completion (string)
  -> prompt_completion / standard / explicit
  -> verifiability=extractable_final_answer coverage=1.000
     question  p50=218 p99=536  max=985
     answer    p50=260 p99=744  max=1228

partition 'socratic'
  ... same schema; answer p50=412 p99=1072 max=1657
```

Two configs become two **partitions**, each classified independently. The socratic answers are
~1.6× longer at the median — a real difference in sequence budget that a single merged profile would
have averaged away.

### `HuggingFaceH4/no_robots` — chat, and the sibling-split case

```
rows_present=20,000
  split test       canonical=test   n=500   glob='data/test-*.parquet'
  split test_sft   canonical=test   n=500   glob='data/test_sft*.parquet'
  split train      canonical=train  n=9500  glob='data/train-*.parquet'
  split train_sft  canonical=train  n=9500  glob='data/train_sft*.parquet'

  features: prompt->prompt, prompt_id->id, messages->messages, category->meta
  -> messages / mixed / explicit   candidates=['messages', 'prompt_only']

  messages  turns p50=2 p99=9  content_chars p99=5568
            roles=['system','user','assistant']  ends_with_assistant=1.00  alternation=1.00
  category  values=['Brainstorm','Chat','Classify','Closed QA','Coding',
                    'Extract','Generation','Open QA','Rewrite','Summarize']
```

Note `data/train-*.parquet` rather than `data/train*.parquet`: `train` sits beside `train_sft`, and
the simple pattern would have swallowed both. Verification is what demotes it, so the narrower form
is only reached when it is actually needed.

`category` has its values quoted because its detected role is `meta`; `prompt` does not, because its
role is `prompt`.

### `trl-lib/ultrafeedback_binarized` — preference pairs

```
rows_present=63,135
  split test   n=1000    glob='data/test*.parquet'
  split train  n=62135   glob='data/train*.parquet'

  features: chosen->chosen (messages), rejected->rejected (messages),
            score_chosen->score (float64), score_rejected->score (float64)
  -> preference_pair / conversational / implicit

  chosen          turns p50=2 p99=2  content_chars p99=6336  ends_with_assistant=1.00
  rejected        turns p50=2 p99=2  content_chars p99=6080  ends_with_assistant=1.00
  score_chosen    min=1.0 max=10.0 mean=7.83
  score_rejected  min=1.0 max=10.0 mean=5.96
```

The scores are on a **1–10** scale, not `[0, 1]`. A pipeline that assumes normalised rewards does
not crash on this — it trains badly. `min`/`max` are exact, so this is a fact rather than a sample.

`prompt_form: implicit` because the prompt is embedded in the first turn of both `chosen` and
`rejected` rather than sitting in its own column.

### `tatsu-lab/alpaca` — classic instruction SFT

```
rows_present=52,002
  split 'train-00000-of-00001-a09b74b3ef9c3b56'  canonical=train  n=52002

  features: instruction->prompt, input->context, output->completion, text->(no role)
  -> prompt_completion / standard / explicit

  instruction  p50=57  p99=127  max=489
  input        p50=0   p99=276  max=2467     <- half the rows have no context
  output       p50=186 p99=1200 max=4181
```

The split *name* is unlovely: `_SHARD_SUFFIX` anchors on end-of-string, and this file carries a
content hash *after* the shard marker. `canonical` still resolves to `train` because alias matching
is prefix-based, so downstream consumers keying on `canonical` are unaffected.

`input` having `p50=0` is the profile earning its keep — half of Alpaca's rows have an empty context
field, which changes how the prompt template should be built.

## Limitations

- **Two formats.** Parquet and jsonl/ndjson. Everything else is reported, not read.
- **Characters are not tokens.** Length quantiles are in characters. The ratio runs ~3–5 chars/token
  for English prose and shifts substantially for code and non-Latin scripts, so `p99` is a starting
  point for `max_seq_len`, not a substitute for tokenizing.
- **Shape, not quality.** No duplication or contamination detection, no content-quality scoring, no
  PII detection — PII belongs to the anonymizer.
- **Dotted directories are not skipped.** See the `snapshot_download` note above.
- **No file-level sampling.** Every file is opened. A row budget bounds rows per partition, not
  files, so a fileset with very many shards still pays one open per shard.

## Tests

```bash
uv run pytest plugins/nemo-datasets/tests/ -q
```
