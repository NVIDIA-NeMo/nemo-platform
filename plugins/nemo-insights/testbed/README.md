# testbed — insights analyst test runner (maintainer tooling)

Runs the Insights analyst against registered **subjects** and emits Insights. Think
"pytest for the analysis loop." This is dev tooling — it *drives* `nemo insights`;
it is not the product CLI and is not shipped in the wheel.

```bash
uv run python -m testbed analyze tau2-airline         # reproducible default: restore the pinned state locally, then analyze
uv run python -m testbed list
uv run python -m testbed doctor                       # fresh clone? run this first
uv run python -m testbed run tau2-airline             # produce: tau2 -> ingest -> record the run (expensive, once)
uv run python -m testbed analyze tau2-airline --live  # analyze the recorded run's live traces (no restore)
uv run python -m testbed analyze nvq --live           # intake: analyze existing live traces
uv run python -m testbed snapshot tau2-airline        # export the subject's workspaces (read API) into a portable bundle
uv run python -m testbed restore --state state-v7     # re-ingest a state bundle into fixture workspaces (additive, idempotent)
uv run python -m testbed restore --state state-vN --into WORKSPACE
```

Bare `analyze <subject>` is a fully reproducible run: pinned data (the subject's
`state.lock` entry) restored onto the local platform, analyzed with fresh
insights (no prior seed). Every deviation is one explicit flag:

- `--state <state-vN|FILE>` — another published state, or a local bundle file
  (mutually exclusive with `--live`).
- `--live [--since S]` — skip the restore and read the platform's live traces
  (`--since` applies to `analyze --live` and to `snapshot`; pinned/`--state`
  analysis derives its bound from the bundle manifest).
- `--update-insights` — run against the existing local insights (prod-like update flow:
  updates them and adds new ones); default is a fresh start with priors moved to backup.
  Valid in every mode.
- `--base URL` — the one platform flag, on every platform-touching command.
  Fixture targets (restore, roundtrip, pinned/`--state` analyze) default to
  `http://localhost:8080`; live targets (`run`, `analyze --live`, snapshot's
  source) default to the stanza's `base_url`. publish's guard runs wherever
  its `--base` points — no default; `--no-verify` skips it out loud.
- `--set KEY=VALUE` — one-off config override (`run`/`analyze` only,
  repeatable). Values take the stanza key's type — bool keys accept only
  `true`/`false`, so `--set include_rewards=false` is really false; keys new
  to the stanza stay strings. If you keep reaching for it, move the value
  into `testbeds.toml`. `--set` applies after `--base`, so `--set base_url=…` wins when both are given.

`run` produces traces and records the run to `testbed/tmp/<subject>.run.json`;
`analyze --live` then analyzes it — for a `benchmark` it re-uses the last recorded
run (no tau2 re-run), for an `intake` subject it analyzes the configured agent.
Iterate on insight generation by re-running `analyze` as often as you like; `run`
again only when you want fresh traces. (A benchmark `analyze --live` follows the
base_url recorded at `run` time, so set `--base` on `run`.)

## Breaking changes (2026-07-07)

- **Deleted flags:** `--pinned` (it's the default), `--latest` (release-latest
  is cross-subject and unsafe under per-subject pins), `--ref` and its `""`
  sentinel, analyze's `--from` (folded into `--state FILE`), `--local`
  everywhere (localhost is the default wherever a fixture is the target;
  `--base` overrides).
- **Fresh by default:** the old seed flag (`none|keep`) is gone — the seed flag became
  `--update-insights` (the not-fresh flow), and bundles no longer carry insight
  YAMLs at all (pure data fixtures; restore seeds run records only).
- **CI:** the state-ref input is renamed `state` (empty = each subject's
  `state.lock` pin); the seed input is deleted (runners start clean — CI is
  inherently fresh).
- **The `insights` command alias is gone** — one name: `analyze`.

## State bundles

Immutable per-subject fixtures on the `testbed-state` GitHub release, pinned in
`testbed/state.lock` — analyst changes get measured against fixed data.

