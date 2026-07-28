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
from nemo_experimentalist_plugin.experimentalist.components.evaluator import Dataset
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.components.dataset_staging import stage_task_template
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import TraceAnalyzer
from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import TraceExplorer
```

## Credentials (standalone)

Copy [`.env.example`](.env.example) to `.env` and set `AUTHOR_API_KEY` (and optionally model names / `NMP_BASE_URL`):

```bash
cp plugins/nemo-eval-author/.env.example plugins/nemo-eval-author/.env
```

`AUTHOR_*` is Eval Author's credential contract, and `model_config` imports nothing
from Experimentalist. When the API base is the NVIDIA Inference Gateway over HTTPS,
`INFERENCE_API_KEY` is also accepted.

Two pieces of that module are transitional and disappear with the last
Experimentalist import, both tagged `TODO(eval-author-standalone)`:

- unset `AUTHOR_*` variables fall back to `EXPERIMENTALIST_*`, so insight mode works
  from a single Experimentalist profile `.env`. Setting `AUTHOR_*` explicitly today
  avoids the break when the fallback is removed.
- importing `nemo_eval_author_plugin._env_bridge` copies `AUTHOR_*` into unset
  `EXPERIMENTALIST_*` slots, so the Experimentalist helpers Eval Author still
  borrows see credentials during a standalone run. `eval_author.agent` imports it
  ahead of any Experimentalist agent, because those agents read the environment when
  their class body executes.

A `nemo eval-author` CLI that auto-loads this `.env` is not wired yet.
