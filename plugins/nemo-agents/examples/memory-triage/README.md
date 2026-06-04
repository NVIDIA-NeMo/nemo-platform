# Memory triage example

Drive the council orchestration from
[`improvement/memory/`](../../src/nemo_agents_plugin/improvement/memory/)
against a real `pi-hermes`-style Markdown corpus. Talks to whatever
models the local NeMo Platform IGW exposes via its OpenAI-compatible
endpoint, so no direct provider credentials are needed.

This is the **Phase 1 / 1.5 driver**. Phase 2
(bd `mdubrinsky-7au.6`) turns this into a proper
`nemo agents triage-memory` NemoJob; the CLI surface and config schema
will replace this script.

## Quickstart

Local laptop, platform up (`nemo services run`):

```bash
# Sonnet 4.6-only baseline (the gold reference for tuned-model comparison)
uv run --frozen python plugins/nemo-agents/examples/memory-triage/run_triage.py \
    --judge azure-anthropic-claude-sonnet-4-6 \
    --basename baseline-sonnet-4-6-user \
    --output-dir plugins/nemo-agents/src/nemo_agents_plugin/improvement/memory/phase1-smoke/baselines/

# 3-judge research smoke (first --judge is the reference for aggregation)
uv run --frozen python plugins/nemo-agents/examples/memory-triage/run_triage.py \
    --judge azure-anthropic-claude-sonnet-4-6 \
    --judge nvidia-nemotron-3-nano-30b-a3b \
    --judge nvidia-llama-3-3-nemotron-super-49b-v1-5 \
    --basename research-smoke-v5
```

## Running on omnistation

Prerequisite checks (run on the omnistation, not your laptop):

```bash
# 1. Platform is up.
nemo services run     # if not already running
nemo inference get-url

# 2. The PoC USER corpus is reachable. Either scp from your laptop:
#    scp ~/.pi/agent/claude-session-replays/CONSOLIDATED/USER.md \
#        omnistation:~/.pi/agent/claude-session-replays/CONSOLIDATED/USER.md
#    Or pass --corpus to point at wherever you put it.

# 3. The memory-triage branch is checked out and the plugin is reinstalled.
cd ~/projects/nvidia/nemo-platform
git fetch origin
git checkout memory-triage/md
git pull
uv sync --reinstall-package nemo-agents-plugin

# 4. Baseline run.
uv run --frozen python plugins/nemo-agents/examples/memory-triage/run_triage.py \
    --judge azure-anthropic-claude-sonnet-4-6 \
    --basename baseline-sonnet-4-6-user \
    --output-dir plugins/nemo-agents/src/nemo_agents_plugin/improvement/memory/phase1-smoke/baselines/
```

## CLI reference

```
--judge MODEL              Judge model id from `nemo models list`. Repeat for council.
                           First --judge is the reference model for aggregation.
--corpus PATH              Path to the consolidated USER.md / MEMORY.md / failures.md.
                           Default: ~/.pi/agent/claude-session-replays/CONSOLIDATED/USER.md
--store-name NAME          Store name recorded on every proposal.
                           Default: pi-hermes:CONSOLIDATED:user
--output-dir DIR           Where to write {basename}.json + {basename}.md.
                           Default: ./output/
--basename NAME            Filename pair basename. Default: triage
--max-tokens N             Per-call max_tokens. Default: 4096 (reasoning models need >=2048)
--max-entries N            Cap entries processed (for pilot runs).
--api-key KEY              IGW API key. Default: "not-needed" (IGW handles upstream auth).
--timeout SECS             Per-request timeout. Default: 180
```

## Operational notes

- Reasoning models (Nemotron-Nano, Kimi, Super v1-5) can burn 500-1500
  completion tokens on internal reasoning before emitting JSON output.
  `--max-tokens 4096` is the safe default; bump to 6144 if Kimi or
  Super start surfacing empty-content errors.
- The first --judge is the reference model. The aggregator picks
  refined_text / merge_with / justification from this judge when it
  agrees with the council majority.
- Output JSON is structured (machine-readable) and is the input for
  the eventual baseline-vs-candidate eval primitive (Phase 2 /
  `mdubrinsky-7au.6`). The Markdown is human-reviewable, organized
  by verdict bucket.

## Cost / wallclock guide (USER.md, 71 entries)

Wallclock is dominated by the slowest judge per entry (per-entry
parallel). Approximate numbers from local laptop + IGW routing:

| council | wallclock | notes |
| --- | ---: | --- |
| Sonnet 4.6 alone | ~15 min | the baseline; fastest single judge |
| Sonnet 4.6 + 1 Nemotron | ~25-30 min | depends on Nemotron tier |
| 3-judge with Super v1-5 | ~45-50 min | Super is the long pole |
| Sonnet 4.6 + Nano-3 | ~20-25 min | dense Nano is moderate latency |

Token costs are trivial at single-corpus scale (<$5 per full run on
Sonnet, near-free on Nemotron via inference-api). Cost matters when
this becomes a per-iteration eval loop running daily; the whole
point of getting a tuned Nemotron is to make that loop free.

## See also

- [`DESIGN.md`](../../src/nemo_agents_plugin/improvement/memory/DESIGN.md) — Phase 0 contract, council slots, phasing
- [`RESULTS.md`](../../src/nemo_agents_plugin/improvement/memory/RESULTS.md) — Phase 1 smoke results, calibration findings, v1-v4 evolution
- bd `mdubrinsky-7au` — parent issue
- bd `mdubrinsky-7au.6` — eval-loop work (this script's successor)
- bd `mdubrinsky-7au.3` — judge fine-tune corpus from the v1 disagreement set