The assets currently live in `NVIDIA-dev/NeMo-Optimizer`. Release operations
target that repository explicitly; set `TESTBED_STATE_REPO=owner/repository` to
use another fixture home. The `gh` token must be able to read that repository
for restore/analyze and write releases there for local publish. A token scoped
only to the Platform repository cannot access the default internal fixture
home. Platform CI uses the least-privilege `TESTBED_STATE_GH_READ_TOKEN`
secret; automated publishing remains in the canonical fixture repository so
two repositories cannot race to mint the same version.

Which file do I touch?

| Surface              | Owns                                          |
| -------------------- | --------------------------------------------- |
| `testbeds.toml`      | what a subject is                             |
| `testbed/state.lock` | which data version analysis runs against      |
| flags                | this invocation only                          |
| `testbed/.env`       | secrets                                       |
| CI inputs            | 1:1 flag mirror                               |

**Analyze against the pinned fixture (the everyday loop, and the default):**

```bash
uv run python -m testbed analyze tau2-airline
```

Downloads the subject's pinned state (its line under `[subjects]` in
`testbed/state.lock`; a missing line is a hard error — no latest fallback),
re-ingests it into fixture workspaces (`tau2-airline-state-v6`) on the local
platform, and runs the Analyst live. Re-runs skip the ingest (idempotent).
`--state state-vN` / `--state FILE` select another state; `--base URL`
retargets the restore; `--update-insights` seeds the analyst with your local
prior insights (default: fresh — the prior file is moved aside first). `since`
is derived from the bundle's manifest, so old spans can't hide behind the read
API's 30-day default lookback. (`--live` skips the restore entirely and
analyzes the platform's live traces, with `since` from `--since`, the stanza,
or a 30d default — in that order; the effective bound is always printed.)

**Publish a verified candidate from a maintainer machine:**

```bash
uv run python -m testbed snapshot nvq -o testbed/tmp/nvq.tar.zst
uv run python -m testbed publish testbed/tmp/nvq.tar.zst --base http://localhost:8080 --reason "why this exists"
```

`snapshot` drains the subject's workspaces (benchmark subjects: realistic +
`-oracle` twin) into JSONL + manifest — no ClickHouse, no Docker. `publish`
refuses to mint unverified: `--base` runs the round-trip fidelity guard there
first (re-ingest into scratch workspaces → re-export → doc diff), or pass
`--no-verify` only after separately confirming the guard passed (for example,
by checking that the CI `produce` job's round-trip step was green before using
its downloaded candidate artifact).
Then pin it: add `nvq = "state-vN"` under `[subjects]` in `testbed/state.lock`.

**Restore without analyzing:** `uv run python -m testbed restore (FILE | --state state-v7) [--base URL]`.
To restore a one-workspace bundle directly into a named workspace, use
`uv run python -m testbed restore --state state-vN --into WORKSPACE`. `--into`
accepts only one-workspace bundles and requires a fresh, empty target
workspace. The default restore remains fixture-scoped and idempotent.

What restore touches:

- **Platform, default fixture restore:** additive, idempotent, and healing.
  Ingests into `<ws>-<ref>` (`<ws>-<sha256[:8]>` for local files).
  Per-collection guard: counts match → skip, empty → ingest, supported
  interrupted states → heal, anything else → hard error.
- **Platform, direct `--into` restore:** writes to the exact named workspace
  only after proving all three collections are empty. It is fresh-target-only,
  and rerunning into the now-populated workspace fails rather than acting
  idempotently.
- **Local `testbed/tmp`: run records seeded.** The bundle's run records
  replace yours — clobbered files are moved to `testbed/tmp/backup-<timestamp>/`
  first, and only the bundle's own subjects' files are ever touched. Bundles
  carry no insight YAMLs (fresh vs not-fresh is purely local state; see
  `--update-insights`).
- Accepted losses: annotation/evaluator-result `created_at`/`created_by` are
  server-stamped at restore (the write APIs reject client values); a running
  platform is required to analyze.
- Legacy `state-v1..v5` tars were pruned from the release (the v4 corpus lives
  on as `state-v6`); a stray local copy restores only from a checkout
  predating the v6 migration.
- Client-side re-ingest is a stopgap for the platform team's RBAC-scoped
  server-side export/import endpoint; when that ships, snapshot/restore
  collapse to two API calls each.

