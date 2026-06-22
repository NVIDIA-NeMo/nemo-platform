#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Check if minikube is running
if ! minikube status &>/dev/null; then
  echo "Minikube is not running. Starting minikube..."
  # Use the setup_local_minikube_gpu.sh script to start minikube,
  # and ensure the script is in the same directory as this script.
  
  "$SCRIPT_DIR/setup_local_minikube_gpu.sh"
fi

# Wait for minikube to be ready
minikube status

# Build the images with a local tag and then load them
# Use epoch seconds (date +%s) so each run gets a unique tag and upgrades pick up new images
IMAGE_TAG="${IMAGE_TAG:-local-$(date +%s)}"

# Detect platform for build (match host arch)
BUILD_ARCH="${BUILD_ARCH:-linux/$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')}"
GIT_SHA=$(git -C "${REPO_ROOT}" rev-parse HEAD)

echo "Building docker-cpu images with tag $IMAGE_TAG (platform=$BUILD_ARCH)..."

# Allow building directly into minikube's docker daemon
eval "$(minikube docker-env)"

# Set the image tag to the git sha
(
  cd "${REPO_ROOT}"
  CI_COMMIT_SHA="$GIT_SHA" \
    BAKE_TAG="$IMAGE_TAG" \
    IMAGE_REGISTRY="docker.io/my-registry" \
    BUILD_ARCH="$BUILD_ARCH" \
    docker buildx bake docker-cpu --set "*.platform=$BUILD_ARCH"
)


# Echo the image tags and an example script to run end-to-end tests
echo "Image tags:"
echo "  nmp-api: $IMAGE_TAG"
echo "  nmp-cpu-tasks: $IMAGE_TAG"
echo "  platform: $IMAGE_TAG"
echo "----------------------------------------"
echo "Example script to run end-to-end jobs tests:"
echo "  NMP_E2E_INTERNAL_HOST=nemo-platform-api:8080 NMP_E2E_REGISTRY=docker.io/my-registry NMP_E2E_TAG=$IMAGE_TAG uv run pytest e2e --kubernetes --cluster-url=http://localhost:80"
echo "----------------------------------------"
echo "To rerun the helm install/upgrade, run:"
echo "  helm upgrade --install nemo-platform k8s/helm/ -f e2e/k8s/values/local.yaml --set \"api.image.tag=$IMAGE_TAG\" --set \"core.image.tag=$IMAGE_TAG\" --set \"platformConfig.platform.image_tag=$IMAGE_TAG\""
echo "----------------------------------------"

# Install/upgrade the helm chart with image tags
helm upgrade --install nemo-platform k8s/helm/ \
  -f e2e/k8s/values/local.yaml \
  --set "api.image.tag=$IMAGE_TAG" \
  --set "core.image.tag=$IMAGE_TAG" \
  --set "platformConfig.platform.image_tag=$IMAGE_TAG"
