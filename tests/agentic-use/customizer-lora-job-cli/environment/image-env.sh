#!/bin/bash
# Platform and nmp-automodel image registry/tag defaults for agentic GPU evals.
#
# Host operators typically bake images with:
#   export BAKE_TAG=$(git rev-parse --short HEAD)
#   export BASE_TAG_AUTOMODEL=$BAKE_TAG
#   export NMP_IMAGE_TAG=$BAKE_TAG
#   export NMP_IMAGE_REGISTRY=my-registry/nemo-platform-dev
#
# Override any variable before starting the eval container when testing a
# different tag or registry.

if [ -z "${BAKE_TAG:-}" ]; then
  if command -v git >/dev/null 2>&1 && git -C /app rev-parse --short HEAD >/dev/null 2>&1; then
    BAKE_TAG="$(git -C /app rev-parse --short HEAD)"
  else
    BAKE_TAG="${NMP_IMAGE_TAG:-local}"
  fi
fi

export BAKE_TAG
export BASE_TAG_AUTOMODEL="${BASE_TAG_AUTOMODEL:-$BAKE_TAG}"
export NMP_IMAGE_TAG="${NMP_IMAGE_TAG:-$BAKE_TAG}"
export NMP_IMAGE_REGISTRY="${NMP_IMAGE_REGISTRY:-my-registry/nemo-platform-dev}"
export NMP_AUTOMODEL_IMAGE_REGISTRY="${NMP_AUTOMODEL_IMAGE_REGISTRY:-$NMP_IMAGE_REGISTRY}"
