# NeMo Eval Author Plugin

Library-only plugin that owns the Eval Author agent, Harbor evaluator stack, trace analysis helpers, and dataset staging used to author evaluation suites from Insights.

Experimentalist depends on this plugin the same way it depends on `nemo-insights-plugin`.

## Public API

```python
from nemo_eval_author_plugin.eval_author.agent import EvalAuthor, build_eval_author_agent
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_eval_author_plugin.eval_author.run import run_eval_author
from nemo_eval_author_plugin.evaluator import Dataset, DatasetRef, Evaluator
from nemo_eval_author_plugin.evaluator.factory import DatasetFactory, EvaluatorFactory
from nemo_eval_author_plugin.dataset_staging import stage_eval_author_inputs, stage_task_template
from nemo_eval_author_plugin.trace_analyzer import TraceAnalyzer, TraceAnalyzerConfig, Diagnostic
from nemo_eval_author_plugin.trace_explorer import TraceExplorer
```

## Install

From the repository root:

```bash
uv sync --group experimentalist
```

## TODO(shared-module)

The following modules are exact copies of Experimentalist helpers and should eventually live in a shared package:

- `tools.py`
- `model_config.py`
- `cache.py`
- `client.py`
- `repository.py` (agent clone helpers used by `backend.py`)
