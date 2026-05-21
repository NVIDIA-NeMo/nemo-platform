# Design: `nemo-customizer` plugin (local fine-tuning, BYO-venv)

This document describes the motivation, design, and trade-offs behind `plugins/nemo-customizer/`. It is the design doc for the plugin; the README is the user-facing manual.

---

## Motivation

The NeMo Platform monorepo already has a `services/customizer/` that handles **remote** customization (multi-step `PlatformJobSpec`, Automodel / Megatron-Bridge / NeMo-RL backends, distributed-GPU container execution). What it doesn't have is a sanctioned **local** path: a way for a user with a GPU on hand to fine-tune a model from their laptop or a dev pod, against their own Python environment, without taking on the multi-step JobSpec runner.

A local plugin is useful for:

- Smoke tests during development — verify a config / dataset / model combination before submitting a real job.
- Single-GPU experiments that don't justify spinning up a remote cluster.
- Working with libraries (Unsloth, MLX, etc.) that the production training stack does not ship.

The driving design constraint is that heavyweight ML libraries (Unsloth + PyTorch + CUDA + xformers + bitsandbytes + trl + transformers + peft) cannot live in the platform's slim runtime venv — they conflict with the platform's dependency graph and each backend wants a different pinned set. The plugin must keep its own footprint small and execute the user's training code in a separate Python environment.

---

## Design constraints

1. **GPU selection, not reservation** — for local runs, GPU exposure follows the standard ML convention (`CUDA_VISIBLE_DEVICES`). No new reservation API; whatever the user has access to on the host is what the backend sees.
2. **CUDA version is the user's responsibility** for local runs. The plugin does not pin a CUDA toolkit; mismatches between the host driver and the installed PyTorch are surfaced as runtime errors, not papered over.
3. **The user provides the venv.** The plugin does not create or manage Python environments. A user (or their bootstrap script) sets up a venv with the right backend extra installed and passes its path via `--venv`. Auto-creation is intentionally deferred; see "Future work" below.
4. **Security posture: local execution = controlled-network environments only.** The plugin runs arbitrary backend code via subprocess re-exec into a user-supplied interpreter. Same stance as agent deployment: not for hostile or shared environments.

---

