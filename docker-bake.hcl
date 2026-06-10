# NeMo Platform GPU image bake — run from Platform repo root (context = ".").
#
# Groups:
#   nmp-automodel-gpu-wheels   causal-conv1d-wheel, mamba-ssm-wheel
#   nmp-automodel              base, tasks, training, smoke-test targets
#   nmp-unsloth                nmp-unsloth-training
#
# Automodel — inspect wheels (no build):
#   docker buildx bake --print -f docker-bake.hcl nmp-automodel-gpu-wheels
#
# Automodel — build and push wheels:
#   export WHEELS_REGISTRY=my-registry/nemo-platform-dev
#   export WHEELS_TAG=$(git rev-parse --short HEAD)
#   docker buildx bake -f docker-bake.hcl nmp-automodel-gpu-wheels --push
#
# Automodel — build runtime images:
#   docker buildx bake -f docker-bake.hcl nmp-automodel-base-builder
#
# Unsloth — local build (--load):
#   docker buildx bake -f docker-bake.hcl nmp-unsloth-training --load \
#     --set "*.platform=linux/amd64"
#
# Unsloth — push to registry:
#   export IMAGE_REGISTRY=my-registry/nemo-platform-dev
#   export BAKE_TAG=$(git rev-parse --short HEAD)
#   docker buildx bake -f docker-bake.hcl nmp-unsloth-training --push \
#     --set "*.platform=linux/amd64"
#
# Published tags:
#   ${IMAGE_REGISTRY}/nmp-automodel-{base,tasks,training}:${BAKE_TAG}
#   ${IMAGE_REGISTRY}/nmp-unsloth-training:${BAKE_TAG}

# ---------------------------------------------------------------------------
# Shared / automodel variables
# ---------------------------------------------------------------------------

variable "IMAGE_REGISTRY" {
  default = "my-registry/nemo-platform-dev"
}

variable "BASE_REGISTRY" {
  default = "my-registry/nemo-platform-dev"
}

variable "WHEELS_REGISTRY" {
  default = "my-registry/nemo-platform-dev"
}

variable "BAKE_TAG" {
  default = "local"
}

variable "BASE_TAG_AUTOMODEL" {
  default = "local"
}

variable "WHEELS_TAG" {
  default = "3fd6986ff173b598446ffac06d9be3f84b482495"
}

variable "CUDA_VERSION" {
  default = "12.8.1"
}

variable "MAMBA_22_COMMIT" {
  default = "6b32be06d026e170b3fdaf3ae6282c5a6ff57b06"
}

variable "MAMBA_23_COMMIT" {
  default = "v2.3.0"
}

variable "CAUSAL_CONV1D_VERSION" {
  default = "v1.5.3"
}

# For local builds: --set "*.platform=linux/amd64"
variable "BUILD_PLATFORMS" {
  default = ["linux/amd64", "linux/arm64"]
}

# ---------------------------------------------------------------------------
# Automodel helpers
# ---------------------------------------------------------------------------

function "wheel_tags" {
  params = [name]
  result = ["${WHEELS_REGISTRY}/${name}:${WHEELS_TAG}"]
}

function "get_causal_conv1d_wheel_image" {
  params = []
  result = "${WHEELS_REGISTRY}/causal-conv1d-wheel:${WHEELS_TAG}"
}

function "get_mamba_ssm_wheel_image" {
  params = []
  result = "${WHEELS_REGISTRY}/mamba-ssm-wheel:${WHEELS_TAG}"
}

# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

group "nmp-automodel-gpu-wheels" {
  targets = [
    "causal-conv1d-wheel",
    "mamba-ssm-wheel",
  ]
}

group "nmp-automodel" {
  targets = [
    "nmp-automodel-base-builder",
    "nmp-automodel-tasks-docker",
    "nmp-automodel-training-docker",
    "nmp-automodel-tasks-smoke-test",
    "nmp-automodel-training-smoke-test",
  ]
}

group "nmp-unsloth" {
  targets = ["nmp-unsloth-training"]
}

# ---------------------------------------------------------------------------
# Automodel — GPU wheels
# ---------------------------------------------------------------------------

target "causal-conv1d-wheel" {
  target     = "causal-conv1d-wheel"
  context    = "."
  dockerfile = "services/automodel/docker/Dockerfile.mamba-wheel"
  tags       = wheel_tags("causal-conv1d-wheel")
  args = {
    CUDA_VERSION          = CUDA_VERSION
    CAUSAL_CONV1D_VERSION = CAUSAL_CONV1D_VERSION
  }
  platforms = BUILD_PLATFORMS
}

