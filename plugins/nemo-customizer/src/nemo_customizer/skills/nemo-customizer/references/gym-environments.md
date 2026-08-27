<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

<!-- NeMo Gym environment packaging for GRPO. Job JSON: `hyperparameters-rl.md`. Prompt rows: `dataset-formats.md` § NeMo-RL (GRPO). -->

# NeMo Gym environments for GRPO

GRPO scores sampled responses against an **environment** — code that runs a rollout and returns a reward. The platform takes that environment as a **FileSet**, and the prompts as a **separate** FileSet. This file covers what a valid environment package looks like in all three formats, and how to get from the user's source to one of them.

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
| A Gym server tree whose deps resolve at spin-up (cluster has egress, or they are prefetched in the image) | **`native-v1`** | No | `responses_api_agents/`, `resources_servers/`, `responses_api_models/` |
| A Prime Intellect hub env, or any `verifiers` environment installable as a wheel | **`adapter-wheels-v1`** | **Yes** | `configs/` |
| Anything else — including a Gym server tree whose deps must be vendored | **`wheels-v1`** | **Yes** | anywhere in the package |

Decision shortcut: **is there a `verifiers` environment?** → `adapter-wheels-v1` (and use the converter, below). **Otherwise** → `wheels-v1`, unless the cluster can resolve the server's requirements from an index at spin-up, in which case `native-v1` saves you vendoring.

**All three formats run on the same runtime.** The training image carries the NeMo Gym source tree and starts a package's servers the same way it starts Gym's own. What differs is **where dependencies come from** (§ **Dependency installation**). Settle that before layout.

`adapter-wheels-v1` is the only format with a bundled converter, and `verifiers_agent` is the only entry on `IMAGE_ADAPTER_ALLOWLIST`. That is the shortest path for a `verifiers` env.

## Dependency installation — settle this first

Source of truth: `nemo_rl.environments.gym_env_package` (in the RL image), `docker/rl/README.md` § *NeMo-Gym environments: a second, separate venv layer*.

Gym builds **one venv per server** at spin-up, from that server's own `pyproject.toml` / `requirements.txt`, under `NEMO_GYM_VENV_DIR` (`/opt/gym_venvs`). That directory ships **empty** — `NEMO_GYM_PREFETCH_CONFIGS` is off by default — so every environment pays this on first use, built-in ones included.

The platform itself installs nothing. `grpo_driver` calls `bootstrap_environment_package(..., install_wheels=False)`: it validates and stops there, because the venvs a server runs from do not exist until `RunHelper.start`. NeMo-RL prepends the package to `NEMO_GYM_EXTRA_ROOTS` (so a package server shadows a built-in of the same name) and adds `wheels/` to `UV_FIND_LINKS`, then after the venvs exist installs the closure into each one as **unpinned distribution names**. Requirements the wheelhouse does not carry resolve from an index.

| Format | Server deps come from | Needs egress at spin-up |
|---|---|---|
| `native-v1` | An index, per the server's `requirements.txt` | **Yes** |
| `wheels-v1` | The package's `wheels/`, for whatever it vendors | **No**, if the closure is complete |
| `adapter-wheels-v1` | The package's `wheels/`, plus the agent harness's own requirements | **Yes** — see below |

**`adapter-wheels-v1` requires network at job start.** The wheelhouse covers the hub environment; the `verifiers_agent` harness builds its venv from its own `requirements.txt`, which carries `verifiers @ git+https://github.com/PrimeIntellect-ai/verifiers.git`. A converted hub env needs egress even with a complete FileSet. Do not promise an offline run.

Egress is operator config, never a job field: `NMP_RL_SANDBOX_ALLOW_INTERNET`, plus `NMP_RL_SANDBOX_PUBLIC_DNS_ALLOW` for hosts outside NeMo-RL's built-in `*.com` / `*.org` allowance (e.g. `hub.primeintellect.ai`). Check with the operator before committing a user to `native-v1` on a deny-default cluster.

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

Gym resolves servers **by name** against a component search path, and the package is prepended to it (`NEMO_GYM_EXTRA_ROOTS`), so a package entry shadows a built-in with the same name. That applies to every format, not just this one.

