# Memory triage example

Drive the memory-triage council from
[`improvement/memory/`](../../src/nemo_agents_plugin/improvement/memory/)
against a `pi-hermes`-style Markdown corpus. Talks to whatever models
the local NeMo Platform IGW exposes via its OpenAI-compatible endpoint.
No direct provider credentials are needed; IGW handles upstream auth.

## Canonical entry point

This subdirectory is the home of the **`nemo agents triage-memory`**
NemoJob (registered under `nemo.jobs` as `agents.triage-memory` by the
plugin's `pyproject.toml`).

```bash
# Lock the Sonnet 4.6 baseline (the gold reference for tuned-model comparison).
nemo agents triage-memory run \
    --spec-file plugins/nemo-agents/examples/memory-triage/baseline-sonnet-4-6.triage-memory.yml

# Inspect the spec schema.
nemo agents triage-memory explain

# Submit to a cluster instead of running locally.
nemo agents triage-memory submit \
    --spec-file <spec>.yml --cluster <cluster-url>
```

## Path or fileset on both input AND output

Both the `corpus` (input) and `output` (artifacts) fields accept either
a local path or a NeMo Platform fileset reference. The dispatch is
automatic and matches the platform's RFC LJ-3 convention:

- Values starting with `.`, `/`, `..`, or `~` are local paths.
- Bare names are fileset references (`fileset-name` resolves under the
  `workspace` field; `workspace/fileset-name` inlines the workspace).
- For `corpus`, the fileset must contain exactly one `.md` file; the
  job refuses ambiguity rather than guessing.
- For `output`, the fileset is auto-created on first use. On a
  successful run both artifacts (`{basename}.json` and `{basename}.md`)
  are uploaded; a failed run skips the upload so the fileset never
  holds a half-finished pair.
- When `output` is omitted entirely, artifacts land in
  `ctx.storage.persistent / 'triage-output'` (the platform-injected
  persistent volume), matching the EvaluateAgent convention.

**Use local paths** when the corpus and output destination live on
the machine the job runs on. See
[`baseline-sonnet-4-6.triage-memory.yml`](baseline-sonnet-4-6.triage-memory.yml).

**Use filesets on both ends** when the job runs somewhere you can't
easily scp to (omnistation, remote scheduler, etc.). The corpus is
pulled from one fileset; the artifacts are pushed to another. No
host-local directory is required at any point. See
[`baseline-sonnet-4-6-fileset.triage-memory.yml`](baseline-sonnet-4-6-fileset.triage-memory.yml).

## Quickstart: laptop, local corpus

Platform running (`nemo services run`), corpus on disk:

```bash
nemo agents triage-memory run \
    --spec-file plugins/nemo-agents/examples/memory-triage/baseline-sonnet-4-6.triage-memory.yml
```

## Quickstart: omnistation, filesets on both ends

Avoids needing to know the omnistation's filesystem layout entirely.
From your laptop, upload the corpus to a fileset (auto-creates the
fileset on first upload):

```bash
nemo files upload --fileset user-memory-corpus \
    ~/.pi/agent/claude-session-replays/CONSOLIDATED/USER.md
```

Then on the omnistation (inside your tssh session):

```bash
cd ~/projects/nvidia/nemo-platform
git fetch origin && git checkout memory-triage/md && git pull && uv sync

nemo agents triage-memory run \
    --spec-file plugins/nemo-agents/examples/memory-triage/baseline-sonnet-4-6-fileset.triage-memory.yml
```

The spec points `output` at the `memory-triage-artifacts` fileset; the
job auto-creates it and uploads `baseline-sonnet-4-6-user.{json,md}` on
success. Back on the laptop, pull the artifacts when ready:

```bash
nemo files download --fileset memory-triage-artifacts --local-path ./artifacts
```

## Raw driver (debugging mode)

[`run_triage.py`](run_triage.py) is the pre-NemoJob driver. It does the
same thing as `nemo agents triage-memory run` but takes CLI flags
instead of a YAML spec, and prints per-judge calibration to stdout.
Useful when iterating on judge models or prompts; the NemoJob is the
canonical entry point for everything else.

```bash
uv run --frozen python plugins/nemo-agents/examples/memory-triage/run_triage.py \
    --judge azure-anthropic-claude-sonnet-4-6 \
    --max-entries 3 --basename pilot
```

The raw driver does **not** support fileset references on either end.
Use local paths or `nemo files download` to stage inputs first, and
`nemo files upload` to ship the artifacts afterward.

## Spec field reference

| field | type | default | notes |
| --- | --- | --- | --- |
| `corpus` | str | required | Local path OR fileset reference (auto-dispatch). |
| `workspace` | str | `"default"` | Default workspace for unqualified fileset refs (both corpus and output). |
| `judges` | list[str] | required | Judge model ids from `nemo models list`. First is reference. |
| `store_name` | str | `"pi-hermes:memory"` | Recorded on every emitted proposal. |
| `output` | str? | `None` | Local path OR fileset reference for artifacts. None falls back to `ctx.storage.persistent / 'triage-output'`. |
| `basename` | str | `"triage"` | Filename pair basename. |
| `max_tokens` | int | `4096` | Per-judge budget. Floor: 512. Bump to 6144 for heavy reasoners. |
| `max_entries` | int? | `None` | Cap entries processed (for pilot runs). |
| `timeout_sec` | float | `180` | Per-request timeout. |
| `igw_base_url` | str? | auto | Override IGW URL. Default: resolved via `nemo inference get-url`. |
| `igw_api_key` | str | `"not-needed"` | IGW auth. Default works because IGW handles upstream auth. |

## Operational notes

- Reasoning models (Nemotron-Nano, Kimi, Super v1-5) can burn 500-1500
  completion tokens on internal reasoning before emitting JSON. The
  default `max_tokens=4096` is safe; bump to 6144 if you see empty-content
  errors from Kimi or Super.
- Per-entry wallclock is dominated by the slowest judge. With Sonnet
  alone, a 71-entry USER.md run is ~12 minutes; adding a heavy
  Nemotron judge can push it to 30-50 minutes.
- Output JSON is structured and is the input for the eventual
  baseline-vs-candidate eval primitive (Phase 2 / bd `mdubrinsky-7au.6`).
  Markdown is human-reviewable, organized by verdict bucket.

## See also

- [`DESIGN.md`](../../src/nemo_agents_plugin/improvement/memory/DESIGN.md) — Phase 0 contract, council slots, phasing.
- [`RESULTS.md`](../../src/nemo_agents_plugin/improvement/memory/RESULTS.md) — Phase 1 smoke results, calibration findings, v1-v4 evolution.
- bd `mdubrinsky-7au` — parent issue.
- bd `mdubrinsky-7au.6` — eval-loop work (baseline-vs-candidate diff primitive).
- bd `mdubrinsky-7au.3` — judge fine-tune corpus from the v1 disagreement set.
