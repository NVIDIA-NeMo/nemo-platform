#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"

ACTION=""
COMPOSE_DIR="${SCRIPT_DIR}"
DRY_RUN="false"
IMAGE_SELECTED="$([[ -n "${IMAGE_REGISTRY:-}" || -n "${BAKE_TAG:-}" ]] && printf "true" || printf "false")"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-my-registry}"
BAKE_TAG="${BAKE_TAG:-local}"
TEST_LIFECYCLE="fresh"
TEST_LIFECYCLE_SET="false"
TEST_PLATFORM=""
TEST_PLATFORM_SET="false"
TEST_DOCKER_TARGET="nmp-api-docker"
COMPOSE_DIR_SET="false"

usage() {
    cat <<'EOF'
Usage:
  contrib/auth/authentik/run.sh stack [options]
  contrib/auth/authentik/run.sh down [options]
  contrib/auth/authentik/run.sh test [options]

Runs the local Authentik reference example or its auth-idp test suite.

Actions:
  stack                  Start NeMo, Authentik, and the gateway in the foreground.
  down                   Remove the example Compose stack and volumes.
  test                   Build the local test image if needed, then run auth-idp tests.

Image options:
  --image IMAGE          Use an existing nmp-api image.
                         Expected format: <registry>/nmp-api:<tag>

Test options:
  --lifecycle MODE       Docker Compose lifecycle for tests: fresh or reuse.
                         Default: fresh.
  --platform PLATFORM    Platform for the default local test image build.
                         Default: current machine architecture.

Other options:
  --compose-dir DIR      Compose directory for stack/down. Default: this script's directory.
  --dry-run              Print commands without running them.
  -h, --help             Show this help.

Examples:
  contrib/auth/authentik/run.sh stack
  contrib/auth/authentik/run.sh stack --image my-registry/nmp-api:local
  contrib/auth/authentik/run.sh test
  contrib/auth/authentik/run.sh test --lifecycle reuse
  contrib/auth/authentik/run.sh test --image my-registry/nmp-api:local
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
    IMAGE_SELECTED="true"

    if [[ -z "${IMAGE_REGISTRY}" || -z "${BAKE_TAG}" ]]; then
        die "--image must include both a registry path and a tag"
    fi
}

host_platform() {
    case "$(uname -m)" in
        x86_64 | amd64)
            printf "linux/amd64"
            ;;
        arm64 | aarch64)
            printf "linux/arm64"
            ;;
        *)
            die "unsupported host architecture for test image build: $(uname -m). Pass --platform explicitly."
            ;;
    esac
}

validate_test_lifecycle() {
    case "${TEST_LIFECYCLE}" in
        fresh | reuse)
            ;;
        *)
            die "--lifecycle must be fresh or reuse"
            ;;
    esac
}

quote_args() {
    local arg

    for arg in "$@"; do
        printf "%q " "${arg}"
    done
}

print_command_in_dir() {
    local dir="$1"
    shift

    printf "+ cd %q && " "${dir}"
    quote_args "$@"
    printf "\n"
}

run_with_image_env_in_dir() {
    local dir="$1"
    shift

    if [[ "${DRY_RUN}" == "true" ]]; then
        printf "+ cd %q && IMAGE_REGISTRY=%q BAKE_TAG=%q " "${dir}" "${IMAGE_REGISTRY}" "${BAKE_TAG}"
        quote_args "$@"
        printf "\n"
        return
    fi

    (cd "${dir}" && IMAGE_REGISTRY="${IMAGE_REGISTRY}" BAKE_TAG="${BAKE_TAG}" "$@")
}

run_in_repo() {
    if [[ "${DRY_RUN}" == "true" ]]; then
        print_command_in_dir "${REPO_ROOT}" "$@"
        return
    fi

    (cd "${REPO_ROOT}" && "$@")
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

build_default_test_image() {
    local platform="${TEST_PLATFORM:-$(host_platform)}"
    echo "Building auth-idp test image for ${platform}: $(image_ref)"
    run_in_repo make docker-load "DOCKER_TARGET=${TEST_DOCKER_TARGET}" "DOCKER_PLATFORMS=${platform}"
}

run_tests() {
    validate_test_lifecycle

    if [[ "${IMAGE_SELECTED}" == "true" ]]; then
        echo "Using prebuilt auth-idp test image: $(image_ref)"
    else
        build_default_test_image
    fi

    run_in_repo \
        env "IMAGE_REGISTRY=${IMAGE_REGISTRY}" "BAKE_TAG=${BAKE_TAG}" "NMP_E2E_COMPOSE_LIFECYCLE=${TEST_LIFECYCLE}" \
        uv run --frozen pytest tests/auth_idp -v --run-e2e
}

if [[ $# -eq 0 ]]; then
    usage
    exit 0
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        stack | down | test)
            if [[ -n "${ACTION}" ]]; then
                die "only one action can be specified"
            fi
            ACTION="$1"
            shift
            ;;
        --image)
            [[ $# -ge 2 ]] || die "--image requires a value"
            parse_image "$2"
            shift 2
            ;;
        --lifecycle)
            [[ $# -ge 2 ]] || die "--lifecycle requires a value"
            TEST_LIFECYCLE="$2"
            TEST_LIFECYCLE_SET="true"
            shift 2
            ;;
        --platform)
            [[ $# -ge 2 ]] || die "--platform requires a value"
            TEST_PLATFORM="$2"
            TEST_PLATFORM_SET="true"
            shift 2
            ;;
        --compose-dir)
            [[ $# -ge 2 ]] || die "--compose-dir requires a value"
            COMPOSE_DIR="$2"
            COMPOSE_DIR_SET="true"
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

if [[ -z "${ACTION}" ]]; then
    die "missing action"
fi

if [[ -z "${IMAGE_REGISTRY}" || -z "${BAKE_TAG}" ]]; then
    die "image registry and tag must be non-empty"
fi

if [[ "${ACTION}" != "test" ]]; then
    if [[ "${TEST_LIFECYCLE_SET}" == "true" ]]; then
        die "--lifecycle is only valid with the test action"
    fi
    if [[ "${TEST_PLATFORM_SET}" == "true" ]]; then
        die "--platform is only valid with the test action"
    fi
fi

if [[ "${ACTION}" == "test" && "${COMPOSE_DIR_SET}" == "true" ]]; then
    die "--compose-dir is only valid with stack or down"
fi

case "${ACTION}" in
    stack)
        stack_up
        ;;
    down)
        compose_down
        ;;
    test)
        run_tests
        ;;
esac
