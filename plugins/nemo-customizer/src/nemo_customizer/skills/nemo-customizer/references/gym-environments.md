<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

<!-- NeMo Gym environment packaging for GRPO. Job JSON: `hyperparameters-rl.md`. Prompt rows: `dataset-formats.md` § NeMo-RL (GRPO). -->

# NeMo Gym environments for GRPO

GRPO scores sampled responses against an **environment** — code that runs a rollout and returns a reward. The platform takes that environment as a **FileSet**, and the prompts as a **separate** FileSet. This file covers what a valid environment package looks like in all three formats, and how to get from whatever the user has today to one of them.

**Two FileSets, never one.** The environment package holds code and config; the dataset holds prompt rows. Validation **rejects any `.jsonl` inside the environment package** (`validate_manifest_against_listing`), so a Gym config that points at an in-tree `jsonl_fpath` — which is how environments are shipped in the Gym source tree — will not work here unchanged. Prompts come from the dataset FileSet.

```
environment FileSet (purpose=environment)   dataset FileSet (purpose=dataset)
  nemo-environment.yaml   ← manifest          training.jsonl    ← required
  configs/ or server dirs                     validation.jsonl  ← optional
  wheels/                 ← 2 of 3 formats
```

Job JSON then references both as strings:

```json
{ "environment": "default/<env-fileset>", "dataset": "default/<dataset-fileset>" }
```

## Pick a format

Source of truth: `services/rl/src/nmp/rl/schemas/environment.py`.

| The user has… | Format | Ships wheels? | `config_paths` must live under |
|---|---|---|---|
| An environment already in the NeMo Gym source tree, or one written against Gym's server layout | **`native-v1`** | No | `responses_api_agents/`, `resources_servers/`, `responses_api_models/` |
| A Prime Intellect hub env, or any `verifiers` environment installable as a wheel | **`adapter-wheels-v1`** | **Yes** | `configs/` |
| Their own environment code that must ship as an installable package, with no `verifiers` harness | **`wheels-v1`** | **Yes** | anywhere in the package |

Decision shortcut: **is there a `verifiers` environment?** → `adapter-wheels-v1` (and use the converter, below). **Is the code already a Gym server tree?** → `native-v1`. **Otherwise** → `wheels-v1`.

`adapter-wheels-v1` is the best-supported path — it is what the bundled converter emits and what the training image is built to run. Prefer it when the user has a choice.

## The manifest — `nemo-environment.yaml`

Required at the package root in every format. Parsed by `parse_manifest`; unknown keys are **rejected** (`extra="forbid"`).

```yaml
format: adapter-wheels-v1          # or native-v1 / wheels-v1
config_paths:                      # >=1, relative, no "..", no symlinks, must exist
  - configs/policy_model.yaml
  - configs/verifiers_agent.yaml
adapter:                           # adapter-wheels-v1 ONLY
  agent: verifiers_agent
  agent_type: responses_api_agents
  image_config_root: responses_api_agents/verifiers_agent
metadata:
  name: ascii-tree                 # required
  description: ...                 # optional
  hub_id: primeintellect/ascii-tree
  vf_env_id: ascii-tree            # must match every dataset row's vf_env_id
  adapter_agent: verifiers_agent
```

`metadata` is provenance only — nothing in it changes how the environment installs or runs, **except** that `vf_env_id` is what dataset rows are checked against when you validate them.

### Rules every format shares

| Rule | Enforced by |
|---|---|
| `nemo-environment.yaml` at the package root | `load_manifest` |
| At least one `config_paths` entry, each relative and free of `..` | `_ManifestBase` |
| Every `config_paths` entry exists in the package | `validate_manifest_against_listing` |
| No symlinks, and no path escaping the package root | `validate_package_layout` |
| **No `.jsonl` anywhere in the package** | `validate_manifest_against_listing` |
| `wheels/` non-empty and `*.whl`-only (wheels formats) | `offline_wheel_install_required` |

## Path A — an environment already in Gym (`native-v1`)

Use when the user names an environment that ships with NeMo Gym (`resources_servers/<name>/`, `responses_api_agents/<name>/`) or has written one in that layout.

A Gym server directory looks like this, and the package is a **slice of the Gym tree** with its directory structure preserved:

```
resources_servers/example_single_tool_call/
  app.py
  configs/example_single_tool_call.yaml
  requirements.txt
  data/                       ← drop this; .jsonl is rejected
nemo-environment.yaml         ← you add this at the package root
```

```yaml
format: native-v1
config_paths:
  - resources_servers/example_single_tool_call/configs/example_single_tool_call.yaml
metadata:
  name: example-single-tool-call
```

Gym resolves servers **by name** against a component search path, and the platform prepends the package to it (`NEMO_GYM_EXTRA_ROOTS`), so a package entry shadows a built-in with the same name. Dependencies come from Gym's own per-server install — `native-v1` ships **no** `wheels/` and the platform installs nothing for it, so anything the server imports must already be in the training image.

