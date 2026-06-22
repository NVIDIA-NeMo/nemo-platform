#!/usr/bin/env bash
# Install the auth-enabled local E2E harness on minikube.
#
# Layers minikube-auth.yaml on top of minikube.yaml so auth-specific
# config stays minimal and doesn't duplicate base minikube values.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"

export NAMESPACE="${NAMESPACE:-${KUBE_NAMESPACE:-default}}"
export HELM_RELEASE_NAME="${HELM_RELEASE_NAME:-nemo-platform}"
export HELM_VALUES="${HELM_VALUES:-${REPO_ROOT}/e2e/k8s/values/minikube.yaml}"
export HELM_EXTRA_ARGS="${HELM_EXTRA_ARGS:-} -f ${REPO_ROOT}/e2e/k8s/values/minikube-auth.yaml"
export NMP_E2E_REGISTRY="${NMP_E2E_REGISTRY:-my-registry}"
export NMP_E2E_TAG="${NMP_E2E_TAG:-local}"
export POSTGRES_IMAGE="${POSTGRES_IMAGE:-docker.io/library/postgres}"
export BUSYBOX_IMAGE="${BUSYBOX_IMAGE:-busybox}"

export REQUIRE_NMP_E2E_IMAGES="${REQUIRE_NMP_E2E_IMAGES:-true}"

exec "${SCRIPT_DIR}/install_helm_e2e.sh"
