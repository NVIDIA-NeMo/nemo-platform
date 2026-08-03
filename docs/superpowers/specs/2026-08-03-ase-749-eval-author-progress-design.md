# ASE-749: Eval Author progress output (via Experimentalist RunReporter)

## Problem

Experimentalist gained additive run-progress narration in [PR #965](https://github.com/NVIDIA-NeMo/nemo-platform/pull/965) (`RunReporter` in `experimentalist/reporting.py`). Eval Author still goes quiet for the whole insight-suite materialization → analysis → metric-authoring stretch when invoked from Experimentalist insight mode, so the parent run looks stalled.

## Goal

When Experimentalist runs Eval Author, reuse the parent's `RunReporter` so the same stderr narration continues through Eval Author phases — including clear start and complete lines — without a second header/footer or any change to standalone Eval Author CLI paths (those remain `reporter=None` for now).

## Non-goals

- Standalone `run_eval_author` / future `nemo agents eval-author run` narration (follow-up).
- Extracting a shared reporting package.
- Duplicating `RunReporter` into Eval Author.
- Changing Experimentalist candidate/reward narration or Eval Author return values / control flow.

## Approach

**Import Experimentalist's utilities and allowlist the import** (option A from design discussion).

Eval Author imports `RunReporter` from `nemo_experimentalist_plugin.experimentalist.reporting` and adds that module to `_ALLOWED_EXPERIMENTALIST_IMPORTS` in `tests/test_plugin_boundary.py`, with a note that ASE-749 reuses the Experimentalist narrator rather than duplicating it. This is deliberate temporary coupling toward standalone: the allowlist still ratchets; we are not opening the door to unrelated Experimentalist imports.

## Architecture

```text
Experimentalist loop (owns RunReporter lifecycle)
  run_started / progress / candidate_* / run_finished
        │
        ▼ reporter=deps.reporter
EvalAuthor.__init__(..., reporter: RunReporter | None = None)
        │
        ▼ when reporter is set
  progress("eval author · starting")
  progress(... materialize / analyze / discover / author / repair ...)
  progress("eval author · complete")   # on success
  # never calls run_started / run_finished
```

### Injection

- Add optional `reporter: RunReporter | None = None` on `EvalAuthor.__init__`, stored as `self._reporter`.
- Thread the same optional arg through `build_eval_author_agent` for API consistency (callers that do not pass it stay quiet).
- In `loop.py` insight-mode construction, pass `reporter=reporter` (the loop-local `deps.reporter`).
- Leave `run_eval_author()` unchanged: it keeps using `build_eval_author_agent` without a reporter.

### Emission rules

- Every emit is best-effort and must never break the run (same contract as Experimentalist: call `RunReporter` methods, which already swallow sink failures).
- When `self._reporter is None`, emit nothing.
- **Do not** call `run_started` or `run_finished` from Eval Author while Experimentalist owns the run.
- Use `progress` and `note` only.

### Phase lines (NORMAL verbosity)

Exact wording can be tuned in implementation, but the sequence is:

| When | Call |
| --- | --- |
| Enter `_run` (before work) | `progress(phase="eval author · starting")` |
| Staging / filling templates | `progress(phase="eval author · materializing tasks", completed=..., total=..., unit="task")` as appropriate |
| Trace analysis | `progress(phase="eval author · analyzing traces", completed=..., total=..., unit="trace")` |
| Per failed analysis (optional) | `note(...)` |
| Discover runner | `progress(phase="eval author · discovering runner")` |
| Author metrics | `progress(phase="eval author · authoring metrics")` |
| Validation repair attempt | `progress(phase="eval author · repairing metrics", completed=attempt, total=max)` or `note` |
| Successful finalize / return | `progress(phase="eval author · complete")` |
| Early exit (no trace refs) | emit starting, then `note("no trace refs — nothing to analyze")`, then complete |

Quiet verbosity already suppresses `progress` / `note` inside `RunReporter`; Eval Author does not special-case QUIET beyond passing the shared reporter.

## Error handling

- If Eval Author raises, do **not** emit `complete`; the parent Experimentalist narration continues with its own failure path / logging.
- Reporter methods must not be wrapped in ways that mask real Eval Author errors; only narration failures are swallowed (already inside `RunReporter`).

## Testing

1. **Eval Author unit tests** (new): with a `StringIO` sink + `RunReporter`, drive a thin `_run` path or a test double of phases and assert start, mid-phase, and complete lines appear; assert `reporter=None` emits nothing.
2. **Boundary test**: allowlist update for `nemo_experimentalist_plugin.experimentalist.reporting`.
3. **Call-site**: Experimentalist loop passes `reporter=reporter` into `EvalAuthor(...)`. Existing Experimentalist `test_reporting.py` remains the utility source of truth; no need to re-test reward/delta semantics here.
4. Existing `test_eval_author_run.py` / e2e constructors keep working with the new optional kwarg defaulting to `None`.

## Files to touch

- `plugins/nemo-eval-author/src/nemo_eval_author_plugin/eval_author/agent.py` — accept reporter; emit phases in `_run`
- `plugins/nemo-eval-author/src/nemo_eval_author_plugin/eval_author/run.py` — thread optional `reporter` through `build_eval_author_agent` for signature parity; do not construct a reporter in `run_eval_author` yet
- `plugins/nemo-eval-author/tests/test_plugin_boundary.py` — allowlist `...reporting`
- `plugins/nemo-eval-author/tests/` — new reporter emission tests
- `plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/experimentalist/components/loop.py` — pass parent reporter into `EvalAuthor`

## Success criteria

- An Experimentalist insight-mode run prints Eval Author start, phase progress, and complete lines on the same sink as the rest of the run.
- Standalone `run_eval_author` behavior and output are unchanged.
- Plugin boundary allowlist grows by exactly one intentional module (`reporting`).
- Narration cannot break an Eval Author run.