**The dataset caveat bites hardest here.** Gym's own configs point `datasets[].jsonl_fpath` at an in-tree file. That file cannot ship in the package. Either drop the `datasets` block and let the platform's dataset FileSet supply rows, or keep it and accept that the path will not resolve. Prompts must be converted to Gym JSONL rows either way — see `dataset-formats.md` § **NeMo-RL (GRPO)**.

## Path B — a Prime Intellect / verifiers env (`adapter-wheels-v1`)

The supported, automated path. A bundled converter downloads the hub package, vendors its full wheel closure, writes both configs and the manifest, and builds the prompt JSONL.

**Run it on a host with internet.** Training clusters have no hub egress and consume uploaded FileSets only.

```bash
uv run --package nmp-rl pi-to-gym-conversion \
  --hub-id primeintellect/ascii-tree \
  --hub-version 0.1.5 \
  --out-dir ./ascii-tree-pkg \
  --dataset-dir ./ascii-tree-data \
  --validation-fraction 0.1
```

| Flag | Use it for |
|---|---|
| `--hub-id` | Hub slug. Required for conversion. |
| `--hub-version` | **Pin it.** Unset takes whatever the index offers now; a later release can narrow `Requires-Python` and fail the download, or install but not run on the training image's Python. This is what makes a conversion reproducible. |
| `--out-dir` | Environment package output. |
| `--dataset-dir` | Prompt JSONL output. Defaults to a sibling of `--out-dir`. |
| `--vf-env-id` | Override the verifiers load id. Defaults to the hub slug's last segment. |
| `--vf-env-args` | JSON object forwarded to the environment loader. Must be a JSON **object**. |
| `--dataset-size` | Cap rows (`-1` = all). |
| `--validation-fraction` | Split fraction in `[0, 1)`. `0` writes training rows only. |
| `--wheels-dir` | Use pre-vendored wheels instead of downloading. |
| `--upload` | Create both FileSets and upload, in one step. Needs `NMP_BASE_URL`. |
| `--validate-only <dir>` | Check an existing package and exit. Never touches the hub. |

What it writes:

```
ascii-tree-pkg/
  nemo-environment.yaml
  configs/policy_model.yaml       ← points Gym at the job's own vLLM engine
  configs/verifiers_agent.yaml    ← vf_env_id, vf_env_args, max_tokens, temperature
  wheels/*.whl                    ← resolved closure
ascii-tree-data/
  training.jsonl
  validation.jsonl                ← only with --validation-fraction > 0
```

**`adapter.agent` must be on the image allowlist.** The package ships config and wheels; the agent harness itself comes from the training image. Today the allowlist is exactly one entry — `verifiers_agent` (`IMAGE_ADAPTER_ALLOWLIST`). Anything else is rejected at validation, so a user who wants a different harness needs `wheels-v1` or `native-v1`.

**Why two configs.** `verifiers_agent.yaml` references a model server named `policy_model`; nothing defines that server unless a second config supplies it, and Gym fails the merged-config check with `ServerRefNotFoundError: ... Available responses_api_models: (none)`. `policy_model.yaml` supplies it, interpolating `${policy_base_url}` / `${policy_api_key}` / `${policy_model_name}` against the config NeMo-RL injects at spin-up — which is what points Gym at the vLLM engine the job is already running instead of starting its own.

**`max_tokens` lives in the package, not the job.** `configs/verifiers_agent.yaml` carries `max_tokens` (default 8192), and `verifiers_agent` reads it in preference to the job's `max_new_tokens`. To bound response length for an adapter env, edit this file before uploading — see `hyperparameters-rl.md` § **Known limitation**.

## Path C — the user's own environment code (`wheels-v1`)

Use when the code is neither a Gym source tree nor a `verifiers` environment: a custom verifier, a bespoke agent, anything that has to ship as an installable package.

`wheels-v1` is the least constrained format — `config_paths` may sit anywhere — and correspondingly the one with the least done for you. There is no converter; build it by hand.

```
my-env/
  nemo-environment.yaml
  configs/my_env.yaml           ← anywhere, but keep it tidy
  wheels/*.whl                  ← full closure, offline-installable
```

```yaml
format: wheels-v1
config_paths:
  - configs/my_env.yaml
metadata:
  name: my-env
  description: Custom reward environment
```

Build the wheel closure so it installs with **no index**, because that is how the platform installs it (`pip install --no-index --find-links=wheels/ wheels/*.whl`):

```bash
mkdir -p my-env/wheels
uv pip download ./my-env-src --dest my-env/wheels        # or: pip download
uv run --package nmp-rl pi-to-gym-conversion --validate-only ./my-env
```

`wheels-v1` declares **no adapter**, so the platform treats its code as possibly a verifier rather than an agent, and starts both `responses_api_agents` and `resources_servers` from it. Your config decides which servers exist.