The YAML **implementation** key is the directory Gym `cd`s into (`resources_servers/<impl>/` with `requirements.txt` or `pyproject.toml`). The **instance** name (top-level key) is what `agent_ref.name` and `{type, name}` refs use. Image implementations (`simple_agent`, `vllm_model`, `verifiers_agent`) can be referenced without uploading their `app.py`.

**`native-v1` ships no `wheels/`, so its per-server venv resolves from a package index at spin-up and the job needs egress.** It does *not* mean the server's imports must already be in the image — Gym installs them at first use either way. Choose `native-v1` when the cluster can reach an index (or the server is one of the built-ins baked in via `NEMO_GYM_PREFETCH_CONFIGS`); otherwise ship the same tree as `wheels-v1` with a vendored closure. That is Path C, and it is the more common answer on a deny-default cluster.

**The dataset caveat bites hardest here.** Gym's own configs point `datasets[].jsonl_fpath` at an in-tree file. That file cannot ship in the package. Either drop the `datasets` block and let the platform's dataset FileSet supply rows, or keep it and accept that the path will not resolve. Prompts must be converted to Gym JSONL rows either way — see `dataset-formats.md` § **NeMo-RL (GRPO)**.

## Path B — a Prime Intellect / verifiers env (`adapter-wheels-v1`)

The automated path, and the only one with a converter. It downloads the hub package, vendors its full wheel closure, writes both configs and the manifest, and builds the prompt JSONL.

**Run it on a host with internet.** Training clusters have no hub egress and consume uploaded FileSets only.

`pi-to-gym-conversion` is a console script that ships with `nemo-rl-plugin`, so on an installed platform run it bare. The `uv run --package nmp-rl` prefix below is for a repo checkout.

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

**Why two configs — and this is not adapter-only.** `verifiers_agent.yaml` references a model server named `policy_model`; nothing defines that server unless a second config supplies it, and Gym resolves every ref when it merges configs, failing with `ServerRefNotFoundError: ... Available responses_api_models: (none)`. `policy_model.yaml` supplies it, interpolating `${policy_base_url}` / `${policy_api_key}` / `${policy_model_name}` against the config NeMo-RL injects at spin-up — which is what points Gym at the vLLM engine the job is already running instead of starting its own.

**Every format needs this file.** Gym's own server configs reference `policy_model` the same way (`math_with_judge` needs it for both `model_server` and `judge_model_server`, and `should_use_judge: false` does not help — resolution happens before any judging would be skipped). The converter writes it; hand-built packages must add it. Generate it from the same helper the converter uses, so the two cannot drift:

```python
import yaml
from nmp.rl.tasks.environment.package import build_policy_model_yaml

(out_dir / "configs").mkdir(parents=True, exist_ok=True)
(out_dir / "configs" / "policy_model.yaml").write_text(
    yaml.safe_dump(build_policy_model_yaml(), sort_keys=False), encoding="utf-8"
)
```

List it **first** in `config_paths`, ahead of the config that references it. Placement differs by format: `configs/policy_model.yaml` for the two wheels formats; `native-v1` must live under a Gym server prefix. Use `responses_api_models/vllm_model/configs/policy_model.yaml` so the on-disk path matches the YAML implementation (`vllm_model`). A folder named `policy_model` also passes the prefix check; Gym runs `responses_api_models/vllm_model/` from the YAML body, not from the config file's directory.

**`max_tokens` lives in the package, not the job.** `configs/verifiers_agent.yaml` carries `max_tokens` (default 8192), and `verifiers_agent` reads it in preference to the job's `max_new_tokens`. To bound response length for an adapter env, edit this file before uploading — see `hyperparameters-rl.md` § **Known limitation**.

## Path C — vendored code (`wheels-v1`)

The catch-all, and the right answer more often than its "bring your own code" framing suggests. Use it for a custom verifier or bespoke agent — **and for a Gym source-tree server whose dependencies have to travel with it**, which is the common case on a cluster without egress.