## High-level architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  user types: nemo customizer finetune run --venv VENV \              │
│              --backend unsloth --training-type sft --gpus 0          │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  parent process (host venv)                                          │
│  ─ Typer parses --venv from the static signature                     │
│  ─ commands.py._run() pops `venv`, calls reexec_run_in_venv()        │
│  ─ subprocess.run: <VENV>/bin/python -m nemo_platform.cli.app        │
│                    customizer finetune run --backend unsloth ...     │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  child process (user-supplied venv with unsloth installed)           │
│  ─ Typer re-parses argv (without --venv)                             │
│  ─ FinetuneJob.run(config) is called                                 │
│  ─ is_satisfied_locally(spec)  →  True (unsloth importable)          │
│  ─ dispatch_in_process(spec, ctx):                                   │
│      • set CUDA_VISIBLE_DEVICES from spec.gpus                       │
│      • import nemo_customizer_plugin.backends.unsloth                │
│      • unsloth.train_sft(spec, ctx)                                  │
│  ─ result dict prints as JSON                                        │
└──────────────────────────────────────────────────────────────────────┘
```

The plugin has no subprocess of its own — the only inter-process hop is the platform's `--venv` re-exec. Both the JobSpec parsing and the heavy training code run inside the user's venv, in a single process.

---

## Components

### `jobs/finetune.py` — `FinetuneJob` + `FinetuneSpec`

- `FinetuneSpec` is a Pydantic v2 model whose scalar fields become auto-generated CLI flags via the platform's `walk_spec_leaves`. The submitter sees `--training-type`, `--backend`, `--model`, `--max-steps`, `--lora-rank`, `--lora-alpha`, `--learning-rate`, `--gpus`, `--max-seq-length`, `--dataset-path`.
- `training_type` and `backend` are typed as `str` (with `@field_validator` enforcing membership) rather than `Literal[...]`. The platform's spec-flag walker skips `Literal` fields today — surfacing these knobs as flags is more important than the stronger static type, and the runtime validator still rejects bad values.
- `FinetuneJob.run` does two things: probe whether the current interpreter has the backend's deps importable, and either dispatch in-process or raise an actionable error. It does not start subprocesses.

### `venv_resolver.py` — probe + extras heuristic

- `extra_for_spec(spec) → str` is a flat lookup that maps `(training_type, backend)` to the pip extra (`"unsloth"`, `"automodel"`, `"megatron-bridge"`). Future training algorithms (DPO, RLHF) add rows.
- `is_satisfied_locally(spec) → bool` uses `importlib.util.find_spec` to check for the backend's marker module without actually importing it. Avoids Unsloth's import-time monkey-patching of transformers in the parent process and keeps the probe fast (microseconds).
- `default_venv_path(backend) → Path` returns the conventional path `~/.nemo/customizer/<backend>/.venv`. The plugin does not create this — `doctor` and the bootstrap script use it for convenience.
- `probe_venv(path, backend)` runs `python -c "import nemo_platform, nemo_customizer_plugin, <marker>"` in the target venv and reports success / detail. Used by `doctor`.
- `missing_venv_message(spec)` builds the actionable error string the job raises when the current interpreter does not satisfy the JobSpec.

### `backends/_dispatch.py` — in-process backend selector

A single function, `dispatch_in_process(spec, ctx)`:

1. Sets `CUDA_VISIBLE_DEVICES` from `spec.gpus` (must happen before the backend imports torch, since the variable is frozen at torch-init time).
2. Branches on `spec.backend` and lazily imports the backend module.
3. Calls `backend.train_sft(spec, ctx)` and returns its dict.

Heavy imports are inside the branch arms so the parent process (which does not have unsloth) can `import _dispatch` for entry-point discovery without crashing.

### `backends/unsloth.py` — the real backend

`train_sft(spec, ctx) → dict`. Notable details:

- `import unsloth` is the **first** import inside the function, before transformers / peft / trl. Unsloth monkey-patches transformers at import time; out-of-order imports silently degrade performance.
- No module-level imports of `unsloth` / `torch` / `transformers`. The parent process (which imports the module path during entry-point introspection) cannot pay those costs.
- Uses `unsloth.FastLanguageModel` for 4-bit load + LoRA, `trl.SFTTrainer` for the training loop. Defaults to `unsloth/Qwen2.5-0.5B-Instruct` and an inline 3-row chat dataset so the smoke test is self-contained.
- Returns `{"loss": float, "steps": int, "model": str, "backend": "unsloth", "output_dir": str, "cuda_visible_devices": str | None}`.

### `backends/automodel.py` and `backends/megatron_bridge.py` — stubs

Each exposes `train_sft(spec, ctx)` that raises `NotImplementedError` with a pointer to `services/customizer/`. The remote service already has production-grade AutoModel and Megatron-Bridge backends; replicating them locally would require factoring their training drivers out of the multi-step `PlatformJobSpec` runner, which is out of scope.

### `cli.py` — `CustomizerCLI` + `doctor`

The plugin's CLI is mostly just the auto-mounted `finetune run` verb. The class adds a `doctor` subcommand that probes a venv's health:

```
nemo customizer doctor --backend unsloth                    # default path
nemo customizer doctor --backend unsloth --venv /path/to/.venv
```

### Core change: `--venv` in `commands.py`

The platform's job `run` verb pops a `venv` kwarg and re-execs into it via `reexec_run_in_venv`. To make `--venv` visible in `--help` and parsed as `Optional[Path]`, the static signature builder in `_build_job_run_signature` adds a `venv` entry under the "Spec Source" panel. `"venv"` is also added to `_JOB_RUN_RESERVED_FLAGS` so spec schemas can't accidentally collide on the name.

---

## CLI surface

```
nemo customizer --help
nemo customizer finetune run --help
nemo customizer doctor --help
```

`finetune run`:

- Spec Source: `--spec`, `--spec-file`, `--venv`
- Job Spec (auto-generated from `FinetuneSpec`): `--training-type`, `--backend`, `--model`, `--dataset-path`, `--max-seq-length`, `--max-steps`, `--lora-rank`, `--lora-alpha`, `--learning-rate`, `--gpus`

---

## Alternatives considered

### Plugin-managed venv auto-creation

An earlier iteration of this design had the plugin auto-create `~/.nemo/customizer/<backend>/.venv` when `--venv` was omitted, installing `nemo-customizer-plugin[<extra>]` into it from the JobSpec-derived extra. This was attractive because the first-run UX was zero-config.

We dropped it for the PoC because:

- Implicit pip-installs into a per-job-shape directory hide significant side effects from the user (multi-GB downloads, several-minute waits, machine state).
- The right venv often depends on host facts (CUDA version, installed system libs) the plugin can't reason about.
- Adding auto-create is strictly additive — once BYO-venv is solid, auto-create can opt-in via a flag (e.g. `--venv auto`) without changing the existing surface.

### Plugin re-execs into its own subprocess

The plugin could spawn its own `python -m nemo_customizer_plugin.backends._dispatch` subprocess into the resolved venv (rather than relying on the core `--venv` re-exec). This was prototyped but removed because:

- It duplicates the platform's `--venv` machinery for no benefit when the user supplies a venv themselves.
- It creates a second re-exec path that has to be reasoned about for recursion safety.
- It only made sense in combination with auto-create.

The core `--venv` mechanism, doing one re-exec into the user's venv and letting the job run in-process from there, is simpler.

### `Literal` types for `training_type` / `backend`

Pydantic `Literal[...]` types would give us static membership checking. The platform's `walk_spec_leaves` skips `Literal` fields when generating per-field CLI flags today, so this would hide `--training-type` / `--backend` from `--help`. We chose `str` + `@field_validator` to keep the flags visible; the validator still rejects bad values at parse time.

A follow-up could add `Literal` → Click Choice handling to `_spec_flags.py`, after which this plugin can flip back to the stronger type.

---

## Entry-point bootstrap subtlety

The plugin is discovered via `importlib.metadata.entry_points()` against the active interpreter's site-packages. When `--venv` re-execs into a different interpreter, the child re-runs entry-point discovery against **its own** site-packages. The plugin's `customizer.finetune` job is only visible if the plugin itself is installed inside the target venv — `unsloth` alone is not enough.

This is why the documented setup command installs the plugin into the venv:

```bash
uv pip install --python "$UNSLOTH_VENV/bin/python" \
    -e /path/to/Platform/plugins/nemo-customizer[unsloth]
