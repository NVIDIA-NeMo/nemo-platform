#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

ACTION="stack"
ACTION_SET="false"
COMPOSE_DIR="${SCRIPT_DIR}"
DRY_RUN="false"
IMAGE=""
IMAGE_REGISTRY="my-registry"
BAKE_TAG="local"

usage() {
    cat <<'EOF'
Usage:
  contrib/auth/authentik/run.sh [stack|down] [options]

Runs the local Authentik reference example.

Actions:
  stack                  Start NeMo, Authentik, and the gateway in the foreground.
  down                   Remove the example Compose stack and volumes.

Image options:
  --image IMAGE          Use an existing nmp-api image and skip local build.
                         Expected format: <registry>/nmp-api:<tag>

Other options:
  --compose-dir DIR      Compose directory. Default: this script's directory.
  --dry-run              Print commands without running them.
  -h, --help             Show this help.

Examples:
  contrib/auth/authentik/run.sh stack
  contrib/auth/authentik/run.sh stack --image my-registry/nmp-api:local
  contrib/auth/authentik/run.sh down
EOF
}

die() {
    echo "error: $*" >&2
    echo >&2
    usage >&2
    exit 2
}

image_ref() {
    printf "%s/nmp-api:%s" "${IMAGE_REGISTRY}" "${BAKE_TAG}"
}

parse_image() {
    local image="$1"

    if [[ "${image}" != */nmp-api:* ]]; then
        die "--image must use the form <registry>/nmp-api:<tag>"
    fi

    IMAGE_REGISTRY="${image%/nmp-api:*}"
    BAKE_TAG="${image##*:}"

    if [[ -z "${IMAGE_REGISTRY}" || -z "${BAKE_TAG}" ]]; then
        die "--image must include both a registry path and a tag"
    fi
}

quote_args() {
    local arg

    for arg in "$@"; do
        printf "%q " "${arg}"
    done
}

run_with_image_env_in_dir() {
    local dir="$1"
    shift

    if [[ "${DRY_RUN}" == "true" ]]; then
        printf "+ cd %q && IMAGE_REGISTRY=%s BAKE_TAG=%s " "${dir}" "${IMAGE_REGISTRY}" "${BAKE_TAG}"
        quote_args "$@"
        printf "\n"
        return
    fi

    (cd "${dir}" && IMAGE_REGISTRY="${IMAGE_REGISTRY}" BAKE_TAG="${BAKE_TAG}" "$@")
}

stack_up() {
    echo "Using existing NeMo API image: $(image_ref)"

    if [[ "${DRY_RUN}" == "true" ]]; then
        run_with_image_env_in_dir "${COMPOSE_DIR}" docker compose up
        return
    fi

    trap 'run_with_image_env_in_dir "${COMPOSE_DIR}" docker compose down -v' EXIT INT TERM
    run_with_image_env_in_dir "${COMPOSE_DIR}" docker compose up
}

compose_down() {
    run_with_image_env_in_dir "${COMPOSE_DIR}" docker compose down -v
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        stack | down)
            if [[ "${ACTION_SET}" == "true" ]]; then
                die "only one action can be specified"
            fi
            ACTION="$1"
            ACTION_SET="true"
            shift
            ;;
        --image)
            [[ $# -ge 2 ]] || die "--image requires a value"
            IMAGE="$2"
            shift 2
            ;;
        --compose-dir)
            [[ $# -ge 2 ]] || die "--compose-dir requires a value"
            COMPOSE_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            die "unknown argument: $1"
            ;;
    esac
done

if [[ -n "${IMAGE}" ]]; then
    parse_image "${IMAGE}"
fi

if [[ -z "${IMAGE_REGISTRY}" || -z "${BAKE_TAG}" ]]; then
    die "image registry and tag must be non-empty"
fi

case "${ACTION}" in
    stack)
        stack_up
        ;;
    down)
        compose_down
        ;;
esac
