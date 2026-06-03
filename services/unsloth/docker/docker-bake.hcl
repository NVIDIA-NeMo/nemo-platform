# nmp-unsloth bake — single image target.
#
# Run from the Platform repo root:
#
#   # Local build (no registry prefix, --load into local daemon):
#   docker buildx bake -f services/unsloth/docker/docker-bake.hcl nmp-unsloth-training --load
#
#   # Push to a registry:
#   IMAGE_REGISTRY=nvcr.io/0921617854601259/nemo-platform-dev \
#     docker buildx bake -f services/unsloth/docker/docker-bake.hcl nmp-unsloth-training --push
#
# Override via env vars:
#   IMAGE_REGISTRY   = registry+repo prefix (default: empty → bare `nmp-unsloth-training:TAG`)
#   IMAGE_TAG        = image tag           (default: local)
#   BUILD_PLATFORM   = OCI platform        (default: linux/amd64)

variable "IMAGE_REGISTRY" {
  default = ""
}

variable "IMAGE_TAG" {
  default = "local"
}

variable "BUILD_PLATFORM" {
  default = "linux/amd64"
}

# Named platform-workspace build context (built from the repo root). Each
# target consumes it via `contexts.platform-workspace`.
target "platform-workspace" {
  context    = "."
  dockerfile = "services/unsloth/docker/Dockerfile.platform-workspace"
  target     = "platform-workspace"
  output     = ["type=cacheonly"]
}

target "nmp-unsloth-training" {
  context    = "."
  dockerfile = "services/unsloth/docker/Dockerfile.nmp-unsloth-training"
  target     = "runtime"
  contexts = {
    platform-workspace = "target:platform-workspace"
  }
  # Tag with the registry prefix only when one is supplied; otherwise emit the
  # bare local name so the image lands as `nmp-unsloth-training:TAG` in the
  # daemon's image store.
  tags = [
    IMAGE_REGISTRY != "" ? "${IMAGE_REGISTRY}/nmp-unsloth-training:${IMAGE_TAG}" : "nmp-unsloth-training:${IMAGE_TAG}",
  ]
  platforms = ["${BUILD_PLATFORM}"]
}

group "default" {
  targets = ["nmp-unsloth-training"]
}
