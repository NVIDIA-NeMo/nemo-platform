<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Custom Gym environment workflow

This directory contains a repeatable workflow for validating custom `wheels-v1` Gym environments
with NeMo Evaluator and OpenSandbox. The workflow prepares or accepts an environment, uploads it,
runs an evaluation, verifies the result, records evidence, and removes temporary Platform
resources. With no input flags it runs the bundled ASCII Tree example; developers can instead
provide any complete compatible environment and Gym dataset.

## What makes the environment custom?

The published `nmp-gym-host` image provides Gym and a standard `simple_agent`. It does not contain
the evaluation-specific code used here.

The default example builds and uploads a `wheels-v1` environment FileSet containing:

- a Python wheel that implements an ASCII Tree reward function; and
- a Gym resources server that extracts the model response and invokes that function.

Evaluator installs the wheel and launches the resources server inside a fresh OpenSandbox sandbox.
The workflow confirms that the uploaded resources server produced the persisted reward, which
demonstrates that Evaluator delivered and executed the selected custom environment.

The example data and scoring semantics come from `primeintellect/ascii-tree==0.1.5`. Prime Intellect
is an implementation detail of this fixture, not the workflow's interface. Its converter normally
produces an `adapter-wheels-v1` package for the unsupported `verifiers` runtime. This utility adapts
that output to Evaluator's supported `wheels-v1` format.

## Project layout

The workflow is organized into the following components:

- `run.py` is the command-line entry point.
- `workflow.py` coordinates generic preparation, upload, inference, evaluation, verification, and
  cleanup.
- `prerequisites.py` performs read-only workstation, cluster, configuration, and image checks.
- `prepare.py` validates and stages complete environment packages and datasets.
- `ascii_tree_example.py` converts the default fixture, builds its scorer wheel, and adapts its
  dataset.
- `submit.py` constructs the Evaluator job, waits for it, and validates downloaded results.
- `config.py` derives settings, temporary resource names, and evidence paths.
- `commands.py`, `artifacts.py`, and `console.py` contain shared helpers.
- `environment/` and `scorer/` contain the bundled example package and wheel source.
- `helm/` contains the values example for enabling the required sandboxed Gym configuration.

## Setup

### Prerequisites

The workflow expects an existing, correctly configured environment. Its prerequisite checks are
read-only; it does not install or upgrade Kubernetes components.

Required infrastructure and access:

- a non-production Kubernetes cluster with NeMo Platform installed;
- OpenSandbox installed and reachable from the Platform namespace;
- sandboxed Gym enabled in the Platform ConfigMap;
- an empty or absent `evaluator.sandbox_runtime_image`;
- the OpenSandbox API-key Secret in the Platform namespace;
- a registry pull Secret for the configured Platform images;
- a `ReadWriteMany` Platform files PVC;
- matching published `nmp-api`, `nmp-cpu-tasks`, and `nmp-gym-host` images at an immutable tag;
- a local checkout compatible with the deployed images;
- `uv`, Docker Buildx, `kubectl`, and Helm;
- workstation access to NGC and, for the default example, Prime Intellect Hub, GitHub, and Hugging
  Face; and
- an NVIDIA API key authorized for the selected Inference Hub model.

The `nmp-temp1` deployment in `nemo-dev-blue` already satisfies these prerequisites.
Before running the workflow there, follow the **Configure sandboxed Gym** steps to apply the
settings required by this test.

The defaults are:

- Helm release `nemo-platform` in namespace `nmp-temp1`;
- OpenSandbox service `opensandbox-server-crun` in namespace `opensandbox-system`;
- Secrets `opensandbox-server-crun-api-key` and `nvcrimagepullsecret`;
- PVC `nemo-platform-core-storage`;
- workspace `default`
- model entity `default/nvidia-meta-llama-3-3-70b-instruct`.

### Configure sandboxed Gym

Apply the example values to an existing Platform release before running the workflow. The
`--reuse-values` flag preserves the release's current image coordinates and unrelated settings.

