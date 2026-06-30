#!/usr/bin/env bash
# Build Docker images locally and deploy to minikube via Helm.
#
# This script handles the build step, then delegates the Helm install to
# install_helm_e2e.sh so install logic lives in one place.
#
# Environment variables:
#   MINIKUBE_PROFILE  - minikube profile name (default: minikube)
#   NMP_REGISTRY      - image registry (default: docker.io/my-registry)
#   IMAGE_TAG         - image tag (default: local-<epoch>)
#   BUILD_ARCH        - target platform (default: auto-detected from host)
#   HELM_VALUES       - values file (default: e2e/k8s/values/minikube.yaml)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-minikube}"

# Check if minikube is running
if ! minikube status -p "${MINIKUBE_PROFILE}" &>/dev/null; then
  echo "Minikube profile ${MINIKUBE_PROFILE} is not running. Starting..."
  MINIKUBE_PROFILE="${MINIKUBE_PROFILE}" "$SCRIPT_DIR/setup_local_minikube_cpu.sh"
fi

# Wait for minikube to be ready
minikube status -p "${MINIKUBE_PROFILE}"

# Use epoch seconds so each run gets a unique tag and upgrades pick up new images
IMAGE_TAG="${IMAGE_TAG:-local-$(date +%s)}"

# Detect platform for build (match host arch)
BUILD_ARCH="${BUILD_ARCH:-linux/$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')}"
GIT_SHA=$(git -C "${REPO_ROOT}" rev-parse HEAD)

NMP_REGISTRY="${NMP_REGISTRY:-docker.io/my-registry}"

echo "Building docker-cpu images with tag $IMAGE_TAG (platform=$BUILD_ARCH)..."

# Build directly into minikube's docker daemon
eval "$(minikube -p "${MINIKUBE_PROFILE}" docker-env)"

(
  cd "${REPO_ROOT}"
  CI_COMMIT_SHA="$GIT_SHA" \
    BAKE_TAG="$IMAGE_TAG" \
    IMAGE_REGISTRY="${NMP_REGISTRY}" \
    BUILD_ARCH="$BUILD_ARCH" \
    docker buildx bake docker-cpu --set "*.platform=$BUILD_ARCH"
)

echo "----------------------------------------"
echo "Images built with tag: $IMAGE_TAG"
echo "----------------------------------------"

# Delegate helm install to install_helm_e2e.sh
export HELM_VALUES="${HELM_VALUES:-${REPO_ROOT}/e2e/k8s/values/minikube.yaml}"
export NMP_E2E_REGISTRY="${NMP_REGISTRY}"
export NMP_E2E_TAG="${IMAGE_TAG}"
export NMP_E2E_PULL_POLICY="Never"
export MINIKUBE_PROFILE
export REQUIRE_NMP_E2E_IMAGES=true

exec "$SCRIPT_DIR/install_helm_e2e.sh"
