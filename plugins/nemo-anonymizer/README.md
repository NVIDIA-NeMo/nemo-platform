<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Anonymizer Plugin

A NeMo Platform plugin that wraps the
[NVIDIA-NeMo/Anonymizer](https://github.com/NVIDIA-NeMo/Anonymizer) library
to detect and replace/rewrite PII in tabular text data.

The plugin exposes an `anonymizer` service, CLI commands under
`nemo anonymizer`, an SDK accessor on `NeMoPlatform.anonymizer`, a streaming
preview API, and an `anonymizer.run` job that executes on the
`nmp-cpu-tasks` container image.

## What it does

- **Detect** PII entities (names, emails, phone numbers, locations, ...) using
  GLiNER plus optional LLM verification.
- **Replace** them via one of four strategies: `Substitute` (LLM-driven
  realistic replacements), `Redact`, `Annotate`, `Hash`. The library's
  `Rewrite` mode is also supported.

## Functional parity with the library

The plugin provides functional parity with the
[NVIDIA NeMo Anonymizer library](https://github.com/NVIDIA-NeMo/Anonymizer):

- All four replacement strategies + `Rewrite` mode.
- Input sources for platform execution: local CSV/Parquet files through the CLI with `--fileset`, `http(s)://` URLs, or NeMo Platform fileset references.
- Preview and run requests require `model_configs` so model calls route through
  NeMo Platform Inference Gateway instead of the library's NVIDIA Build defaults.

## Installation (developer)

This plugin is a `uv` workspace member. From the repo root:

```bash
uv sync
```

## CLI quickstart

```bash
nemo anonymizer preview --spec-file plugins/nemo-anonymizer/examples/redact.yaml --num-records 2 --workspace my-workspace --fileset anonymizer-inputs
nemo anonymizer preview --spec-file plugins/nemo-anonymizer/examples/redact.yaml --num-records 2 --workspace my-workspace --fileset anonymizer-inputs --output-file preview.ndjson --quiet
nemo anonymizer preview --spec-file plugins/nemo-anonymizer/examples/redact.yaml --num-records 2 --workspace my-workspace --fileset anonymizer-inputs --output-remote-path previews/redact.ndjson
nemo anonymizer run --spec-file plugins/nemo-anonymizer/examples/redact.yaml --workspace my-workspace --fileset anonymizer-inputs
nemo anonymizer run --spec-file plugins/nemo-anonymizer/examples/redact.yaml --workspace my-workspace --fileset anonymizer-inputs --watch
nemo anonymizer run --spec-file plugins/nemo-anonymizer/examples/redact.yaml --workspace my-workspace --fileset anonymizer-inputs --watch --output-dir ./anonymizer-artifacts
nemo anonymizer run --spec-file plugins/nemo-anonymizer/examples/redact.yaml --workspace my-workspace --fileset anonymizer-inputs --dry-run  # print schema/request without submitting
```

Preview runs through the Anonymizer plugin service and streams non-log NDJSON
frames to stdout or `--output-file`; log frames go to stderr unless `--quiet`
is set. The example spec points at `plugins/nemo-anonymizer/examples/anonymizer-input.csv`;
pass `--fileset anonymizer-inputs` and the CLI uploads it before preview or run.
Full anonymizer runs execute as NeMo Platform Jobs. When `--fileset` is set,
run artifacts are stored in that fileset, and `--watch --output-dir` downloads
them locally after success. SDK/API callers should use `http(s)` URLs or
filesets directly and require explicit `model_configs`.

Fileset input references point at one CSV or Parquet file:

```bash
fileset://my-workspace/input-files#data/input.parquet
my-workspace/input-files#data/input.csv
input-files#data/input.csv
```

Config validation remains a manual local command:

```bash
nemo anonymizer validate --config ./anonymizer_config.yaml --model-configs ./model_configs.yaml
```