**Vendor exactly one version of each distribution.** Two versions of one project in `wheels/` is legal for a `--find-links` pool, so it only produces a warning locally — but it means the package no longer pins what gets installed, and a consumer that pins every file outright cannot satisfy it. It surfaces on the cluster as `you require uvicorn==0.52.1 and uvicorn==0.52.3, we can conclude that your requirements are unsatisfiable`. If you rebuild into an existing `wheels/`, clear it first: copying overwrites by filename, so a wheel from an earlier run survives whenever the new closure resolved to a different version.

## Validate before uploading

Cheapest possible failure. Run it on every package, whichever path built it:

```bash
uv run --package nmp-rl pi-to-gym-conversion --validate-only ./my-env-pkg
# {"valid": true, "format": "adapter-wheels-v1", "name": "ascii-tree"}
```

Exit 1 with the specific violation on failure. The same checks run again at submit time against the FileSet listing, so a package that validates here will not be rejected for layout later.

## Upload

The converter can do both FileSets in one step:

```bash
export NMP_BASE_URL=http://127.0.0.1:8080
uv run --package nmp-rl pi-to-gym-conversion \
  --hub-id primeintellect/ascii-tree --hub-version 0.1.5 \
  --out-dir ./ascii-tree-pkg --upload \
  --workspace default --environment-name ascii-tree --dataset-name ascii-tree-dataset
```

Or by hand, which is the only option for Paths A and C. **`--purpose environment`** on the environment FileSet — `dataset`, `environment`, `generic`, and `model` are the four valid values, and the environment one carries manifest metadata the platform reads:

```bash
ENV=ascii-tree
nemo files filesets create "$ENV" --workspace default --purpose environment --exist-ok
# upload every file, preserving relative paths
(cd ./ascii-tree-pkg && find . -type f | sed 's|^\./||' | while read -r f; do
  nemo files upload "$f" "$ENV" --workspace default --remote-path "$f"
done)
nemo files list "$ENV" --workspace default

DATA=ascii-tree-dataset
nemo files filesets create "$DATA" --workspace default --purpose dataset --exist-ok
nemo files upload ./ascii-tree-data/training.jsonl   "$DATA" --workspace default --remote-path training.jsonl
nemo files upload ./ascii-tree-data/validation.jsonl "$DATA" --workspace default --remote-path validation.jsonl
```

Relative paths must be preserved: `config_paths` is matched against the FileSet listing, so a package flattened during upload fails with `config_paths reference files that are not in the package`.

## Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `Missing nemo-environment.yaml at environment root` | No manifest, or uploaded one directory too deep | Manifest at the FileSet root, not inside a subdirectory |
| `Invalid nemo-environment.yaml: ... extra_forbidden` | Unknown manifest key | Remove it; the schema is closed |
| `config_paths reference files that are not in the package` | Upload flattened the tree, or a typo | Re-upload preserving relative paths |
| `Prompt JSONL must not live in the environment package` | `.jsonl` inside the package | Move rows to the dataset FileSet |
| `native-v1 config_paths must be under (...)` | Config outside the three Gym server dirs | Move it, or switch to `wheels-v1` |
| `adapter-wheels-v1 config_paths should live under configs/` | Config elsewhere | Move it under `configs/` |
| `format ... installs its dependencies offline, so the package must carry a non-empty wheels/ directory` | Wheels format with no wheels | Vendor the closure |
| `Non-wheel files in wheels/` | Stray file (sdist, README) | `wheels/` holds `*.whl` only |
| `adapter.agent ... is not built into the training image` | Harness not on the allowlist | Use `verifiers_agent`, or switch format |
| `ServerRefNotFoundError: ... Available responses_api_models: (none)` | Agent config references `policy_model` with nothing defining it | Add `configs/policy_model.yaml` (Path B) |
| `Symlinks are not allowed` | Symlinked config | Ship real files |
| `your requirements are unsatisfiable` on the cluster | `wheels/` vendors two versions of one project | Clear `wheels/` and rebuild the closure |

Environment-incompatible-with-reasoning-parser and vLLM `async_engine` errors are runtime, not packaging — see `troubleshooting.md`.

## Related

| For | Read |
|---|---|
| Gym prompt-row schema and converting a dataset to it | `dataset-formats.md` § **NeMo-RL (GRPO)** |
| GRPO job JSON and hyperparameters | `hyperparameters-rl.md` |
| Kubernetes runtime, sandbox settings, PVC | `rl-kubernetes-runtime.md` |
| Manifest schemas (source of truth) | `services/rl/src/nmp/rl/schemas/environment.py` |
| Validation rules (source of truth) | `services/rl/src/nmp/rl/tasks/environment/validate.py` |
| Converter | `services/rl/src/nmp/rl/tasks/environment/convert.py`, `__main__.py` |
