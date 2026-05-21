# nemo-customizer-plugin

Local fine-tuning plugin for the NeMo Platform. Backend dispatch (Unsloth implemented; AutoModel and Megatron-Bridge stubbed). BYO-venv model: the user provides a Python environment that has the backend's heavy dependencies installed, and the plugin re-execs into it via the platform's `--venv` flag.

## Status & security posture

**Proof-of-concept.** Local-only. The plugin spawns Python subprocesses against user-supplied environments. **It is intended for use only in strictly controlled network environments.** Same posture as agent deployment.

For remote / production customization, use `services/customizer/` via `nemo customization job create ...`.

## Backends

| Backend           | Status                                            |
| ----------------- | ------------------------------------------------- |
| `unsloth`         | Implemented                                       |
| `automodel`       | Stub — use remote `services/customizer/`          |
| `megatron-bridge` | Stub — use remote `services/customizer/`          |

## Install

From the monorepo root:

```bash
uv pip install -e plugins/nemo-customizer
```

This installs the plugin into your host venv so `nemo customizer ...` becomes available. Heavy backend dependencies (Unsloth, etc.) are **not** installed by this command — they belong in a separate venv that you create and pass via `--venv`.

## Set up the unsloth venv (one-time)

The plugin does not auto-create venvs. Do this once on a machine with a working CUDA toolchain:

```bash
# Pick a path you'll reuse — the convention is ~/.nemo/customizer/<backend>/.venv,
# but any path works. Example uses /workspace/.venv-unsloth.
UNSLOTH_VENV=/workspace/.venv-unsloth

uv venv "$UNSLOTH_VENV" --python 3.11
uv pip install --python "$UNSLOTH_VENV/bin/python" \
    -e /path/to/Platform/plugins/nemo-customizer[unsloth]
```

The `[unsloth]` extra brings in `unsloth`, `trl`, `transformers`, `datasets`, `peft`, `accelerate`, `bitsandbytes`. The `-e` install also pulls the editable monorepo packages (`nemo-platform`, `nemo-platform-plugin`, `nemo-customizer-plugin`) into the venv — those are required for entry-point discovery once the re-exec lands inside the venv.

Verify with:

```bash
nemo customizer doctor --backend unsloth --venv "$UNSLOTH_VENV"
```

Or do a manual probe:

```bash
"$UNSLOTH_VENV/bin/python" -c "import unsloth, nemo_platform, nemo_customizer_plugin"
```

## Run the smoke test (existing venv)

```bash
UNSLOTH_VENV=/workspace/.venv-unsloth

nemo customizer finetune run \
    --venv "$UNSLOTH_VENV" \
    --backend unsloth \
    --training-type sft \
    --gpus 0
```

What happens:

1. The platform's core `--venv` flag re-execs the entire `nemo` CLI inside `$UNSLOTH_VENV/bin/python` (see `packages/nemo_platform_plugin/src/nemo_platform_plugin/jobs/_venv_reexec.py`).
2. The child process re-enters `FinetuneJob.run()` with `unsloth` importable.
3. `is_satisfied_locally(spec)` returns `True`, so the job dispatches in-process to `backends.unsloth.train_sft`.
4. Unsloth loads `unsloth/Qwen2.5-0.5B-Instruct` (default model), applies LoRA, runs 1 SFT step on a 3-row inline dataset, and prints a JSON result with the training loss.

Override defaults with the auto-generated per-field flags:

```bash
nemo customizer finetune run --venv "$UNSLOTH_VENV" \
    --backend unsloth --training-type sft \
    --model unsloth/llama-3-8b-bnb-4bit \
    --max-steps 10 \
    --lora-rank 16 \
    --gpus 0,1
```

## What happens without `--venv`?

If you forget `--venv` (or run from a venv that doesn't have unsloth), the job exits with an actionable message telling you how to set up a venv and the exact `--venv` value to use:

```
$ nemo customizer finetune run --backend unsloth --training-type sft
...
RuntimeError: Backend 'unsloth' is not importable in the current interpreter, and no
--venv was supplied. The plugin does not auto-create venvs; you need to set one up
and re-run with --venv.

Recommended setup (one-time):
  uv venv /home/user/.nemo/customizer/unsloth/.venv --python 3.11
  uv pip install --python /home/user/.nemo/customizer/unsloth/.venv/bin/python \
      -e <path-to>/plugins/nemo-customizer[unsloth]

Then re-run with:
  nemo customizer finetune run --venv /home/user/.nemo/customizer/unsloth/.venv \
      --backend unsloth --training-type sft ...
```

## GPU selection

`--gpus 0` or `--gpus 0,1` sets `CUDA_VISIBLE_DEVICES` for the in-process backend (set **before** `unsloth`/`torch` is imported, since the env var is frozen on import). Selection, not reservation — whether the backend uses all selected GPUs is the backend's decision (Unsloth picks one).

## CUDA caveat

The plugin does not manage CUDA versions. You're responsible for having a host CUDA install compatible with the Unsloth/PyTorch versions installed into your venv. If `import torch` succeeds but `torch.cuda.is_available()` is `False`, fix your host CUDA before retrying.

Unsloth's documented CUDA support: 12.1, 12.4, 12.6, 12.8. Avoid 12.9 unless you've verified Unsloth supports it.

## Doctor

```bash
nemo customizer doctor --backend unsloth                    # probes ~/.nemo/customizer/unsloth/.venv
nemo customizer doctor --backend unsloth --venv /path/to/.venv   # probes a custom path
```

Exits non-zero if missing or broken.

## File layout

```
plugins/nemo-customizer/
├── pyproject.toml
├── plan.md                       # Design doc (motivation, design, alternatives)
├── README.md                     # This file
├── src/nemo_customizer_plugin/
│   ├── cli.py                    # CustomizerCLI + doctor command
│   ├── venv_resolver.py          # JobSpec → extras, probe, missing-venv messaging
│   ├── jobs/finetune.py          # FinetuneJob + FinetuneSpec
│   └── backends/
│       ├── _dispatch.py          # in-process dispatch; sets CUDA_VISIBLE_DEVICES
│       ├── unsloth.py            # train_sft — the only real backend
│       ├── automodel.py          # stub
│       └── megatron_bridge.py    # stub
├── tests/                        # unit tests for venv_resolver + dispatch
└── devops/                       # GPU pod yaml + bootstrap script for cluster testing
```

## See also

- `plan.md` — design doc with motivation, alternatives considered, and future work.
- `devops/gpu-pod.yaml` — Kubernetes pod spec for a 1-GPU testing pod.
- `devops/init-gpu-pod.sh` — pod-side bootstrap (creates the unsloth venv if missing, then runs the smoke test).
- `packages/nemo_platform_plugin/src/nemo_platform_plugin/jobs/_venv_reexec.py` — the platform's `--venv` re-exec mechanism this plugin builds on.
- `services/customizer/` — remote customization service. Use for production / multi-GPU / multi-node runs.
