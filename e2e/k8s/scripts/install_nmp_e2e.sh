#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)

NAMESPACE="${NAMESPACE:-default}"
HELM_RELEASE_NAME="${HELM_RELEASE_NAME:-nemo-platform}"
NMP_E2E_REGISTRY="${NMP_E2E_REGISTRY:-}"
NMP_E2E_TAG="${NMP_E2E_TAG:-}"
HELM_EXTRA_ARGS="${HELM_EXTRA_ARGS:-}"
HELM_CHART="${HELM_CHART:-${REPO_ROOT}/k8s/helm}"
HELM_VALUES="${HELM_VALUES:-${HELM_VALUES_FILE:-${REPO_ROOT}/e2e/k8s/values/default.yaml}}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-docker.io/library/postgres}"
BUSYBOX_IMAGE="${BUSYBOX_IMAGE:-docker.io/library/busybox}"
RELEASE_READY_SCRIPT="${RELEASE_READY_SCRIPT:-${REPO_ROOT}/e2e/k8s/scripts/wait_for_release_ready.sh}"
EXTRA_HELM_ARGS=()

require_non_empty() {
    local name="$1"
    if [ -z "${!name:-}" ]; then
        echo "${name} is required for ${HELM_RELEASE_NAME} Helm install" >&2
        exit 1
    fi
}

require_non_empty NAMESPACE
require_non_empty HELM_RELEASE_NAME
require_non_empty NMP_E2E_REGISTRY
require_non_empty NMP_E2E_TAG
require_non_empty HELM_CHART
require_non_empty HELM_VALUES
require_non_empty POSTGRES_IMAGE
require_non_empty BUSYBOX_IMAGE
require_non_empty RELEASE_READY_SCRIPT

if [ ! -d "${HELM_CHART}" ]; then
    echo "HELM_CHART does not exist or is not a directory: ${HELM_CHART}" >&2
    exit 1
fi

if [ ! -f "${HELM_VALUES}" ]; then
    echo "HELM_VALUES does not exist or is not a file: ${HELM_VALUES}" >&2
    exit 1
fi

if [ ! -x "${RELEASE_READY_SCRIPT}" ]; then
    echo "RELEASE_READY_SCRIPT does not exist or is not executable: ${RELEASE_READY_SCRIPT}" >&2
    exit 1
fi

if [ -n "${HELM_EXTRA_ARGS}" ]; then
    read -r -a EXTRA_HELM_ARGS <<< "${HELM_EXTRA_ARGS}"
fi

HELM_ARGS=(
    "${HELM_RELEASE_NAME}"
    "${HELM_CHART}"
    -n "${NAMESPACE}"
    -f "${HELM_VALUES}"
    "${EXTRA_HELM_ARGS[@]}"
    --set api.image.repository="${NMP_E2E_REGISTRY}/nmp-api"
    --set api.image.tag="${NMP_E2E_TAG}"
    --set core.image.repository="${NMP_E2E_REGISTRY}/nmp-api"
    --set core.image.tag="${NMP_E2E_TAG}"
    --set-string platformConfig.platform.image_registry="${NMP_E2E_REGISTRY}"
    --set-string platformConfig.platform.image_tag="${NMP_E2E_TAG}"
    --set postgresql.image.repository="${POSTGRES_IMAGE}"
    --set core.storage.volumePermissionsImage="${BUSYBOX_IMAGE}"
    --create-namespace
    --timeout 15m
)

echo "Helm install inputs:"
printf '  release: %s\n' "${HELM_RELEASE_NAME}"
printf '  namespace: %s\n' "${NAMESPACE}"
printf '  chart: %s\n' "${HELM_CHART}"
printf '  values: %s\n' "${HELM_VALUES}"
printf '  api image: %s/nmp-api:%s\n' "${NMP_E2E_REGISTRY}" "${NMP_E2E_TAG}"
printf '  core image: %s/nmp-api:%s\n' "${NMP_E2E_REGISTRY}" "${NMP_E2E_TAG}"
printf '  platform image registry: %s\n' "${NMP_E2E_REGISTRY}"
printf '  platform image tag: %s\n' "${NMP_E2E_TAG}"
printf '  postgres image: %s\n' "${POSTGRES_IMAGE}"
printf '  core storage volume permissions image: %s\n' "${BUSYBOX_IMAGE}"
if [ -n "${HELM_EXTRA_ARGS}" ]; then
    printf '  extra Helm args: %s\n' "${HELM_EXTRA_ARGS}"
fi

# Install NMP platform
if ! helm upgrade -i "${HELM_ARGS[@]}"; then
    echo "--- helm list -A ---"
    helm list -A || true
    echo "--- helm status ${NAMESPACE}/${HELM_RELEASE_NAME} ---"
    helm status -n "${NAMESPACE}" "${HELM_RELEASE_NAME}" || true
    echo "--- kubectl get pods -A ---"
    kubectl get pods -A
    echo "--- kubectl describe pods -n ${NAMESPACE} ---"
    kubectl describe pods -n "${NAMESPACE}"
    exit 1
fi

if ! "${RELEASE_READY_SCRIPT}"; then
    echo "--- helm list -A ---"
    helm list -A || true
    echo "--- helm status ${NAMESPACE}/${HELM_RELEASE_NAME} ---"
    helm status -n "${NAMESPACE}" "${HELM_RELEASE_NAME}" || true
    echo "--- kubectl get pods -A ---"
    kubectl get pods -A
    echo "--- kubectl describe pods -n ${NAMESPACE} ---"
    kubectl describe pods -n "${NAMESPACE}"
    exit 1
fi
