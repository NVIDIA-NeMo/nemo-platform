# NeMo Anonymizer Plugin

A NeMo Platform plugin that wraps the
[NVIDIA-NeMo/Anonymizer](https://github.com/NVIDIA-NeMo/Anonymizer) library
to detect and replace/rewrite PII in tabular text data.

The plugin exposes an `anonymizer` service, CLI commands under
`nemo anonymizer`, an SDK accessor on `NeMoPlatform.anonymizer`, a streaming
`anonymizer.preview` function, and an `anonymizer.run` job that executes
on the `nmp-cpu-tasks` container image.

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
- Input sources: `http(s)://` URL or NeMo Platform fileset reference.
- Execution requires `model_configs` so requests route through NeMo Platform
  Inference Gateway instead of the library's NVIDIA Build defaults.

## Installation (developer)

This plugin is a `uv` workspace member. From the repo root:

```bash
uv sync
```

## CLI quickstart

```bash
nemo anonymizer preview submit --spec-file ./preview_spec.yaml --workspace my-workspace

nemo anonymizer run submit --spec-file ./run_spec.yaml --workspace my-workspace
```

Execution supports `http(s)` URLs and filesets, and requires explicit `model_configs`.

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
