# Troubleshooting

Read this file when submit fails, jobs fail on images, or the user asks for Unsloth.

## Backend choice (automodel vs unsloth)

**Do not** run `docker info` on the agent machine. The platform often runs elsewhere (`NEMO_BASE_URL`). Ask the **connected platform** what executors it exposes.

After `nemo auth login`, list profiles:

```bash
uv run nemo jobs list-execution-profiles -f json
```

REST equivalent (same payload): `GET /apis/jobs/v2/execution-profiles` on the platform base URL with the saved auth token.

Each entry has `provider`, `profile` (name), and `backend` (e.g. `docker`, `kubernetes_job`, `volcano_job`, `subprocess`).

| Condition | Plugin |
|-----------|--------|
| User explicitly asks for Unsloth | `unsloth` (verify `--venv` setup — see *Unsloth `--venv` setup and probe* below) |
| User explicitly asks for Automodel | `automodel` (verify a GPU execution profile exists) |
| Response includes **`provider`: `gpu` or `gpu_distributed`** | **`automodel`** (default) |
| No GPU profiles (only `subprocess` and/or CPU `provider`), caller has a usable local GPU | **`unsloth`** locally (one-time `--venv` setup required) |
| No GPU profiles **and** no local GPU | Report that GPU customization is unavailable; offer to set up a remote platform with a GPU profile |

Automodel training steps need a **GPU execution profile** on the platform. `subprocess` profiles run host commands and are not a substitute for automodel's GPU container step. Unsloth ignores execution profiles entirely — it runs in-process inside `$UNSLOTH_VENV` on the caller's machine and reads `hardware.gpus` (selection via `CUDA_VISIBLE_DEVICES`, not platform reservation).

### Pick `training.execution_profile`

When using automodel, set `training.execution_profile` in job JSON to the **`profile`** string of a GPU row from the list (e.g. `default`, `docker_gpu`). If omitted, the plugin default is usually `gpu` — submit errors mentioning an unknown profile mean you should re-list and set an exact name from the API.

Quick filter (stdout only — do not use `2>&1` or `json.load` breaks on stderr warnings):

```bash
uv run nemo jobs list-execution-profiles -f json 2>/dev/null | python3 -c "
import sys, json
for p in json.load(sys.stdin):
    if p.get('provider') in ('gpu', 'gpu_distributed'):
        print(p['profile'], p.get('backend'), p.get('provider'))
"
```

Do not run `nemo customization --help` unless submit returns unknown plugin.

## Verb is backend-specific

- **Automodel** uses **`submit` only** (no local `run`). Dataset refs in job JSON: `default/<fileset>`.
- **Unsloth** uses **`run` only** (no `submit`). The CLI exits non-zero with a friendly hint if you try `nemo customization unsloth submit ...`. Dataset refs in job JSON: `default/<fileset>` (single `dataset.path`).

## Unsloth `--venv` setup and probe

Unsloth requires a **separate Python venv** containing the heavy ML extras (`unsloth`, `torch`, `transformers`, `trl`, `peft`, `accelerate`, `bitsandbytes`). The base `nemo` install does **not** pull these. The platform's `--venv` flag re-execs `nemo customization unsloth run` inside the supplied interpreter before importing anything torch-related.

One-time setup (from nemo-platform root):

```bash
export UNSLOTH_VENV=/workspace/.venv-unsloth   # any path the user owns
uv venv "$UNSLOTH_VENV" --python 3.11
uv pip install --python "$UNSLOTH_VENV/bin/python" -e plugins/nemo-unsloth[unsloth]
```

Probe (must print nothing and exit 0):

```bash
"$UNSLOTH_VENV/bin/python" -c "import nemo_platform, nemo_unsloth_plugin, unsloth"
```

| Error from `unsloth run` | Cause | Fix |
|--------------------------|-------|-----|
| `Backend 'unsloth' is not importable in the current interpreter` | `--venv` omitted, or the venv doesn't have the `[unsloth]` extra | Pass `--venv "$UNSLOTH_VENV"`; if it still fails, re-run the install above and the probe |
| `torch.cuda.is_available()` returns False inside training | Host CUDA / driver mismatch with the torch wheel installed into `$UNSLOTH_VENV` | Verify `nvidia-smi` works on the host, then reinstall torch in the venv against a compatible CUDA wheel (`uv pip install --python "$UNSLOTH_VENV/bin/python" torch --index-url https://download.pytorch.org/whl/cu121` or matching cu-tag) |
| `ImportError: cannot import name 'FastLanguageModel'` | Old `unsloth` version | `uv pip install --python "$UNSLOTH_VENV/bin/python" -U unsloth` |
| `OSError: Could not find a suitable CUDA install` | No GPU on the caller machine | Switch to automodel (remote GPU); unsloth is single-GPU on the local box |

The plugin does **not** auto-create venvs and does **not** manage CUDA versions — that's the BYO-venv contract. See `plugins/nemo-unsloth/README.md` for the canonical install snippet.

## Missing training images (automodel only)

Set **before** starting the platform (not per job):

```bash
export NMP_IMAGE_REGISTRY=<registry>
export NMP_IMAGE_TAG=<tag>
export NMP_AUTOMODEL_IMAGE_REGISTRY=$NMP_IMAGE_REGISTRY
```

Pull automodel images only when the job error mentions a missing image. Unsloth does **not** consume platform-managed training images — it runs in-process inside `$UNSLOTH_VENV`, so registry env vars are irrelevant to it.

## CLI quick reference

Shared:

| Action | Command |
|--------|---------|
| Execution profiles | `nemo jobs list-execution-profiles -f json` |
| Create dataset fileset | `nemo files filesets create <name> --workspace default --purpose dataset --exist-ok` |
| Create HF weights fileset | `nemo files filesets create <name> --workspace default --purpose model --exist-ok --storage '{"type":"huggingface","repo_id":"<repo>","repo_type":"model","revision":"main"}'` |
| Upload | `nemo files upload <local> <fileset> --workspace default --remote-path train.jsonl` |
| List files | `nemo files list <fileset> --workspace default` |
| Create model | `nemo models create <name> --workspace default --exist-ok --input-data '<json>'` |

Automodel (remote):

| Action | Command |
|--------|---------|
| Submit | `nemo customization automodel submit <job.json> --workspace default` |
| Status | `nemo jobs get-status automodel-<id>` |
| Live schema | `nemo customization automodel explain` |

Unsloth (local):

| Action | Command |
|--------|---------|
| One-time venv setup | `uv venv "$UNSLOTH_VENV" --python 3.11 && uv pip install --python "$UNSLOTH_VENV/bin/python" -e plugins/nemo-unsloth[unsloth]` |
| Venv probe | `"$UNSLOTH_VENV/bin/python" -c "import nemo_platform, nemo_unsloth_plugin, unsloth"` |
| Run | `nemo customization unsloth run <job.json> --venv "$UNSLOTH_VENV" --workspace default` |
| Live schema | `nemo customization unsloth explain` |

There is **no** `nemo jobs get-status` for unsloth — `run` is synchronous and prints the result dict to stdout. There is no `submit` verb either (it is intentionally disabled).
