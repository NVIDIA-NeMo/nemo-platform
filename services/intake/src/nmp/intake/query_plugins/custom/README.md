# Local query plugins

Python modules in this directory are **local-only** — they are gitignored and are not part of the
platform repo. Use them for prototype or org-specific query plugins during Studio plugin development.

## Setup

1. Add one module per query plugin (e.g. `experiment_error_summary.py`).
2. Copy `registry_local.py.example` to `registry_local.py` and list your plugin instances in
   `QUERY_PLUGINS`.
3. Restart intake. Registered ids appear on `GET …/query-plugins`.

At deploy time, org plugins should live in a separate Python package merged via
`NEMO_QUERY_PLUGINS_MODULES` instead of this directory.

## Example

```python
# registry_local.py (gitignored)
from nmp.intake.query_plugins.custom.experiment_error_summary import ExperimentErrorSummaryQueryPlugin
from nmp.intake.query_plugins.custom.experiment_error_spans import ExperimentErrorSpansQueryPlugin

QUERY_PLUGINS = [
    ExperimentErrorSummaryQueryPlugin(),
    ExperimentErrorSpansQueryPlugin(),
]
```