```bash
export KUBECONFIG="${HOME}/teleport-kubeconfig.yaml"
export NMP_GYM_CUSTOM_NAMESPACE="${NMP_GYM_CUSTOM_NAMESPACE:-nmp-temp1}"
export NMP_GYM_CUSTOM_RELEASE="${NMP_GYM_CUSTOM_RELEASE:-nemo-platform}"
export GYM_VALUES=/tmp/gym-custom-environment-values.yaml

cp \
  plugins/nemo-evaluator/scripts/gym-custom-environment/helm/opensandbox-values.example.yaml \
  "$GYM_VALUES"

# Set the namespace used by the internal Platform API URL.
export INTERNAL_PLATFORM_API_URL="http://nemo-platform-api.${NMP_GYM_CUSTOM_NAMESPACE}.svc.cluster.local:8080"
yq -i '
  .platformConfig.evaluator.sandbox_policy_base_urls = [strenv(INTERNAL_PLATFORM_API_URL)]
' "$GYM_VALUES"

# Render against the live cluster first. Review this output locally; existing
# ConfigMap values can include sensitive configuration.
helm upgrade "$NMP_GYM_CUSTOM_RELEASE" k8s/helm \
  -n "$NMP_GYM_CUSTOM_NAMESPACE" \
  --reuse-values \
  -f "$GYM_VALUES" \
  --dry-run=server \
  --hide-secret

helm upgrade "$NMP_GYM_CUSTOM_RELEASE" k8s/helm \
  -n "$NMP_GYM_CUSTOM_NAMESPACE" \
  --reuse-values \
  -f "$GYM_VALUES" \
  --timeout 20m

# The Platform config is mounted with subPath, so restart consumers after the
# ConfigMap changes.
kubectl rollout restart deployment \
  -l "app.kubernetes.io/instance=${NMP_GYM_CUSTOM_RELEASE}" \
  -n "$NMP_GYM_CUSTOM_NAMESPACE"

kubectl rollout status deployment \
  -l "app.kubernetes.io/instance=${NMP_GYM_CUSTOM_RELEASE}" \
  -n "$NMP_GYM_CUSTOM_NAMESPACE" \
  --timeout 20m
```

Confirm that both Platform and Evaluator sandboxing are enabled and that
`sandbox_runtime_image` is empty:

```bash
kubectl get configmap nemo-platform-config \
  -n "$NMP_GYM_CUSTOM_NAMESPACE" \
  -o 'jsonpath={.data.config\.yaml}' |
  yq '.platform, .evaluator'
```

Optionally, override only values that differ:

```bash
export NMP_GYM_CUSTOM_NAMESPACE="<platform-namespace>"
export NMP_GYM_CUSTOM_RELEASE="<helm-release>"
export NMP_GYM_CUSTOM_WORKSPACE="<workspace>"
export NMP_GYM_CUSTOM_JOB_PVC="<read-write-many-pvc>"
export NMP_GYM_CUSTOM_REGISTRY_SECRET="<registry-pull-secret>"
export NMP_GYM_CUSTOM_OPENSANDBOX_NAMESPACE="<opensandbox-namespace>"
export NMP_GYM_CUSTOM_OPENSANDBOX_SERVICE="<opensandbox-service>"
export NMP_GYM_CUSTOM_OPENSANDBOX_API_SECRET="<opensandbox-api-key-secret>"
export NMP_GYM_CUSTOM_PLATFORM_API_SERVICE="<platform-api-service>"
export NMP_GYM_CUSTOM_MODEL_ENTITY_ID="<workspace>/<model-entity>"
export NMP_GYM_CUSTOM_LOCAL_PORT=18080
```

If Docker is not authenticated to NGC, log in without putting the key in shell history:

```bash
test -n "${NGC_API_KEY:-}" || {
  printf 'NGC API key: ' >&2
  IFS= read -rs NGC_API_KEY
  printf '\n' >&2
  export NGC_API_KEY
}

printf '%s' "$NGC_API_KEY" |
  docker login nvcr.io --username '$oauthtoken' --password-stdin
```

### Connect to the Platform API

The workflow accesses the Platform API through a local Kubernetes port-forward. It checks
`127.0.0.1:18080` first and reuses an existing healthy connection. If none exists, the workflow
starts a temporary port-forward automatically and closes it when the run finishes.

To manage the connection yourself, run the following in a separate terminal and leave it running
for the duration of the workflow:

