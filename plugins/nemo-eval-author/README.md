# NeMo Eval Author Plugin

Library-only plugin that owns the Eval Author agent (`eval_author/`). Shared
evaluator, trace, staging, tools, and client helpers stay in
`nemo-experimentalist-plugin`; this package takes a hard dependency on
Experimentalist and imports those modules from there.

Experimentalist insight mode imports `EvalAuthor` from this plugin at runtime.
Install both via the workspace group (avoids a circular package dependency):

```bash
uv sync --group experimentalist
```

## Public API

```python
from nemo_eval_author_plugin.eval_author.agent import EvalAuthor, build_eval_author_agent
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_eval_author_plugin.eval_author.run import run_eval_author

# Shared infrastructure lives in Experimentalist:
from nemo_experimentalist_plugin.experimentalist.components.evaluator import Dataset
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.components.dataset_staging import stage_task_template
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import TraceAnalyzer
from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import TraceExplorer
```

## Credentials (standalone)

Copy [`.example.env`](.example.env) to `.env` and set `AUTHOR_API_KEY` (and optionally model names / `NMP_BASE_URL`):

```bash
cp plugins/nemo-eval-author/.example.env plugins/nemo-eval-author/.env
```

`model_config` prefers `AUTHOR_*`. If those are unset it falls back to
`EXPERIMENTALIST_*` so Experimentalist insight-mode keeps working with a single
Experimentalist profile `.env`. On construction, Eval Author also bridges
`AUTHOR_*` into unset `EXPERIMENTALIST_*` slots so Experimentalist helpers such
as `TraceAnalyzer` see credentials during standalone runs. When the API base is
the NVIDIA Inference Gateway, `INFERENCE_API_KEY` is also accepted.

A `nemo eval-author` CLI that auto-loads this `.env` is not wired yet.
