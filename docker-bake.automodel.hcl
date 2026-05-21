# nmp-automodel image bake - run from Platform repo root (context = ".").
#
# Inspect targets (no build; finishes in ~0s):
#   docker buildx bake --print -f docker-bake.automodel.hcl nmp-automodel-gpu-wheels
#
# Build wheels (override registry/tag via env, not --set):
#   export WHEELS_REGISTRY=nvcr.io/0921617854601259/nemo-platform-dev
#   export WHEELS_TAG=$(git rev-parse --short HEAD)
#   docker buildx bake -f docker-bake.automodel.hcl nmp-automodel-gpu-wheels --push
#
# Build automodel images:
#   docker buildx bake -f docker-bake.automodel.hcl nmp-automodel-base-builder
#
# Published tags: nvcr.io/0921617854601259/nemo-platform-dev/nmp-automodel-{base,tasks,training}:<tag>
# NVCR allows only one repo segment after the registry prefix (no nmp/automodel-base nesting).

variable "IMAGE_REGISTRY" {
  default = "nvcr.io/0921617854601259/nemo-platform-dev"
}

variable "BASE_REGISTRY" {
  default = "nvcr.io/0921617854601259/nemo-platform-dev"
}

variable "WHEELS_REGISTRY" {
  default = "nvcr.io/0921617854601259/nemo-platform-dev"
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
  default = ["linux/arm64"]
}

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

# Pre-built mamba-ssm / causal-conv1d wheels (cp311, cp312, cu13.1.1). Pushed to WHEELS_REGISTRY.
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

target "platform-workspace" {
  target     = "platform-workspace"
  context    = "."
  dockerfile = "services/automodel/docker/Dockerfile.platform-workspace"
}

target "nmp-automodel-base-builder" {
  target          = "nmp-automodel-base-builder"
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
    platform-workspace = "target:platform-workspace"
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
    platform-workspace = "target:platform-workspace"
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
    platform-workspace = "target:platform-workspace"
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
    platform-workspace = "target:platform-workspace"
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