```

If the plugin is missing from the venv, the child fails with `Error: no such command 'customizer'`, not a useful pointer to the misconfigured venv. Future work could add a clearer error here.

---

## Test commands

### With an existing venv

```bash
UNSLOTH_VENV=/workspace/.venv-unsloth

# One-time setup
uv venv "$UNSLOTH_VENV" --python 3.11
uv pip install --python "$UNSLOTH_VENV/bin/python" \
    -e /path/to/Platform/plugins/nemo-customizer[unsloth]

# Verify
nemo customizer doctor --backend unsloth --venv "$UNSLOTH_VENV"

# Smoke test
nemo customizer finetune run --venv "$UNSLOTH_VENV" \
    --backend unsloth --training-type sft --gpus 0
```

### Without `--venv` (negative path)

```bash
nemo customizer finetune run --backend unsloth --training-type sft
# → RuntimeError: Backend 'unsloth' is not importable in the current interpreter, ...
```

### Stub backend

```bash
nemo customizer finetune run --venv "$ANY_VENV" --backend automodel --training-type sft
# → NotImplementedError: Local 'automodel' backend is not implemented. Use the remote ...
```

---

## Future work

- **Opt-in venv auto-creation** — `--venv auto` (or similar) re-introduces the install-into-default-path flow as an explicit user request. Use the JobSpec → extras mapping that's already in `venv_resolver`.
- **Surface better errors when the plugin is missing from the target venv** — detect the "no such command 'customizer'" case in the re-exec child and translate it into "install nemo-customizer-plugin into <venv>".
- **`Literal` → Click Choice in `_spec_flags.py`** — once added, flip `training_type` and `backend` back to `Literal` types.
- **Real backends for AutoModel / Megatron-Bridge** — factor the training driver out of `services/customizer/`'s multi-step runner so it can run as a single in-process call.
- **Multi-GPU / DDP** — `--gpus 0,1` works as selection today; the backend (unsloth) currently picks one. A future revision could wire torchrun / accelerate launch through the dispatch layer.
- **Submit verb** — `nemo customizer finetune submit` for sending the same JobSpec to the remote service.

---

## Files

**Plugin (`plugins/nemo-customizer/`):**

- `pyproject.toml` — entry points (`nemo.cli`, `nemo.jobs`), optional dependencies (`[unsloth]`, `[automodel]`, `[megatron-bridge]`, `[all]`).
- `src/nemo_customizer_plugin/cli.py` — `CustomizerCLI` + `doctor` command.
- `src/nemo_customizer_plugin/venv_resolver.py` — `extra_for_spec`, `is_satisfied_locally`, `default_venv_path`, `probe_venv`, `missing_venv_message`.
- `src/nemo_customizer_plugin/jobs/finetune.py` — `FinetuneJob`, `FinetuneSpec`.
- `src/nemo_customizer_plugin/backends/_dispatch.py` — `dispatch_in_process`.
- `src/nemo_customizer_plugin/backends/unsloth.py` — real backend.
- `src/nemo_customizer_plugin/backends/{automodel,megatron_bridge}.py` — stubs.
- `tests/` — unit tests for `venv_resolver` and `_dispatch`.
- `devops/gpu-pod.yaml` — 1-GPU testing pod.
- `devops/init-gpu-pod.sh` — pod-side bootstrap (creates the unsloth venv if missing; runs the smoke test).

**Core change (`packages/nemo_platform_plugin/src/nemo_platform_plugin/commands.py`):**

- `_build_job_run_signature` now declares `--venv` under the "Spec Source" panel.
- `_JOB_RUN_RESERVED_FLAGS` includes `"venv"` to prevent collisions with spec field names.