`wheels-v1` is the least constrained format — `config_paths` may sit anywhere — and correspondingly the one with the least done for you. There is no converter; build it by hand.

Gym runs `{server_type}/{implementation}/` and requires `requirements.txt` or `pyproject.toml` there. A `configs/` + `wheels/` package with **no** server directories only works when every YAML implementation is already in the image (`simple_agent`, `vllm_model`, `verifiers_agent`). A custom `resources_servers/my_env` **must** ship that directory, even if the YAML itself lives under `configs/`.

```
my-env/
  nemo-environment.yaml
  configs/policy_model.yaml     ← required; see Path B
  configs/my_env.yaml
  resources_servers/my_env/     ← required for a custom implementation
    app.py
    requirements.txt
  wheels/*.whl                  ← the closure
```

```yaml
format: wheels-v1
config_paths:
  - configs/policy_model.yaml
  - configs/my_env.yaml
metadata:
  name: my-env
  description: Custom reward environment
```

`wheels-v1` declares **no adapter**, so its code may be a verifier rather than an agent, and both `responses_api_agents` and `resources_servers` are started from it. Your config decides which servers exist.

### Vendoring the closure

The wheelhouse reaches Gym through `UV_FIND_LINKS`, so it is a candidate pool, not a lock file: what it covers installs from local files; what it misses goes to an index.

**Wheels must target the training image, not the build host.** The image is **Python 3.13 on `x86_64` manylinux**. A closure downloaded on macOS or arm64 passes `--validate-only` — which checks layout, never wheel tags — and then fails on the cluster with `has no wheels with a matching platform tag`. Match what the converter does (`TARGET_PYTHON_VERSION`, `TARGET_WHEEL_PLATFORMS` in `convert.py`):

```bash
mkdir -p my-env/wheels
pip download -r requirements.txt --dest my-env/wheels \
  --only-binary=:all: \
  --python-version 3.13 \
  --platform manylinux_2_39_x86_64 \
  --platform manylinux_2_28_x86_64 \
  --platform manylinux_2_17_x86_64 \
  --platform manylinux2014_x86_64
uv run --package nmp-rl pi-to-gym-conversion --validate-only ./my-env
```

`--platform` is repeated because pip matches tags literally rather than expanding a compatibility range, so a project publishing only against an older glibc floor is missed unless its tag is named.

**Vendor exactly one version of each distribution.** Several versions of one project is legal for a find-links pool, so it only warns locally — but the package then no longer pins what gets installed. Clear `wheels/` before rebuilding into it: copies overwrite by filename, so a wheel from an earlier run survives whenever the new closure resolved that project to a different version.

### Packaging a Gym server tree as `wheels-v1`

Keep the Gym directory structure (`resources_servers/<name>/` with its `app.py`, `configs/`, `requirements.txt`), drop `data/` and `tests/` so no `.jsonl` survives, add `configs/policy_model.yaml` and the manifest at the root, and vendor `wheels/`.

**Vendor `nemo-gym` itself.** Gym builds each server's venv from its `requirements.txt`, which in the source tree starts `-e nemo-gym[dev] @ ../../`. Outside a Gym checkout that relative path does not exist, so `setup_env_command` rewrites the line to `nemo-gym==<parent version>` and resolves it from an index. Vendoring the matching `nemo-gym` wheel keeps that offline — and it must be the *exact* version the image runs, or Gym silently falls back to PyPI:

```bash
docker run --rm <training-image> python -c 'import importlib.metadata as m; print(m.version("nemo-gym"))'
```

Validate the tree with `--validate-only`.

## Validate before uploading

Cheapest possible failure. Run it on every package, whichever path built it:

```bash
uv run --package nmp-rl pi-to-gym-conversion --validate-only ./my-env-pkg
# {"valid": true, "format": "adapter-wheels-v1", "name": "ascii-tree"}
```

Exit 1 with the specific violation on failure. The same checks run again at submit time against the FileSet listing, so a package that validates here will not be rejected for layout later.

**What it does not check:** wheel platform tags, whether the closure is complete, whether `config_paths` actually define the servers your rows route to, or anything about dataset rows. Those all surface at spin-up. Validation is a layout check, not a dry run.

