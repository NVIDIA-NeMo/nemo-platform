<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Inputs

The anonymizer reads a **single CSV or Parquet file**. Configure it via the `data` block in the YAML spec:

```yaml
data:
  source: <local-path | http(s)-url | fileset-ref>
  text_column: text                # optional; defaults to "text"
  id_column: id                    # optional, stable record identifier
  data_summary: "Short free-text records; English."   # optional, helps LLMs
```

## Source kinds

| Kind     | Example                                          | Supported by                                                                              |
|----------|--------------------------------------------------|-------------------------------------------------------------------------------------------|
| Local    | `./data/input.csv` or `./data/input.parquet`     | CLI preview/run with `--fileset <name>`; the CLI uploads the file before remote execution. |
| HTTP(S)  | `https://example.com/input.csv`                  | Platform preview and Jobs execution (`run`).                                              |
| Fileset  | `<workspace>/<fileset>#<path>`                   | Platform preview and Jobs execution (`run`).                                              |

Platform preview and Jobs execution run outside the caller's filesystem. Use the CLI with `--fileset` to stage a local file, or use HTTP(S) URLs / fileset refs directly for SDK/API calls.

## Fileset references

Three equivalent shapes (the `#<path>` fragment is required and must point at a `.csv` or `.parquet` file):

```
fileset://my-workspace/input-files#data/input.parquet
my-workspace/input-files#data/input.csv
input-files#data/input.csv          # uses the request's workspace
```

For SDK/API upload commands, use the platform files CLI docs or `nemo-files` skill. Then put the resulting fileset reference in `data.source`, for example `fileset://<workspace>/anonymizer-inputs#anonymizer-input.csv`. For CLI preview/run, put the local CSV/Parquet path in `data.source` and pass `--fileset <name>`.

## Choosing the text column

- The `text_column` defaults to `text`; include it explicitly when the input uses a different free-text column.
- The `id_column` is optional but recommended — when set, output rows preserve it so you can join detection results back to the source.
- All other columns in the input file are passed through to the output unchanged.

## Run Artifacts

Run jobs save a working artifacts directory; the anonymized dataset is one file inside that directory.

Full `run` jobs store an `artifacts` result in NeMo Platform job storage. Layout under that `artifacts/` directory:

| File                  | Description                                                                |
|-----------------------|----------------------------------------------------------------------------|
| `dataset.parquet`     | User-facing anonymized dataframe (replace/rewrite output).                 |
| `trace.parquet`       | Internal trace dataframe with detection details (spans, labels, confidences). |
| `metadata.json`       | Run metadata (includes the original text column name).                     |
| `failed_records.json` | Per-record failures with reasons. Only written when at least one record failed. |

### Loading downloaded artifacts

Read the parquet files directly from the artifacts directory:

```python
import json
from pathlib import Path
import pandas as pd

artifacts_dir = Path("/path/to/downloaded/artifacts")
metadata = json.loads((artifacts_dir / "metadata.json").read_text())
dataset = pd.read_parquet(artifacts_dir / "dataset.parquet", dtype_backend="pyarrow")
trace   = pd.read_parquet(artifacts_dir / "trace.parquet",   dtype_backend="pyarrow")
failed_path = artifacts_dir / "failed_records.json"
failed_records = json.loads(failed_path.read_text()) if failed_path.exists() else []
```

The trace dataset (and `dataset.parquet` for `annotate` / `substitute` strategies) contains pyarrow-backed `struct<entities: list<...>>` columns. If you need plain Python `dict`/`list` values for JSON output, read via `pyarrow.parquet.read_table(...).to_pylist()` instead of `pd.read_parquet`.

### Remote CLI retrieval

For `run`, pass `--watch --output-dir <dir>` to download artifacts locally after a successful job. To retrieve artifacts later, use the standard Jobs CLI after `nemo anonymizer run` prints the job name:

```bash
nemo jobs get-status <job-name> --workspace <ws>
nemo jobs get-logs <job-name> --workspace <ws> --all-pages
nemo jobs results list <job-name> --workspace <ws>
nemo jobs results download artifacts --job <job-name> --workspace <ws> --output-file artifacts.tar.gz
```

Extract the downloaded tarball, then read `dataset.parquet`, `trace.parquet`, `metadata.json`, and optional `failed_records.json` from the extracted artifacts directory.
