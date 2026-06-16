#!/usr/bin/env bash
# Script: install_helm_e2e.sh
# Description: Installs NeMo Platform via Helm using e2e.yaml values (expects minikube cluster and secrets already set up)
# Usage: ./install_helm_e2e.sh
#
# Prerequisites: Run setup_local_minikube_gpu.sh first (or ensure minikube is running with ingress and secrets).
#
# Environment Variables:
#   MINIKUBE_PROFILE (optional) - Minikube profile name (defaults to minikube)
#   NMP_E2E_REGISTRY (optional) - Container image registry for NMP services (e.g. ghcr.io/nvidia-nemo/platform)
#   NMP_E2E_TAG (optional) - Container image tag for NMP services (e.g. a commit SHA)
#   HELM_CHART (optional) - Override the helm chart source (default: local k8s/helm)
#   HELM_VALUES_FILE (optional) - Override the default helm values file (default: e2e/k8s/values/default.yaml)
#   HELM_EXTRA_ARGS (optional) - Additional helm install/upgrade arguments (e.g. --set api.image.repository=...)
#   NGC_API_KEY (optional) - Required for helm dependency build (chart depends on NGC nvidia repo)

set -euo pipefail

MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-minikube}"
REPO_ROOT=$(git rev-parse --show-toplevel)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

log_info "Validating environment..."

for tool in kubectl helm curl; do
    if ! command -v $tool &> /dev/null; then
        log_error "$tool is not installed. Please install it first."
        exit 1
    fi
done

# Install RustFS for S3 storage scenarios
install_rustfs() {
    log_info "Installing RustFS for S3-compat storage..."

    # Add RustFS helm repo if not already added
    if ! helm repo list | grep -q "rustfs"; then
        helm repo add rustfs https://charts.rustfs.com
    fi
    helm repo update rustfs

    # Install RustFS in standalone mode for E2E testing
    # See https://github.com/rustfs/helm for parameter reference
    # Uses default credentials (rustfsadmin/rustfsadmin)
    helm upgrade -i rustfs rustfs/rustfs \
        --version 0.0.85 \
        --set mode.standalone.enabled=true \
        --set mode.distributed.enabled=false \
        --set ingress.className=nginx \
        --set storageclass.name=standard \
        --timeout 5m

    # Wait for RustFS to be ready (needs time for image pull + 30s readiness delay)
    log_info "Waiting for RustFS pod to be ready..."
    if ! kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=rustfs --timeout=300s; then
        log_error "RustFS pod failed to become ready"
        kubectl describe pods -l app.kubernetes.io/name=rustfs || true
        kubectl logs -l app.kubernetes.io/name=rustfs --tail=50 || true
        return 1
    fi
    log_info "RustFS is ready"

    # Create the test bucket using aws-cli
    log_info "Creating E2E test bucket in RustFS..."
    if ! kubectl run aws-cli --rm -i --restart=Never \
        --image=amazon/aws-cli:2.22.35 \
        --pod-running-timeout=2m \
        --env="AWS_ACCESS_KEY_ID=rustfsadmin" \
        --env="AWS_SECRET_ACCESS_KEY=rustfsadmin" \
        -- --endpoint-url http://rustfs-svc:9000 s3 mb s3://e2e-k8s-test; then
        log_error "Failed to create E2E test bucket in RustFS"
        return 1
    fi
    log_info "E2E test bucket created successfully"
}

if ! minikube status -p "${MINIKUBE_PROFILE}" &> /dev/null; then
    log_error "Minikube cluster is not running. Run setup_local_minikube_gpu.sh first."
    exit 1
fi

log_info "Installing NeMo Platform via Helm..."

HELM_CHART="${HELM_CHART:-${REPO_ROOT}/k8s/helm}"
HELM_VALUES="${HELM_VALUES_FILE:-${REPO_ROOT}/e2e/k8s/values/default.yaml}"
HELM_ARGS=(
    nemo-platform
    "${HELM_CHART}"
    -f "${HELM_VALUES}"
    --timeout 15m
    --wait
)

if [ -n "${NMP_E2E_REGISTRY:-}" ]; then
    log_info "Using image registry: ${NMP_E2E_REGISTRY}"
    HELM_ARGS+=(
        --set "api.image.repository=${NMP_E2E_REGISTRY}/nmp-api"
        --set "core.image.repository=${NMP_E2E_REGISTRY}/nmp-api"
        --set-string "platformConfig.platform.image_registry=${NMP_E2E_REGISTRY}"
    )
fi

if [ -n "${NMP_E2E_TAG:-}" ]; then
    log_info "Using image tag: ${NMP_E2E_TAG}"
    HELM_ARGS+=(
        --set "api.image.tag=${NMP_E2E_TAG}"
        --set "core.image.tag=${NMP_E2E_TAG}"
        --set-string "platformConfig.platform.image_tag=${NMP_E2E_TAG}"
    )
fi

# Append any extra helm args (applied last, so they can override anything above).
# Note: HELM_EXTRA_ARGS is word-split, so values must not contain spaces.
if [ -n "${HELM_EXTRA_ARGS:-}" ]; then
    # shellcheck disable=SC2206
    HELM_ARGS+=(${HELM_EXTRA_ARGS})

    # If using s3-rustfs scenario, install RustFS first
    if echo "${HELM_EXTRA_ARGS}" | grep -q "s3-rustfs"; then
        install_rustfs
    fi
fi

log_info "Helm chart: ${HELM_CHART}"
log_info "Helm values file: ${HELM_VALUES}"

# Chart depends on k8s-nim-operator from NGC; add repo so dependency build can fetch it
if ! helm repo list 2>/dev/null | grep -q "helm.ngc.nvidia.com"; then
    if [ -z "${NGC_API_KEY:-}" ]; then
        log_error "NGC_API_KEY is required to add the NGC Helm repo (needed for chart dependencies). Export NGC_API_KEY and re-run."
        exit 1
    fi
    log_info "Adding NGC Helm repo for chart dependencies..."
    helm repo add nvidia https://helm.ngc.nvidia.com/nvidia --username='$oauthtoken' --password="${NGC_API_KEY}"
fi
helm repo update nvidia 2>/dev/null || true

helm dependency build "${HELM_CHART}"

if ! helm upgrade -i "${HELM_ARGS[@]}"; then
    log_error "Helm install/upgrade failed (possible timeout). Collecting diagnostics..."
    "$(dirname "$0")/collect_k8s_logs.sh"
    exit 1
fi

log_info "Helm values from chart (nemo-platform):"
helm get values nemo-platform

log_info "Verifying deployment..."
kubectl get pods -o wide

MINIKUBE_IP=$(minikube ip -p "${MINIKUBE_PROFILE}")
CLUSTER_URL="http://${MINIKUBE_IP}"

if curl -f -s --max-time 10 "${CLUSTER_URL}/cluster-info" > /dev/null 2>&1; then
    log_info "Cluster info endpoint check passed"
else
    log_warn "Could not reach cluster-info endpoint"
fi

log_info "=========================================="
log_info "NeMo Platform Helm Install Complete!"
log_info "=========================================="
log_info ""
log_info "Cluster URL: ${CLUSTER_URL}"
log_info ""
log_info "To run e2e GPU tests:"
log_info "  NMP_E2E_INTERNAL_HOST=nemo-platform-api:8080 uv run --project platform --frozen pytest e2e --kubernetes --feature gpu --cluster-url=\"${CLUSTER_URL}\" -v"
log_info "=========================================="
