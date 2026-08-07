# NeMo Eval Author Plugin

Library-only plugin that owns the Eval Author agent (`eval_author/`).

## Direction of travel

**Eval Author is meant to become standalone, with nothing imported from
Experimentalist.** Prefer duplicating a helper over sharing one, even when sharing
looks tidier.

Right now the two packages depend on each other:

| Arrow | Status | Why |
| --- | --- | --- |
| Experimentalist → Eval Author | permanent | insight mode imports `EvalAuthor` and `EvalAuthorConfig` at module scope |
| Eval Author → Experimentalist | temporary | still borrows evaluator/Harbor, staging, trace, tools, cache, backend |

[`tests/test_plugin_boundary.py`](tests/test_plugin_boundary.py) pins the second list
so it can only shrink, and names what each remaining import is still for. `uv`
resolves the current cycle; install both packages with:

```bash
uv sync --group experimentalist
```

## Public API

```python
from nemo_eval_author_plugin.eval_author.agent import EvalAuthor, build_eval_author_agent
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_eval_author_plugin.eval_author.run import run_eval_author

# Still borrowed from Experimentalist, and on the way out. Treat these as Eval Author's
# own types once they move; do not build new code on the Experimentalist paths.
from nemo_experimentalist_plugin.entities import Dataset, DatasetRef
from nemo_experimentalist_plugin.experimentalist.components.dataset_staging import stage_task_template
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import TraceAnalyzer
from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import TraceExplorer
```

## Agent models

Run `nemo setup` and select the default and fast models for the active Platform
context. Eval Author uses the default model for authoring and the fast model for
summarization. Press Enter at the fast-model prompt to reuse the default model.

The selections are workspace-qualified Platform Model Entity IDs. The Platform
routes each request to the provider registered for that entity and reads its
credential from Platform Secrets; Eval Author does not accept separate provider,
endpoint, key, or model environment variables.

For non-interactive and isolated environments, `NEMO_DEFAULT_MODEL` and
`NEMO_FAST_MODEL` can override the stored selections. Values must still use
`workspace/model-name` and refer to Model Entities on the target Platform.

A `nemo agents eval-author` CLI is registered under `nemo.cli.agents` and
mounted by the agents plugin. Verb scaffolding is in place
(`discover`, `audit`, `propose`, `run`, `doctor`); bodies are still
placeholders until ASE-673–678 land. The library runner already uses the
configured Platform model pair.