Each benchmark `run` reuses **two stable workspaces** per subject — `<workspace>`
(the realistic, oracle-free workspace the Analyst evaluates, blind) and
`<workspace>-oracle` (the answer key + scores, for the UI). The stanza's `workspace`
is that base name. Runs no longer mint a workspace each. Run isolation comes from
the per-span `nemo.experiment.id=<run-id>` tag plus the Analyst's `evaluation_id`
filter (which AND-pins every span read to that run) — that is what scopes the
analysis. The matching **Experiment** entity registered on the `-oracle` workspace
is metadata for the UI (run-picker + leaderboard), not the scoping mechanism. So
workspaces stop accumulating and each run reads only its own traces. (Old runs'
spans age out by Intake retention; the Experiment entities are cheap and
soft-deletable.)

Keys come from `testbed/.env` (see below), so the commands need no inline env. **`doctor`**
prints a per-subject readiness checklist — on a fresh clone, run it first and it tells you
exactly what to install/set (`✓ ready` or `✗ needs: …`).

Subjects live in `testbeds.toml` — one table per subject, keyed by `type`:
- `type = "intake"` — analyze an agent's existing Intake traces (config: `agent`, `workspace`, `base_url`, optional `since`).
- `type = "benchmark"` — run a benchmark to produce traces, ingest them into Intake, then analyze (config: `domain`, `base_url`, `workspace`, `agent_llm`, `user_llm`, `task_split_name`, `num_trials`, `max_concurrency`, `seed`, optional `num_tasks`/`timeout`/`include_rewards`).

`--since` (analyze `--live`, snapshot) accepts `Nd`/`Nh`/`Nm` (days/hours/minutes)
or an ISO date; `--since ''` means no lower bound (the epoch). Insights are
written to `testbed/tmp/insights_<name>.yaml`.

## Config split: secrets in `.env`, everything else in `testbeds.toml`

On startup the CLI auto-loads `testbed/.env` (gitignored) as `KEY=VALUE` lines. Keep
**only secrets/endpoints** there — `INFERENCE_API_KEY` (analyst) and
`OPENAI_API_KEY`/`OPENAI_API_BASE` (the proxy litellm uses for the benchmark sim LLMs).
Real shell environment variables override the file. Everything non-secret (paths, models,
ports, run sizes) lives in the subject's `testbeds.toml` stanza.

## Benchmark prereqs (tau2-airline / tau2-retail)

Clone tau2-bench as a sibling of this repo and install it once:

```bash
git clone https://github.com/sierra-research/tau2-bench   # sibling of nemo-insights plugin
cd tau2-bench && uv sync          # Python 3.12+; installs the `tau2` CLI into .venv
uv run tau2 check-data            # verify the shipped domain data
```

The `[tau2-airline]` and `[tau2-retail]` stanzas then need (all non-secret, committed):
- `tau2_repo` — the checkout above; relative to this repo's root (`../tau2-bench`, the
  sibling default) or absolute. Both the CLI (`<repo>/.venv/bin/tau2`) and the data dir
  (`<repo>/data`) are derived from it (`tau2_bin`/`tau2_data_dir` override if needed).
- `agent_llm`/`user_llm` — models your proxy key serves (`GET {OPENAI_API_BASE}/v1/models`);
  default `openai/nvidia/nvidia/nemotron-3-super-v3`.
- `base_url` — a reachable NeMo Platform (default `http://localhost:8080`).

With `testbed/.env` holding the three secrets, run:

```bash
uv run python -m testbed run tau2-airline
uv run python -m testbed analyze tau2-airline --live

uv run python -m testbed run tau2-retail
uv run python -m testbed analyze tau2-retail --live
```

## CI (`.github/workflows/insights-testbed.yml`)