## Upload

The converter can do both FileSets in one step:

```bash
export NMP_BASE_URL=http://127.0.0.1:8080
uv run --package nmp-rl pi-to-gym-conversion \
  --hub-id primeintellect/ascii-tree --hub-version 0.1.5 \
  --out-dir ./ascii-tree-pkg --upload --workspace default
```

Without `--environment-name` / `--dataset-name` it derives them from the hub slug as **`<slug>-env`** and **`<slug>-env-dataset`** — here `ascii-tree-env` and `ascii-tree-env-dataset`. Read the names back from the `uploaded` block in its JSON output rather than assuming.

Or by hand, which is the only option for Paths A and C. Use **`--purpose environment`** on the environment FileSet; `dataset`, `environment`, `generic`, and `model` are the four valid values. The package is identified by `nemo-environment.yaml` at submit; set `purpose` so listings are accurate.

`nemo files upload` takes a directory and uploads recursively, preserving relative paths, so one command per fileset is enough:

```bash
ENV=ascii-tree-env
nemo files filesets create "$ENV" --workspace default --purpose environment --exist-ok
nemo files upload ./ascii-tree-pkg/ "$ENV" --workspace default
nemo files list "$ENV" --workspace default

DATA=ascii-tree-env-dataset
nemo files filesets create "$DATA" --workspace default --purpose dataset --exist-ok
nemo files upload ./ascii-tree-data/ "$DATA" --workspace default
```

The **trailing slash** on the local path is load-bearing (fsspec): it selects the directory's contents rather than the directory itself.

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
| `ServerRefNotFoundError: ... Available responses_api_models: (none)` | A config references `policy_model` with nothing defining it | Add a `policy_model` config — **every** format needs one; see Path B |
| `Symlinks are not allowed` | Symlinked config | Ship real files |
| `your requirements are unsatisfiable` on the cluster | `wheels/` vendors two versions of one project | Clear `wheels/` and rebuild the closure |
| `has no wheels with a matching platform tag` | Closure built for the build host (macOS / arm64), not the image | Re-download with the `--python-version` / `--platform` flags in Path C |
| Spin-up stalls, then fails resolving a package | The per-server venv build cannot reach an index | Vendor it (`wheels-v1`), or ask the operator for `NMP_RL_SANDBOX_ALLOW_INTERNET` — see § **Dependency installation** |
| `OpenSandbox is not yet available on this cluster (sandbox_cluster_capable=false)` | Operator has not enabled sandboxed Gym | Platform config, not the package — `rl-kubernetes-runtime.md` § **Sandboxed Gym** |
| `Sandboxed GRPO requires the job-storage PVC claim name` | `NMP_RL_JOB_STORAGE_PVC_CLAIM` unset | Same — operator config |

The last two fail **at submit**, before any GPU is claimed, and no change to the package will fix them.

Environment-incompatible-with-reasoning-parser and vLLM `async_engine` errors are runtime, not packaging — see `troubleshooting.md`.

## Related

| For | Read |
|---|---|
| Gym prompt-row schema and converting a dataset to it | `dataset-formats.md` § **NeMo-RL (GRPO)** |
| GRPO job JSON and hyperparameters | `hyperparameters-rl.md` |
| Kubernetes runtime, sandboxed Gym, PVC, egress | `rl-kubernetes-runtime.md` § **Sandboxed Gym (GRPO)** |
| Manifest schemas (source of truth) | `services/rl/src/nmp/rl/schemas/environment.py` |
| Validation rules (source of truth) | `services/rl/src/nmp/rl/tasks/environment/validate.py` |
| Converter, wheel targeting, `build_policy_model_yaml` | `services/rl/src/nmp/rl/tasks/environment/convert.py`, `package.py`, `__main__.py` (`pi-to-gym-conversion`) |
| GPU smoke (convert → upload → one GRPO step) | `scripts/gpu-grpo-smoke/` |
| How wheels and search roots actually reach Gym | `nemo_rl.environments.gym_env_package` (RL image), `docker/rl/README.md` § **NeMo-Gym environments** |
