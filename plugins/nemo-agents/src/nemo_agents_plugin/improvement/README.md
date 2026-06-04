# `improvement/` — agent-improvement workflow (POC)

This subpackage implements the agent-improvement workflow described in the
[design plan PR](https://github.com/NVIDIA-NeMo/nemo-platform/pull/141): run
containerized eval suites against an agent, analyze failures, and optimize
agent skills via a coding agent (Claude).

**Replaces `tools/self_improve/` from PR #38.** The standalone `nmp-eval-run`
/ `nmp-eval-analyze` / `nmp-self-improve` CLI tools are subsumed by these
plugin commands; the canonical NeMo self-improvement config lives at
`.agent-improver.yml` in the repo root and is invoked as:

```bash
nemo agents optimize-skills run --spec-file .agent-improver.yml
```

**New here?** Read [`GETTING_STARTED.md`](./GETTING_STARTED.md) for the
end-to-end walkthrough (from "I have an agent + Harbor evals" to
"the loop just optimized my skills"). For the annotated config template,
see [`examples/agent-improver.example.yml`](../../../examples/agent-improver.example.yml).

The plugin also ships the [`nemo-agent-skills-optimization`](../../../skills/nemo-agent-skills-optimization/SKILL.md)
skill (registered via `nemo.skills`), so a Claude session in any repo
with this plugin installed knows how to drive the workflow when the user
asks to "improve the agent" / "run agent evals" / etc.

## CLI surface

Three subcommands extend `nemo agents`, each registered as a standard
NemoJob with `run` / `submit` / `explain` verbs:

```bash
# Run locally, in-process — daily use
nemo agents evaluate-suite run --spec-file ./.agent-improver.yml
nemo agents analyze         run --spec-file ./.agent-improver.yml
nemo agents optimize-skills run --spec-file ./.agent-improver.yml

# Submit to a cluster
nemo agents optimize-skills submit --spec-file ./.agent-improver.yml --cluster <url>

# Inspect the spec schema for a job
nemo agents optimize-skills explain
```

You can pass the spec inline as JSON instead of a file:

```bash
nemo agents analyze run --spec '{"batch": "./runs/batch-2026-04-28", "format": "md"}'
```

For one-off overrides, edit the YAML in place (or copy it and pass the
copy via `--spec-file`); `--spec` JSON is ignored when `--spec-file` is set.

Example `.agent-improver.yml`:

```yaml
# All fields match OptimizeSkillsConfig (Pydantic schema).
evals: ./tests/agentic
agent: .
skills_path: .agents/skills

iterations: 3
concurrency: 4
repeats: 3              # >1 enables median aggregation for noise reduction

# filter_glob: "auth-*"  # optional: scope to subset of evals
# initial_batch: ./runs/batch-2026-04-28  # skip the initial run

full_verification: false
open_pr: false          # set true to auto-open a GitLab MR via glab
```

## Layout

```
improvement/
├── models.py                      # shared dataclasses (ported from PR #38)
├── baselines.py                   # baseline tracking with history
├── loop.py                        # optimize-skills orchestration
├── worktree.py                    # git worktree helpers
├── runners/
│   ├── base.py                    # Runner protocol
│   ├── detect.py                  # auto-detection by marker file
│   ├── harbor.py                  # Harbor runner (Claude Code agent)
│   ├── nat.py                     # NAT runner (NeMo Agent Toolkit agent)
│   └── _harbor_*.py               # internal Harbor implementation
├── traces/
│   ├── base.py                    # TraceParser protocol + TraceSummary
│   ├── claude_code.py             # Claude Code session.jsonl primitives
│   └── claude_code_parser.py      # ClaudeCodeTraceParser — the only impl today
├── analysis/
│   ├── mechanical.py              # pure-Python clustering, regressions
│   └── llm.py                     # LLM hypothesis generation
├── strategies/
│   ├── base.py                    # ImprovementStrategy protocol
│   └── skills.py                  # the v0 strategy
└── coding_agents/
    ├── base.py                    # CodingAgent protocol
    └── claude.py                  # the v0 coding agent (codex is named v1)
```

## v0 limitations

- **Trace-derived analysis is Claude-Code-only today.** ``TraceParser``
  is the protocol; ``ClaudeCodeTraceParser`` (session.jsonl → typed tool
  calls, errors, skills) is the only implementation today. Callers
  pick a parser at the call site — the loop always uses Claude Code (it
  enforces a harbor-only / claude-code-only guard upstream); ``analyze-job``
  defaults to Claude Code and runs mechanical-only on batches whose
  traces aren't claude-code-shaped. New parsers plug into the protocol
  and callers choose them at invocation. NAT-hosted agents emit
  ``IntermediateStep`` records via the ``nemo_files`` telemetry exporter
  today; a parser for those records is the planned next implementation,
  gated on plumbing ``workspace`` / ``agent_name`` / ``run_id`` through
  ``EvalResult``.
- **Variance.** Default verdicts are single-trial (PR #38 thresholds: ±5%
  duration, ±10% tokens). Pass `--repeats N` for median aggregation.
- **Coding agent is hardcoded to Claude.** Codex is the named v1 deliverable;
  the `CodingAgent` protocol is in place so it slots in as a sibling file.
- **Verified diff producer by default.** Pass `--open-pr` to auto-open a
  GitLab MR via `glab` on improvement.

See [PR #141](https://github.com/NVIDIA-NeMo/nemo-platform/pull/141) for the full
design rationale.

## What was ported from PR #38

The bulk of the v0 logic — eval discovery, parallel Harbor execution, result
parsing, baseline tracking, mechanical analyzer, LLM analyzer, the
optimize-skills loop, hypothesis selection, verdict computation — is ported
verbatim from `tools/self_improve/` in PR #38, with import-path renames and
hardcoded paths generalized behind `--evals` / `--agent` / `--skills-path`.

The new code in this POC:
- `runners/{base,nat,detect}.py` — the runner protocol, NAT runner (subprocess
  wrapper around `tests/agentic-use/nat_runner.py`), auto-detect
- `strategies/{base,skills}.py` — formalized strategy protocol + skills impl
- `coding_agents/{base,claude}.py` — `CodingAgent` protocol + Claude wrapper
- `traces/{base,claude_code_parser}.py` — `TraceParser` protocol + `ClaudeCodeTraceParser` (the only impl today)
- New NemoJobs: `evaluate-suite`, `analyze`, `optimize-skills`