CI runs the testbed against a **self-contained platform inside the job**
(ClickHouse + `auth,entities,intake` from a `nemo-platform` checkout) — the
freeplay remote is not reachable from GitHub-hosted runners. The workflow's
steps are thin wrappers over the same CLI you run locally (`testbed restore`
/ `analyze` / `snapshot` / `roundtrip`); the shared
helpers live in `testbed/eval/` (stdlib-only `plan.py`/`prep.py`/
`run_subjects.py` run on the bare runner before `uv sync`). Dispatch inputs
mirror the CLI flags 1:1 (`mode`, `subjects`, `state`, `num_tasks`,
`num_trials`, `reason`). Three modes, all validated **green
on real GitHub Actions** (branch `testbed-ci-insights`; API-export pipeline:
stack-check
[run 28880210091](https://github.com/NVIDIA-dev/NeMo-Optimizer/actions/runs/28880210091),
analyze vs `state-v6`
[run 28880474684](https://github.com/NVIDIA-dev/NeMo-Optimizer/actions/runs/28880474684)
(966 spans re-ingested into `<ws>-state-v6` fixtures), produce smoke ×2 tasks
[run 28881101719](https://github.com/NVIDIA-dev/NeMo-Optimizer/actions/runs/28881101719)
— round-trip guard green in CI and candidate uploaded for inspection):

Configure the `insights-testbed` GitHub environment with required reviewers
and self-review prevention. Store `NVIDIA_INFERENCE_KEY`,
`NVIDIA_INFERENCE_URL`, and `TESTBED_STATE_GH_READ_TOKEN` exclusively as
secrets in that environment; do not retain repository- or organization-level
copies that PR workflow edits could access without approval. Set the
`TESTBED_STATE_REPO` repository variable when fixtures live outside the
default `NVIDIA-dev/NeMo-Optimizer` repository.

- `stack-check` — bring the stack up, verify `/ping` + `/health/ready`, exit.
  Cheap CI doctor.
- `produce` — **explicit dispatch only** (hard-gated to `workflow_dispatch`): a
  human generates a candidate when there's a reason — tau2-bench update,
  agent/sim config change, staleness refresh. Never runs from PRs or any
  automatic trigger. Candidates come from the fresh in-job stack (no base restore):
  `run_subjects.py` runs the subjects (`subjects=tau2-airline,...`,
  override size with `num_tasks=`/`num_trials=`; analyze retries absorb
  post-sim rate-limit heat) with `--base http://localhost:8080`, then
  `testbed snapshot` exports an **unminted candidate bundle** that is always
  uploaded as workflow artifact `state-candidate-<run_id>-<attempt>` (even on
  failure), and `testbed roundtrip` proves the candidate re-ingests with full
  read-API fidelity. While the fixture release remains in NeMo Optimizer, this
  workflow stops at the candidate artifact; the canonical repository remains
  the only automated publisher. A maintainer can download the candidate and
  run `testbed publish` locally only after inspecting it and confirming that
  the workflow's round-trip step passed.
- `analyze` — `testbed analyze "$SUBJECT" ${STATE:+--state "$STATE"}
  --summary-md "$GITHUB_STEP_SUMMARY"`: an empty `state` input means bare
  analyze — each subject's own pin under `[subjects]` in `testbed/state.lock`
  (a subject without an entry fails loudly — no latest fallback); a non-empty
  ref overrides the lock for **all** subjects in the run. The state is
  re-ingested into its fixture workspaces (`<ws>-<ref>`) on the in-job
  platform, insights regenerate and upload as artifact
  `insights-<subject>-<run_id>-<attempt>` (a `### analyze @ <ref> (<subject>)`
  line is appended to the step summary right after the restore, ahead of the
  insights themselves). Runners start clean, so CI is inherently fresh — no
  priors, no knob. Re-running analyze against a byte-identical state and
  diffing the resulting Insights is the reliability signal ("pass^k for
  insights") this pipeline exists to surface, not noise to suppress.

**One analysis run per PR:** applying the `run-insights` label runs
`mode=analyze` against `tau2-airline` at the current PR head. Later commits do
not rerun it on `synchronize`, avoiding repeated inference spend. Remove and
reapply the label to request an explicit rerun.
States are per-produce-dispatch compositions, so subjects pin different
versions — each under `[subjects]` in `testbed/state.lock`; a subject with no
entry errors (add its line after minting a fixture). Lock-bump PRs edit the
subject's line; bump on `main` to advance that subject's shared baseline after
the produced candidate is verified and manually published. The dispatch
`state` input still overrides the lock for **all** subjects in that run.

### Dispatching a run

`workflow_dispatch` (and `gh workflow run`) only becomes available once the
workflow file has landed on the repository's **default branch** — a GitHub
registration requirement (dispatching from a feature branch 404s). After the
merge, verify with `gh workflow run insights-testbed.yml -f mode=stack-check`,
then:

```bash
gh workflow run insights-testbed.yml -f mode=stack-check
gh workflow run insights-testbed.yml -f mode=produce -f subjects=tau2-airline -f num_tasks=2 \
  -f reason="2-task smoke after tau2-bench bump"   # retained when the candidate is published
gh workflow run insights-testbed.yml -f mode=analyze                    # each subject's state.lock pin
gh workflow run insights-testbed.yml -f mode=analyze -f state=state-v6  # explicit override, all subjects
```

### Pre-merge checklist: validating workflow changes from a branch

Because dispatch requires the default branch, workflow changes are validated
from the feature branch with a **temporary push trigger** before merge:

1. Add `push: {branches: [<your-branch>]}` plus, for each dispatch input a
   round needs, a temporary event-scoped fallback arm in the workflow env —
   `inputs.x`, falling back on push events to a repo variable
   (`gh variable set TESTBED_X --body ...`) — every arm marked `# TEMPORARY`.
   produce's dispatch-only event gate needs a temporary
   `|| github.event_name == 'push'` arm. The Platform workflow has no publish
   step, so validation runs cannot mint fixture refs.
2. Drive rounds by setting the variables (e.g. `gh variable set TESTBED_MODE
   --body produce`) plus a trivial trigger commit; watch `gh run list` /
   `gh run view --log-failed` (runs take 5–20 min).
3. Cleanup before merge: remove the push trigger and every `TEMPORARY` arm,
   `gh variable delete` each temporary variable, and confirm the PR's
   `pull_request` run all-skips without the `run-insights` label.

### Public-runner constraints

GitHub-hosted runners are unauthenticated and this org allowlists Actions by
pinned SHA, which shaped the composites in `.github/actions/`:
- `uv` is curl-installed and pinned to `0.9.14` — the org's allowlist pins
  `astral-sh/setup-uv` to specific commit SHAs (no `@v*` wildcard), and
  `nemo-platform`'s `pyproject.toml` requires `uv >=0.9.14,<0.10.0` (latest
  `0.11.x` is rejected).

### State model

Bundles are immutable `state-v<N>` tarballs — `export/<workspace>/*.jsonl`
(spans, annotations, evaluator results), `tmp/` (run records only — insights
never travel in bundles), `manifest.json` (per-workspace counts, span time
bounds, source URL, platform build, CI lineage) — stored both as a workflow
artifact and as an asset on the `testbed-state` release. Versions are
**minted at publish time** (candidate → round-trip guard → mint): only a
successful guard's publish claims the next `state-v<N>` and prepends its
catalog row, so failed runs can never burn or collide on a version number.
Restores are additive re-ingests into `<ws>-<ref>` fixture workspaces, so a
bundle never perturbs anything else on the target platform; ClickHouse's TTL
merges are stopped on every CI stack start so restored spans don't age out
mid-run. `testbed/state.lock` pins, per subject (`[subjects]` table), the
version `analyze` uses by default (currently `tau2-airline = "state-v6"`, the
first API-export bundle, and `nvq = "state-v7"`) — a subject without an entry
hard-errors rather than falling back to latest. Bump a subject's line
deliberately after a mint you want as its new shared baseline, or override
per-run with the dispatch `state` input (applies to every subject in the run;
locally: `analyze <subject> --state state-vN`).

Secrets: the workflow uses `TESTBED_STATE_GH_READ_TOKEN`, a least-privilege
GitHub App/PAT credential with release-read access to `TESTBED_STATE_REPO`,
plus `NVIDIA_INFERENCE_KEY` and `NVIDIA_INFERENCE_URL`. The latter are exposed
under the `INFERENCE_API_KEY` and OpenAI-compatible environment names expected
by the analyst and litellm/tau2. The analyst and tau2 sim LLMs need no VPN and
work on public runners.
