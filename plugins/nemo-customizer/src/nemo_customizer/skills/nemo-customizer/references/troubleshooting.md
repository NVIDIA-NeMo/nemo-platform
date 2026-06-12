# Troubleshooting

Read this file when submit fails, jobs fail on images, the platform is unreachable, or the user asks for Unsloth.

## Platform unreachable (connection error)

Any `nemo …` call may fail with `Connection error`, timeout, or connection refused — typically on the first `nemo jobs list-execution-profiles` after auth.

**Did the user override the base URL?**

| Situation | Action |
|-----------|--------|
| User gave a platform host/URL (e.g. `10.0.0.51:8080`) or you set `NEMO_BASE_URL` / `NMP_BASE_URL` to something other than `http://127.0.0.1:8080` or `http://localhost:8080` | Report that the platform is not reachable at that address. Ask them to confirm the host is up and the URL is correct. **Do not** start local services. |
| Default URL only — no user override | **Ask** whether to start the platform locally. If they agree, from the **nemo-platform** git root run in the **background**, then poll until healthy and retry the failed command: |

```bash
uv run nemo services run \
  --host 0.0.0.0 \
  --port 8080 \
  --controllers jobs,entities,models \
  --service-group all
```

Health check (repeat until success or ~2 min):

```bash
curl -sf http://127.0.0.1:8080/health/ready
# or
uv run nemo jobs list-execution-profiles -f json
```

Do **not** auto-start services without asking. Customization needs **jobs**, **entities** (filesets), and **models** controllers — the command above is the minimal local set for this skill.

If the user already has a listener on `:8080` but health fails, see **nemo-status** (stale lock / wedged platform) before starting a second instance.

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
| User explicitly asks for Unsloth | `unsloth` |
| User explicitly asks for Automodel | `automodel` |
| Response includes **`provider`: `gpu` or `gpu_distributed`** | **`automodel`** (default) |
| No GPU profiles (only `subprocess` and/or CPU `provider`) | Report that GPU customization is unavailable |

Both backends are **`submit`-only**. After submit, the platform's **Docker executor** runs GPU container steps on the daemon attached to the connected platform host (`platform.runtime: docker`). Training does not run in the CLI shell — query execution profiles on the platform (`NEMO_BASE_URL`), not GPU availability in the agent's terminal.

### Pick execution profile

**Automodel** — set `training.execution_profile` in job JSON to the **`profile`** string of a GPU row from the list (e.g. `default`, `docker_gpu`). If omitted, the plugin default is usually `gpu` — submit errors mentioning an unknown profile mean you should re-list and set an exact name from the API.

**Unsloth** — pass `--profile <name>` on `nemo customization unsloth submit …` when the default `gpu` profile is wrong. There is no `execution_profile` field in `UnslothJobInput` today.

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

## Parsing CLI JSON

`submit`, `explain`, and `-f json` commands write **JSON on stdout**. Harmless config warnings (e.g. `Configuration file not found, using defaults`) go to **stderr**, not stdout.

**Do not** merge stderr into stdout with **`2>&1`** before `json.load` or jq — the warnings prefix the stream and cause `JSONDecodeError` even when submit **succeeded** and the job is already queued. That parse failure often leads to **duplicate jobs** when the agent re-runs submit.

| Do | Don't |
|----|-------|
| Pipe **stdout only**: `… submit /tmp/job.json \| python3 -c "import sys,json; print(json.load(sys.stdin)['name'])"` | `… submit /tmp/job.json 2>&1 \| python3 -c "import sys,json; json.load(sys.stdin)"` |
| Suppress stderr if noisy: append `2>/dev/null` to the `nemo` command (not `2>&1`) | Merge stderr into the JSON pipe with `2>&1` |
| On `json.load` failure, check `nemo jobs list` before re-submitting | Assume submit failed and submit again |

Same rule for `nemo jobs list-execution-profiles -f json`: parse stdout only; use `2>/dev/null` if needed, never `2>&1` into `json.load`.

## Verb is backend-specific (both submit-only)

- **Automodel** and **Unsloth** both use **`submit` only**. `nemo customization <plugin> run …` hard-fails with a pointer to `submit`.
- Dataset refs in job JSON: `default/<fileset>` (automodel: `dataset.training` / `dataset.validation`; unsloth: `dataset.path` / optional `dataset.validation_path`).

## Missing training images

Job errors like `Failed to pull image … nmp-unsloth-training:… Not Found`, `manifest unknown`, or a missing automodel training image mean the **connected platform's Docker daemon** (the one that runs GPU job steps) does not have the image. With the default `NEMO_BASE_URL` / `NMP_BASE_URL` (`127.0.0.1:8080` / `localhost:8080`), that daemon is usually on the same machine as the agent; with a user-overridden URL (e.g. `10.0.0.51:8080`), it is on the remote target host instead.

**Did the user override the base URL?** (same rule as **Platform unreachable** — track this from the start of the workflow.)

