#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Install the shared-kernel OpenSandbox control plane on a running minikube cluster
# and copy the API-key Secret into the platform job namespace.
#
# The platform Helm chart does not install OpenSandbox. Run this after
# setup_local_minikube_gpu.sh (or setup_local_minikube_cpu.sh), then helm-upgrade
# the platform with sandboxClusterCapable=true.
#
# Usage:
#   OPENSANDBOX_DIR=/path/to/OpenSandbox ./e2e/k8s/scripts/install_opensandbox_minikube.sh
#
# Environment:
#   OPENSANDBOX_DIR   Required. Checkout with kubernetes/charts/{opensandbox-controller,opensandbox-server}
#   KUBE_NAMESPACE    Job / Helm-release namespace (default: default). Alias: NMP_NAMESPACE
#   MINIKUBE_PROFILE  (default: minikube)
#   SKIP_VERIFY=1     Skip k8s/helm/examples/opensandbox/verify/shared-kernel.sh
#   HELM_TIMEOUT      Helm --wait timeout (default: 10m)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
EXAMPLES="${REPO_ROOT}/k8s/helm/examples/opensandbox"
SYSTEM_NS="${SYSTEM_NS:-opensandbox-system}"
KUBE_NAMESPACE="${KUBE_NAMESPACE:-${NMP_NAMESPACE:-default}}"
NMP_NAMESPACE="${KUBE_NAMESPACE}"
MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-minikube}"
HELM_TIMEOUT="${HELM_TIMEOUT:-10m}"
API_SECRET="opensandbox-server-api-key"

for tool in kubectl helm openssl python3; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        log_error "${tool} is not installed. Please install it first."
        exit 1
    fi
done

if ! kubectl get node >/dev/null 2>&1; then
    log_error "kubectl cannot reach a cluster. Start minikube first:"
    log_error "  ./e2e/k8s/scripts/setup_local_minikube_gpu.sh"
    exit 1
fi

if [ -z "${OPENSANDBOX_DIR:-}" ]; then
    log_error "OPENSANDBOX_DIR is required (OpenSandbox checkout with kubernetes/charts/)."
    exit 1
fi
CONTROLLER_CHART="${OPENSANDBOX_DIR}/kubernetes/charts/opensandbox-controller"
SERVER_CHART="${OPENSANDBOX_DIR}/kubernetes/charts/opensandbox-server"
if [ ! -d "${CONTROLLER_CHART}" ] || [ ! -d "${SERVER_CHART}" ]; then
    log_error "OpenSandbox charts not found under ${OPENSANDBOX_DIR}/kubernetes/charts/"
    exit 1
fi

log_info "Installing shared-kernel OpenSandbox (control plane: ${SYSTEM_NS}, jobs: ${KUBE_NAMESPACE})"

kubectl create namespace "${SYSTEM_NS}" --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace "${KUBE_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

log_info "Applying BatchSandbox template ConfigMap..."
kubectl apply -f "${EXAMPLES}/batchsandbox-template.yaml"

if ! kubectl get secret nvcrimagepullsecret -n "${KUBE_NAMESPACE}" >/dev/null 2>&1; then
    log_error "Secret nvcrimagepullsecret is missing in ${KUBE_NAMESPACE}."
    log_error "The BatchSandbox template hard-codes that name. Run setup_local_minikube_gpu.sh first,"
    log_error "or create the pull Secret, or edit imagePullSecrets in ${EXAMPLES}/batchsandbox-template.yaml."
    exit 1
fi

if kubectl get secret "${API_SECRET}" -n "${SYSTEM_NS}" >/dev/null 2>&1; then
    log_info "Reusing existing ${API_SECRET} in ${SYSTEM_NS}"
else
    log_info "Creating ${API_SECRET} in ${SYSTEM_NS}"
    kubectl create secret generic "${API_SECRET}" \
      -n "${SYSTEM_NS}" \
      --from-literal=api-key="$(openssl rand -hex 32)"
fi

log_info "Copying ${API_SECRET} into job namespace ${KUBE_NAMESPACE}..."
kubectl get secret "${API_SECRET}" -n "${SYSTEM_NS}" -o json | python3 -c '
import json, sys
secret = json.load(sys.stdin)
for key in ("uid", "resourceVersion", "creationTimestamp", "namespace", "managedFields"):
    secret.get("metadata", {}).pop(key, None)
json.dump(secret, sys.stdout)
' | kubectl apply -n "${KUBE_NAMESPACE}" -f -

SERVER_VALUES="$(mktemp)"
trap 'rm -f "${SERVER_VALUES}"' EXIT
sed "s/REPLACE_WITH_RELEASE_NAMESPACE/${KUBE_NAMESPACE}/g" \
  "${EXAMPLES}/opensandbox-server.yaml" > "${SERVER_VALUES}"

log_info "Helm upgrade opensandbox-controller..."
helm upgrade --install opensandbox-controller "${CONTROLLER_CHART}" \
  --namespace "${SYSTEM_NS}" \
  --wait --timeout "${HELM_TIMEOUT}" \
  -f "${EXAMPLES}/opensandbox-controller.yaml"

log_info "Helm upgrade opensandbox-server..."
helm upgrade --install opensandbox-server "${SERVER_CHART}" \
  --namespace "${SYSTEM_NS}" \
  --wait --timeout "${HELM_TIMEOUT}" \
  -f "${SERVER_VALUES}"

if [ "${SKIP_VERIFY:-}" != "1" ]; then
    log_info "Verifying shared-kernel OpenSandbox..."
    OPEN_SANDBOX_WORKLOAD_NS="${KUBE_NAMESPACE}" \
      NMP_NAMESPACE="${KUBE_NAMESPACE}" \
      "${EXAMPLES}/verify/shared-kernel.sh"
fi

log_info "=========================================="
log_info "OpenSandbox shared-kernel install complete"
log_info "=========================================="
log_info "Control plane: ${SYSTEM_NS}"
log_info "Job namespace: ${KUBE_NAMESPACE}"
log_info "Service DNS:   opensandbox-server.${SYSTEM_NS}.svc.cluster.local"
log_info ""
log_info "Point the platform Helm release at the server (then helm upgrade):"
log_info "  sandboxClusterCapable: true"
log_info "  opensandbox:"
log_info "    domain: opensandbox-server.${SYSTEM_NS}.svc.cluster.local"
log_info "    protocol: http"
log_info "    apiKeySecret: ${API_SECRET}"
log_info "    apiKeySecretKey: api-key"
log_info ""
log_info "If you previously set sandboxed_gym_default=false to skip OpenSandbox, restore it to true."
