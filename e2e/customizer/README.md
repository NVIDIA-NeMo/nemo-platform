# Customizer GPU e2e tests

End-to-end coverage for the three customizer backends, exercising the full
**train → deploy → evaluate** pipeline against a real GPU cluster:

| Test | Backend | Training | Dataset | Uplift metric |
|------|---------|----------|---------|---------------|
| `test_automodel.py::test_automodel_sft_uplift[lora]` | automodel | SFT + LoRA | `rajpurkar/squad` | F1 vs gold span |
| `test_automodel.py::test_automodel_sft_uplift[all_weights]` | automodel | SFT full-weight | `rajpurkar/squad` | F1 vs gold span |
| `test_unsloth.py::test_unsloth_lora_uplift` | unsloth | SFT + LoRA | `rajpurkar/squad` | F1 vs gold span |
| `test_rl_dpo.py::test_rl_dpo_uplift` | rl | DPO | `nvidia/HelpSteer3` | F1 vs preferred response (proxy) |

Each test fine-tunes a small model, deploys it on **vLLM** (`engine="vllm"`), and
runs a **deterministic** (no-LLM-judge) evaluation comparing the tuned model against
the base model on a held-out validation split. LoRA adapters are evaluated on a
single `lora_enabled` base deployment (the adapter hot-reloads); full-weight and DPO
outputs are deployed as their own entities.

## Why these don't run in CI

They require GPUs, which `nemo-platform` CI does not have. They are gated by a
`gpu` pytest marker that only activates with `--feature gpu`; the `kind-cpu-e2e` /
`make test-e2e` jobs never pass it, so the tests are **skipped** there (they also
carry `container_only`, so they skip without `NMP_BASE_URL`). Run them manually.

## Prerequisites

- A GPU-enabled cluster with the platform deployed via Helm (see below).
- The customizer **GPU images must be present in the cluster's container runtime**.
  These are all-manual runs, so build them **locally into minikube's docker daemon**
  (no registry needed) and deploy the platform at that registry/tag with a
  `Never` pull policy:

  ```bash
  eval "$(minikube -p minikube docker-env)"
  IMAGE_REGISTRY=local/nemo-platform BAKE_TAG=local BUILD_ARCH=linux/amd64 USE_LOCAL_WHEELS=1 \
    make docker-load TARGET="docker-cpu nmp-automodel nmp-unsloth nmp-rl"
  ```

  `USE_LOCAL_WHEELS=1` builds the mamba-ssm / causal-conv1d wheels from source in the
  same graph (no internal registry needed). Then point the platform at those images
  via `install_helm_e2e.sh` (`NMP_E2E_REGISTRY=local/nemo-platform NMP_E2E_TAG=local
  NMP_E2E_PULL_POLICY=Never`). This is heavy but runs fine on the GPU box.
- `NGC_API_KEY` (NIM/base-image pulls) and, for gated HF models, an `hf-token`
  secret. Base models here (`Qwen/*`, `unsloth/*`) are public.

## Run

```bash
NMP_BASE_URL=http://localhost:30080 \
  uv run --frozen pytest e2e/customizer --kubernetes --feature gpu --run-e2e -v
# or:  NMP_E2E_CLUSTER_URL=http://localhost:30080 make test-e2e-kubernetes-gpu-customizer
```

`--cluster-url` / `NMP_E2E_CLUSTER_URL` is bridged to `NMP_BASE_URL` automatically.

### Cluster option A — local GPU box / in-pod minikube

```bash
bash e2e/k8s/scripts/setup_local_minikube_gpu.sh
# Build all images into minikube's docker daemon (see Prerequisites), then:
HELM_VALUES=e2e/k8s/values/minikube.yaml \
  NMP_E2E_REGISTRY=local/nemo-platform NMP_E2E_TAG=local NMP_E2E_PULL_POLICY=Never \
  bash e2e/k8s/scripts/install_helm_e2e.sh
```

### Cluster option B — dev-blue GPU pod

Use `nmptool dev-machine` to create a GPU pod, then run option A **inside** the pod.
See the K8s Developer Guide §4 ("Dev-blue box"). The suite runs inside the pod
against `http://localhost:30080`.

## Environment knobs

| Variable | Default | Meaning |
|----------|---------|---------|
| `NMP_BASE_URL` / `NMP_E2E_CLUSTER_URL` | — | Platform URL (required). |
| `E2E_N_TRAIN` / `E2E_N_VAL` | `3000` / `300` | Dataset slice sizes. Lower for a faster smoke run. |
| `E2E_REQUIRE_UPLIFT` | unset | `1` → assert strict `tuned > base`; default asserts non-regression within tolerance (tiny runs rarely show large, stable uplift). |
| `E2E_GPU_TEST_TIMEOUT` | `5400` | Per-test timeout (seconds). |
| `NGC_API_KEY` | — | NIM / base-image pulls. |

## Notes / cluster-validated details

- **rl** skips itself unless the platform reports a `kubernetes_job` / `volcano_job`
  execution backend (a Helm-deployed k8s platform does).
- Datasets are downloaded once per session via HuggingFace `datasets`; the base
  models and (LoRA) adapters are served through the provider gateway by deployment
  name. Deployments are torn down after each eval to free the GPU.