| Situation | Action |
|-----------|--------|
| **Remote platform** — user gave a host/URL (e.g. `10.0.0.51:8080`) or you set `NEMO_BASE_URL` / `NMP_BASE_URL` to something other than `http://127.0.0.1:8080` or `http://localhost:8080` | **Do not** run `docker build`, `docker pull`, or `docker buildx bake` on the agent machine — that only affects the agent's local daemon, not the remote platform. Tell the user they must build or load the image **on the target host** (the machine whose Docker daemon runs the GPU job steps). Report with **Report to user** in `SKILL.md`, then append **Report follow-up — missing image (remote platform)** below. Stop; do not retry submit until the user confirms the image is available on the target. |
| **Local platform** — default URL only (`127.0.0.1:8080` / `localhost:8080`) | Build or pull on **that same host** where `nemo services run` and Docker share a daemon. See build commands below and `docker/unsloth/README.md` (unsloth) or automodel docker docs. Set env vars **before** starting/restarting the platform. |

Image env vars are read when the platform starts (not per job):

```bash
export NMP_IMAGE_REGISTRY=<registry>
export NMP_IMAGE_TAG=<tag>
```

**Automodel** — also set `NMP_AUTOMODEL_IMAGE_REGISTRY=$NMP_IMAGE_REGISTRY`.

**Unsloth** — set `NMP_UNSLOTH_TRAINING_IMAGE` (and optionally `NMP_UNSLOTH_TASKS_IMAGE`) to the full built ref, then restart platform services so the env var takes effect.

### Build on the target host (unsloth)

Run on the **platform host** (SSH, console, or CI on that box — not from the agent when the platform is remote):

```bash
cd /path/to/nemo-platform

# Local build (platform and Docker on the same machine)
docker buildx bake \
  -f docker-bake.hcl \
  nmp-unsloth-training \
  --load \
  --set "*.platform=linux/amd64"

export NMP_UNSLOTH_TRAINING_IMAGE="${IMAGE_REGISTRY:-my-registry/nemo-platform-dev}/nmp-unsloth-training:${BAKE_TAG:-local}"
# Restart platform so the env var is picked up
nemo services restart
```

Or push to a registry the target can pull from — see **Option B** in `docker/unsloth/README.md` — then set `NMP_UNSLOTH_TRAINING_IMAGE` to that full ref before restart.

After the image is on the target, re-submit the same job JSON (use a fresh `output.name` if a prior partial run already registered an adapter).

### Report follow-up — missing image (remote platform)

When submit or poll returns a missing-image error and the base URL is **user-overridden**, start with the **Report to user** template in `SKILL.md` (status `error`, **Output adapter fileset (planned):**, Notes quoting the pull error and naming the target host). Then append these sections:

**What you need to do on the target host** — build or load the training image on the machine running the NeMo platform (where `docker info` works for the platform's daemon), set `NMP_UNSLOTH_TRAINING_IMAGE` or automodel image env vars, and restart platform services. Full steps: `docker/unsloth/README.md` (unsloth) or automodel docker docs.

**Re-submit after the image is available:**

```bash
export NEMO_BASE_URL=<user's platform URL>
cd /path/to/nemo-platform
uv run nemo customization <plugin> submit /tmp/job.json --workspace default [--profile <gpu-profile>]
```

Then poll until terminal status. Offer to re-submit once the user confirms the image is on the target — do not attempt a local Docker build from the agent for a remote platform.

## Unsloth submit errors

| Error / symptom | Cause | Fix |
|-----------------|-------|-----|
| `Unsloth does not support local run` | Used `run` instead of `submit` | `nemo customization unsloth submit <job.json> -w <workspace>` |
| `Unsloth training requires platform.runtime: docker` | Platform not configured for Docker GPU jobs | Start platform with Docker runtime and a GPU execution profile |
| Unknown execution profile | Default `gpu` profile missing or wrong | Re-list profiles; pass `--profile <exact-name>` on submit |
| Missing `nmp-unsloth-training` image / `Failed to pull image` / `manifest unknown` | Image not on the **platform host's** Docker daemon | **Remote platform** (`NEMO_BASE_URL` not localhost): tell user to build on the target — **do not** `docker build` locally. **Local platform**: build on same host; see **Missing training images** above and `docker/unsloth/README.md` |
| `torch.cuda.is_available()` False in training step logs | GPU not exposed to the container step | Confirm the execution profile is GPU-backed; check platform Docker GPU setup |
| Job stuck in `active` after training step completes | Upload / model-entity steps still running | Keep polling top-level status (same as automodel) |

See `plugins/nemo-unsloth/README.md` for the 4-step job flow (download → train → upload → model-entity).

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
| Poll job | `nemo jobs get-status <automodel\|unsloth>-<job-id>` |

Automodel:

| Action | Command |
|--------|---------|
| Submit | `nemo customization automodel submit <job.json> --workspace default` |
| Status | `nemo jobs get-status automodel-<job-id>` |
| Live schema | `nemo customization automodel explain` |

Unsloth:

| Action | Command |
|--------|---------|
| Submit | `nemo customization unsloth submit <job.json> --workspace default [--profile P] [--cluster C]` |
| Status | `nemo jobs get-status unsloth-<job-id>` |
| Live schema | `nemo customization unsloth explain` |
| Run (disabled) | `nemo customization unsloth run …` → hard-fails; use `submit` |

Both backends return a job id from `submit` — poll until top-level status is terminal (`completed`, `error`, or `cancelled`).