target "mamba-ssm-wheel" {
  target     = "mamba-ssm-wheel"
  context    = "."
  dockerfile = "services/automodel/docker/Dockerfile.mamba-wheel"
  tags       = wheel_tags("mamba-ssm-wheel")
  args = {
    CUDA_VERSION    = CUDA_VERSION
    MAMBA_22_COMMIT = MAMBA_22_COMMIT
    MAMBA_23_COMMIT = MAMBA_23_COMMIT
  }
  platforms = BUILD_PLATFORMS
}

target "automodel-platform-workspace" {
  target     = "platform-workspace"
  context    = "."
  dockerfile = "services/automodel/docker/Dockerfile.platform-workspace"
  platforms = BUILD_PLATFORMS
}

target "nmp-automodel-base-builder" {
  target          = "nmp-automodel-base"
  context         = "."
  dockerfile      = "services/automodel/docker/Dockerfile.nmp-automodel-base"
  no-cache-filter = ["automodel-clone"]
  tags            = ["${IMAGE_REGISTRY}/nmp-automodel-base:${BAKE_TAG}"]
  args = {
    CAUSAL_CONV1D_WHEEL_IMAGE = get_causal_conv1d_wheel_image()
    MAMBA_SSM_WHEEL_IMAGE     = get_mamba_ssm_wheel_image()
  }
  platforms = BUILD_PLATFORMS
}

target "nmp-automodel-tasks-docker" {
  target     = "runtime"
  context    = "."
  dockerfile = "services/automodel/docker/Dockerfile.nmp-automodel-tasks"
  contexts = {
    platform-workspace = "target:automodel-platform-workspace"
    nmp-automodel-base = "target:nmp-automodel-base-builder"
  }
  tags = ["${IMAGE_REGISTRY}/nmp-automodel-tasks:${BAKE_TAG}"]
  args = {
    BASE_REGISTRY      = BASE_REGISTRY
    BASE_TAG_AUTOMODEL = BASE_TAG_AUTOMODEL
  }
  platforms = BUILD_PLATFORMS
}

target "nmp-automodel-training-docker" {
  target     = "runtime"
  context    = "."
  dockerfile = "services/automodel/docker/Dockerfile.nmp-automodel-training"
  contexts = {
    platform-workspace = "target:automodel-platform-workspace"
    nmp-automodel-base = "target:nmp-automodel-base-builder"
  }
  tags = ["${IMAGE_REGISTRY}/nmp-automodel-training:${BAKE_TAG}"]
  args = {
    BASE_REGISTRY      = BASE_REGISTRY
    BASE_TAG_AUTOMODEL = BASE_TAG_AUTOMODEL
  }
  platforms = BUILD_PLATFORMS
}

target "nmp-automodel-tasks-smoke-test" {
  target     = "smoke-test"
  context    = "."
  dockerfile = "services/automodel/docker/Dockerfile.nmp-automodel-tasks"
  contexts = {
    platform-workspace = "target:automodel-platform-workspace"
    nmp-automodel-base = "target:nmp-automodel-base-builder"
  }
  args = {
    BASE_REGISTRY      = BASE_REGISTRY
    BASE_TAG_AUTOMODEL = BASE_TAG_AUTOMODEL
    SMOKE_MARKER       = "smoke_nmp_automodel_tasks"
  }
  output    = ["type=cacheonly"]
  platforms = BUILD_PLATFORMS
}

target "nmp-automodel-training-smoke-test" {
  target     = "smoke-test"
  context    = "."
  dockerfile = "services/automodel/docker/Dockerfile.nmp-automodel-training"
  contexts = {
    platform-workspace = "target:automodel-platform-workspace"
    nmp-automodel-base = "target:nmp-automodel-base-builder"
  }
  args = {
    BASE_REGISTRY      = BASE_REGISTRY
    BASE_TAG_AUTOMODEL = BASE_TAG_AUTOMODEL
    SMOKE_MARKER       = "smoke_nmp_automodel_training"
  }
  output    = ["type=cacheonly"]
  platforms = BUILD_PLATFORMS
}

# ---------------------------------------------------------------------------
# Unsloth
# ---------------------------------------------------------------------------

target "unsloth-platform-workspace" {
  context    = "."
  dockerfile = "services/unsloth/docker/Dockerfile.platform-workspace"
  target     = "platform-workspace"
  output     = ["type=cacheonly"]
  platforms = BUILD_PLATFORMS
}

target "nmp-unsloth-training" {
  context    = "."
  dockerfile = "services/unsloth/docker/Dockerfile.nmp-unsloth-training"
  target     = "runtime"
  contexts = {
    platform-workspace = "target:unsloth-platform-workspace"
  }
  tags = ["${IMAGE_REGISTRY}/nmp-unsloth-training:${BAKE_TAG}"]
  platforms = BUILD_PLATFORMS
}
