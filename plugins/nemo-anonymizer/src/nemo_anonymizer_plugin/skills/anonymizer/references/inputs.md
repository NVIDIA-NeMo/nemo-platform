# Inputs

The anonymizer reads a **single CSV or Parquet file**. Configure it via the `data` block in the YAML spec:

```yaml
data:
  source: <http(s)-url | fileset-ref>
  text_column: text                # optional; defaults to "text"
  id_column: id                    # optional, stable record identifier
  data_summary: "Short free-text records; English."   # optional, helps LLMs
```

## Source kinds

| Kind     | Example                                          | Supported by                                                                              |
|----------|--------------------------------------------------|-------------------------------------------------------------------------------------------|
| Local    | `/tmp/input.csv` or `./data/input.parquet` | Not supported by plugin execution. Upload to a fileset or use HTTP(S). |
| HTTP(S)  | `https://example.com/input.csv`            | Plugin-service / Jobs execution (`preview submit`, `run submit`). |
| Fileset  | `<workspace>/<fileset>#<path>`                   | Plugin-service / Jobs execution (`preview submit`, `run submit`). |

Plugin-service / Jobs execution runs outside the caller's filesystem — use HTTP(S) URLs or fileset refs.

## Fileset references

Three equivalent shapes (the `#<path>` fragment is required and must point at a `.csv` or `.parquet` file):

```
fileset://my-workspace/input-files#data/input.parquet
my-workspace/input-files#data/input.csv
input-files#data/input.csv          # uses the request's workspace
```

For upload commands, use the platform files CLI docs or `nemo-files` skill. Then put the resulting fileset reference in `data.source`, for example `fileset://<workspace>/anonymizer-inputs#anonymizer-input.csv`.

## Choosing the text column

- The `text_column` defaults to `text`; include it explicitly when the input uses a different free-text column.
- The `id_column` is optional but recommended — when set, output rows preserve it so you can join detection results back to the source.
- All other columns in the input file are passed through to the output unchanged.

## Run Artifacts

Run jobs save an artifacts directory in {{platform_name}} job storage. Layout under that `artifacts/` directory:

| File                  | Description                                                                |
|-----------------------|----------------------------------------------------------------------------|
| `dataset.parquet`     | User-facing anonymized dataframe (replace/rewrite output).                 |
| `trace.parquet`       | Internal trace dataframe with detection details (spans, labels, confidences). |
| `metadata.json`       | Run metadata (includes the original text column name).                     |
| `failed_records.json` | Per-record failures with reasons. Only written when at least one record failed. |

### CLI retrieval

Use the standard Jobs CLI after `nemo anonymizer run submit` prints the job name:

```bash
nemo jobs get-status <job-name> --workspace <ws>
nemo jobs get-logs <job-name> --workspace <ws> --all-pages
nemo jobs results list <job-name> --workspace <ws>
nemo jobs results download artifacts --job <job-name> --workspace <ws> --output-file artifacts.tar.gz
```

Extract the downloaded tarball, then read `dataset.parquet`, `trace.parquet`, `metadata.json`, and optional `failed_records.json` from the extracted artifacts directory.