```bash
export KUBECONFIG="${HOME}/teleport-kubeconfig.yaml"
export NMP_GYM_CUSTOM_NAMESPACE="${NMP_GYM_CUSTOM_NAMESPACE:-nmp-temp1}"
export NMP_GYM_CUSTOM_PLATFORM_API_SERVICE="${NMP_GYM_CUSTOM_PLATFORM_API_SERVICE:-nemo-platform-api}"
export NMP_GYM_CUSTOM_LOCAL_PORT="${NMP_GYM_CUSTOM_LOCAL_PORT:-18080}"

kubectl port-forward \
  -n "$NMP_GYM_CUSTOM_NAMESPACE" \
  "service/$NMP_GYM_CUSTOM_PLATFORM_API_SERVICE" \
  "$NMP_GYM_CUSTOM_LOCAL_PORT:8080"
```

## Run

### Bundled example

From the repository root, run the workflow without input flags to use the bundled ASCII Tree
example:

```bash
export KUBECONFIG="${HOME}/teleport-kubeconfig.yaml"

uv run --isolated --frozen \
  --package nemo-evaluator-plugin \
  --with-editable packages/filesets \
  --with-editable packages/models \
  python \
  plugins/nemo-evaluator/scripts/gym-custom-environment/run.py
```

The script securely prompts for the NVIDIA API key. For non-interactive use, export
`INFERENCE_NVIDIA_API_KEY` before running it.

The command runs the workflow in an isolated, package-scoped uv environment and does not modify
the repository `.venv`. Within that environment, the pinned Prime Intellect converter runs with
only its `conversion` extra. The workflow retains and caches only the two-row JSONL fixture,
discarding the converter's adapter package and dataset snapshot. The custom scorer wheel is also
cached by a digest of its source. Subsequent runs reuse both artifacts until their inputs change.

### A different custom environment

Supply a complete environment directory and its separate Gym JSONL dataset:

```bash
uv run --isolated --frozen \
  --package nemo-evaluator-plugin \
  --with-editable packages/filesets \
  --with-editable packages/models \
  python \
  plugins/nemo-evaluator/scripts/gym-custom-environment/run.py \
  --environment-dir path/to/environment \
  --dataset path/to/dataset.jsonl
```

The environment directory must:

- contain a valid `nemo-environment.yaml` with `format: wheels-v1`;
- contain every manifest-listed config and a non-empty, flat `wheels/` directory;
- declare at least one resources server; and
- remain separate from the JSONL dataset.

Every dataset row must satisfy Gym's dataset contract, including a
`responses_create_params` mapping. The workflow copies both inputs into its run directory and
does not modify the originals. If the package declares multiple resources servers, select one:

```bash
--resources-server <config-instance-name>
```

The evaluation uses the Gym host's standard `simple_agent`; custom packages provide the
resources server and its wheel-delivered dependencies.

The terminal shows seven numbered stages:

1. check workstation and cluster prerequisites;
2. prepare the custom environment;
3. create temporary Platform resources;
4. smoke-test the selected model;
5. run the custom Gym evaluation;
6. verify evaluation evidence; and
7. clean up temporary resources.

A successful run ends with:

```text
SUCCESS: Custom Gym environment evaluation passed
```

The model does not need a perfect reward. The workflow passes when the FileSet-provided resources
server returns a finite reward, persisted trial and metric values agree, image and OpenSandbox
lifecycle checks pass, and there are no failed or missing results.

## Evidence

Each invocation creates a unique `/tmp/nmp-gym-custom-environment-*` directory. Pass
`--run-dir <path>` to choose a different location. Important evidence includes:

- `evidence/run-summary.json`;
- `evidence/platform-config.json`;
- `evidence/job-status.json` and `evidence/job-logs.json`;
- `evidence/verification.json`;
- `evidence/agent-eval-results/summary.json`, `scores.jsonl`, and `trials.jsonl`;
- `evidence/nmp-api-image.txt`;
- `evidence/nmp-cpu-tasks-image.txt`; and
- `evidence/nmp-gym-host-image.txt`.

Evidence contains prompts and model responses but never the NVIDIA API key.

## Troubleshooting

- **An image cannot be inspected:** authenticate Docker to the configured registry and confirm all
  three images exist at the configured tag.
- **A stale Gym host override is reported:** clear `evaluator.sandbox_runtime_image` and restart
  API/controller deployments.
- **The PVC check fails:** configure `evaluator.sandbox_job_storage_pvc_claim` with a
  `ReadWriteMany` claim shared by task and sandbox pods.
- **The local API port is occupied:** set `NMP_GYM_CUSTOM_LOCAL_PORT` to another port.
- **The model is unavailable:** select an entity served by the temporary Inference Hub provider.
- **The job fails:** inspect `evidence/job-status.json` and `evidence/job-logs.json`.
