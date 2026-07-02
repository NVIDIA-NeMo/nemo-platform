# rl backend — Kubernetes job execution requirement

The `rl` (DPO) backend runs **each job step as a Kubernetes pod** via the
`kubernetes_job` execution backend. This is different from `automodel` / `unsloth`,
which use the **docker** job backend. So the platform you submit against must be
deployed/configured for Kubernetes job execution — the docker job backend cannot
run rl, and `rl submit` fails fast (`require_distributed_runtime`) on a
docker-runtime platform.

Deployment model is the same as automodel/unsloth: **run the platform locally**
(`nemo services run` — never anything else). The only difference for rl is the
**execution backend** the local platform dispatches jobs to: `kubernetes_job`
(pointing at a Kubernetes GPU cluster via its kubeconfig) instead of `docker`.
What matters is that the platform's jobs backend is `kubernetes_job` and the job
pods can reach the platform's APIs.

## Step 1 — verify the connected platform qualifies (always do this first)

```bash
nemo jobs list-execution-profiles -f json
```

- `cpu` and `gpu` profiles report `backend: kubernetes_job` (or `volcano_job`) →
  the platform is ready for rl. Proceed to submit.
- They report `backend: docker` / `subprocess` → the platform is **not**
  configured for rl. Do **not** reuse it and do **not** fall back to
  automodel/unsloth (those are SFT/LoRA, not DPO). Instead, run the local
  platform configured for the `kubernetes_job` backend pointed at a Kubernetes
  GPU cluster (see **Configuring the local platform for rl** below). If **no**
  Kubernetes cluster is available to point at, stop and tell the user rl needs
  one.

## Configuring the local platform for rl

When you start the platform locally (`nemo services run`) for an rl job, it must
be configured with all of:

1. `platform.runtime: kubernetes`.
2. `jobs` `kubernetes_job` executors registered for **both** providers the
   customizer stamps — `cpu` (download / upload / model-entity steps) and `gpu`
   (DPO training) — at the resolved profile.
3. `platform.loopback_address` set to a platform address the **job pods can reach**
   (the platform rewrites the `NMP_*_URL` it injects into pods to this, so the
   download/upload steps can call the files/jobs APIs).
4. The target GPU cluster has, available as pullable/loaded images: the job-step
   images (`nmp-rl-tasks`, `nmp-rl-training`), the **jobs-launcher** image (each
   step runs a launcher init container), and a **job-storage PVC** the steps share.
5. Multi-node only (`parallelism.num_nodes > 1`): `NMP_RL_MULTINODE_SHARED_STORAGE_PATH`
   (a shared filesystem for Ray's cross-node coordination).

If a job pod shows `ErrImagePull` / `ImagePullBackOff` on the launcher init
container or a step image, that image isn't available in the cluster — surface it;
do not build/pull it as part of the customization workflow.

Reference (local platform config): `docs/set-up/manage-jobs.mdx` (execution
backends — `kubernetes_job`), `docs/set-up/config-reference.mdx`
(`platform.runtime`, `loopback_address`, `kubernetes_job` executor config).
