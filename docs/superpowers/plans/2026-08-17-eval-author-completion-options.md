# Eval Author completion options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `CompletionClientOptions` (`reasoning_effort` + `completion_params`) to `nooa_model_client`, and wire Eval Author with default `reasoning_effort="medium"`.

**Architecture:** Options are resolved once at `resolve_model_clients` and baked into each `CompletionClient`. Eval Author builds options from `EvalAuthorConfig`. Other consumers unchanged when options are omitted.

**Tech Stack:** Python, dataclasses, Pydantic, pytest, existing Nooa `CompletionClient` kwargs.

**Spec:** `docs/superpowers/specs/2026-08-17-eval-author-completion-options-design.md`

---

### Task 1: `CompletionClientOptions` + resolve wiring

**Files:**
- Modify: `packages/nemo_platform_plugin/src/nemo_platform_plugin/nooa_model_client.py`
- Modify/Create: `packages/nemo_platform_plugin/tests/test_nooa_model_client.py`

- [ ] Add frozen `CompletionClientOptions`
- [ ] Thread `options` through `_completion_client` / `resolve_model_clients`
- [ ] Merge order: base → `completion_params` → explicit `reasoning_effort` if not None
- [ ] Unit tests for omit / medium / params override / effort wins

### Task 2: Eval Author config + run

**Files:**
- Modify: `plugins/nemo-eval-author/src/nemo_eval_author_plugin/eval_author/models.py`
- Modify: `plugins/nemo-eval-author/src/nemo_eval_author_plugin/eval_author/run.py`
- Modify: `plugins/nemo-eval-author/tests/test_eval_author_run.py`

- [ ] `reasoning_effort: str | None = "medium"`
- [ ] `completion_params: dict[str, Any] = Field(default_factory=dict)`
- [ ] Pass `CompletionClientOptions` into `resolve_model_clients`
- [ ] Test default medium + explicit None + params forwarded (mock resolve)

### Task 3: Verify

- [ ] `uv run --frozen pytest packages/nemo_platform_plugin/tests/test_nooa_model_client.py plugins/nemo-eval-author/tests/test_eval_author_run.py -q`
- [ ] Carry design doc onto the branch if missing
