#!/usr/bin/env bash
# Script: setup_local_kind_cpu.sh
# Description: Sets up a local kind cluster for CPU-only Kubernetes E2E tests.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"

KIND_CLUSTER_NAME="${KIND_CLUSTER_NAME:-nmp-e2e}"
KIND_NODE_IMAGE="${KIND_NODE_IMAGE:-kindest/node:v1.33.7@sha256:d26ef333bdb2cbe9862a0f7c3803ecc7b4303d8cea8e814b481b09949d353040}"
KUBE_NAMESPACE="${KUBE_NAMESPACE:-default}"
KUBE_GATEWAY_NAME="${KUBE_GATEWAY_NAME:-nmp-e2e-gateway}"
CLOUD_PROVIDER_KIND_VERSION="${CLOUD_PROVIDER_KIND_VERSION:-v0.10.0}"
GATEWAY_API_VERSION="${GATEWAY_API_VERSION:-v1.4.1}"
CLOUD_PROVIDER_KIND_CONTAINER="cloud-provider-kind-${KIND_CLUSTER_NAME}"

for tool in kind docker kubectl helm; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        log_error "$tool is not installed. Please install it first."
        exit 1
    fi
done

if [ -z "${NGC_API_KEY:-}" ]; then
    log_error "NGC_API_KEY environment variable is required"
    exit 1
fi

if ! kind get clusters 2>/dev/null | grep -Fxq "${KIND_CLUSTER_NAME}"; then
    log_info "Creating kind cluster ${KIND_CLUSTER_NAME}..."
    kind create cluster --name "${KIND_CLUSTER_NAME}" --image "${KIND_NODE_IMAGE}"
else
    log_info "kind cluster ${KIND_CLUSTER_NAME} already exists"
    kubectl config use-context "kind-${KIND_CLUSTER_NAME}" >/dev/null
fi

log_info "Allowing LoadBalancer traffic to control-plane nodes..."
kubectl label nodes --all node.kubernetes.io/exclude-from-external-load-balancers- >/dev/null 2>&1 || true

if ! kubectl api-resources --api-group=networking.k8s.io | awk '{print $1}' | grep -Fxq "servicecidrs"; then
    log_error "Kubernetes ServiceCIDR API is not available. cloud-provider-kind ${CLOUD_PROVIDER_KIND_VERSION} requires a kind node image with Kubernetes 1.33 or newer."
    log_error "Current node image setting: ${KIND_NODE_IMAGE}"
    exit 1
fi

log_info "Installing Gateway API CRDs (${GATEWAY_API_VERSION})..."
kubectl apply --server-side -f "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml"

log_info "Starting cloud-provider-kind (${CLOUD_PROVIDER_KIND_VERSION})..."
docker rm -f "${CLOUD_PROVIDER_KIND_CONTAINER}" >/dev/null 2>&1 || true
docker run -d --name "${CLOUD_PROVIDER_KIND_CONTAINER}" --rm \
    --network host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    "registry.k8s.io/cloud-provider-kind/cloud-controller-manager:${CLOUD_PROVIDER_KIND_VERSION}" \
    --gateway-channel standard >/dev/null

log_info "Waiting for Gateway API CRDs and GatewayClass..."
kubectl wait --for=condition=Established crd/gateways.gateway.networking.k8s.io --timeout=2m
kubectl wait --for=condition=Established crd/httproutes.gateway.networking.k8s.io --timeout=2m

for attempt in $(seq 1 60); do
    if kubectl get gatewayclass cloud-provider-kind >/dev/null 2>&1; then
        break
    fi
    if [ "${attempt}" -eq 60 ]; then
        log_error "Timed out waiting for GatewayClass cloud-provider-kind"
        docker logs "${CLOUD_PROVIDER_KIND_CONTAINER}" || true
        exit 1
    fi
    sleep 2
done

if [ "${KUBE_NAMESPACE}" != "default" ]; then
    log_info "Creating namespace ${KUBE_NAMESPACE}..."
    kubectl create namespace "${KUBE_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
fi

KUBECTL_NS=(kubectl -n "${KUBE_NAMESPACE}")

log_info "Creating Kubernetes secrets in namespace ${KUBE_NAMESPACE}..."
create_platform_secrets "${KUBE_NAMESPACE}"

log_info "Creating Gateway ${KUBE_NAMESPACE}/${KUBE_GATEWAY_NAME}..."
kubectl apply -f - <<EOF
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: ${KUBE_GATEWAY_NAME}
  namespace: ${KUBE_NAMESPACE}
spec:
  gatewayClassName: cloud-provider-kind
  listeners:
    - name: http
      protocol: HTTP
      port: 80
      allowedRoutes:
        namespaces:
          from: Same
EOF

log_info "Gateway created; it will be programmed after the chart creates its HTTPRoute."

if [ -n "${GITHUB_ENV:-}" ]; then
    {
        echo "KIND_CLUSTER_NAME=${KIND_CLUSTER_NAME}"
        echo "KUBE_GATEWAY_NAME=${KUBE_GATEWAY_NAME}"
        echo "NMP_E2E_CLUSTER_URL="
    } >> "${GITHUB_ENV}"
fi

log_info "=========================================="
log_info "kind E2E cluster is ready"
log_info "=========================================="
log_info "Cluster: ${KIND_CLUSTER_NAME}"
log_info "Namespace: ${KUBE_NAMESPACE}"
log_info "Gateway: ${KUBE_GATEWAY_NAME}"
log_info "Cluster URL: assigned after Helm install programs the Gateway"
log_info "cloud-provider-kind container: ${CLOUD_PROVIDER_KIND_CONTAINER}"
log_info "=========================================="
