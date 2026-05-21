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
| User asks for Unsloth | `unsloth` (if installed) |
| Response includes **`provider`: `gpu` or `gpu_distributed`** | **`automodel`** (default) |
| No GPU profiles (only `subprocess` and/or CPU `provider`) | Platform cannot schedule GPU container training → use **`unsloth`** locally if the user has a GPU, or report that remote automodel is unavailable |

Automodel training steps need a **GPU execution profile** on the platform. `subprocess` profiles run host commands and are not a substitute for automodel’s GPU container step.

### Pick `training.execution_profile`

When using automodel, set `training.execution_profile` in job JSON to the **`profile`** string of a GPU row from the list (e.g. `default`, `docker_gpu`). If omitted, the plugin default is usually `gpu` — submit errors mentioning an unknown profile mean you should re-list and set an exact name from the API.

Quick filter:

```bash
uv run nemo jobs list-execution-profiles -f json | python3 -c "
import sys, json
for p in json.load(sys.stdin):
    if p.get('provider') in ('gpu', 'gpu_distributed'):
        print(p['profile'], p.get('backend'), p.get('provider'))
"
```

Do not run `nemo customization --help` unless submit returns unknown plugin.

Automodel uses **`submit` only** (no `run`). Dataset refs in job JSON: `default/<fileset>`.

## Missing training images

Set **before** starting the platform (not per job):

```bash
export NMP_IMAGE_REGISTRY=<registry>
export NMP_IMAGE_TAG=<tag>
export NMP_AUTOMODEL_IMAGE_REGISTRY=$NMP_IMAGE_REGISTRY
```

Pull automodel images only when the job error mentions a missing image.

## CLI quick reference

| Action | Command |
|--------|---------|
| Execution profiles | `nemo jobs list-execution-profiles -f json` |
| Create dataset fileset | `nemo files filesets create <name> --workspace default --purpose dataset --exist-ok` |
| Create HF weights fileset | `nemo files filesets create <name> --workspace default --purpose model --exist-ok --storage '{"type":"huggingface","repo_id":"<repo>","repo_type":"model","revision":"main"}'` |
| Upload | `nemo files upload <local> <fileset> --workspace default --remote-path train.jsonl` |
| List files | `nemo files list <fileset> --workspace default` |
| Create model | `nemo models create <name> --workspace default --exist-ok --input-data '<json>'` |
| Submit | `nemo customization automodel submit <job.json> --workspace default` |
| Status | `nemo jobs get-status automodel-<id>` |
