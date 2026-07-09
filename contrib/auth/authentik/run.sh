#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AUTHENTIK_ROOT="${SCRIPT_DIR}"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"

ACTION=""
COMPOSE_DIR="${AUTHENTIK_ROOT}/compose"
DRY_RUN="false"
IMAGE_SELECTED="false"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-my-registry}"
BAKE_TAG="${BAKE_TAG:-local}"
TEST_LIFECYCLE="fresh"
REUSE_SET="false"
TEST_PLATFORM=""
TEST_PLATFORM_SET="false"
TEST_DOCKER_TARGET="nmp-api-docker"
COMPOSE_DIR_SET="false"
REUSE_COMPOSE_PROJECT_NAME="${NMP_AUTHENTIK_COMPOSE_PROJECT_NAME:-authentik-e2e-reuse}"
REUSE_COMPOSE_GATEWAY_PORT="${NMP_AUTHENTIK_COMPOSE_GATEWAY_PORT:-18083}"
REUSE_COMPOSE_GATEWAY_TLS_VOLUME="${NMP_AUTHENTIK_COMPOSE_GATEWAY_TLS_VOLUME:-authentik-e2e-${REUSE_COMPOSE_GATEWAY_PORT}-gateway-tls}"
REUSE_COMPOSE_WORKLOAD_NETWORK_NAME="${NMP_AUTHENTIK_COMPOSE_WORKLOAD_NETWORK_NAME:-authentik-e2e-${REUSE_COMPOSE_GATEWAY_PORT}-workload}"
REUSE_K8S_CLUSTER_NAME="${NMP_AUTHENTIK_K8S_REUSE_CLUSTER_NAME:-nmp-authentik-reuse}"
K8S_GATEWAY_PORT="${NMP_AUTHENTIK_K8S_GATEWAY_PORT:-18082}"
K8S_JUNIT_XML="${NMP_AUTHENTIK_K8S_JUNIT_XML:-report-auth-idp-kubernetes.xml}"
HELM_NAMESPACE="${HELM_NAMESPACE:-${NMP_AUTHENTIK_K8S_NAMESPACE:-nemo-authentik}}"
HELM_RELEASE="${HELM_RELEASE:-${NMP_AUTHENTIK_K8S_HELM_RELEASE:-authentik-demo}}"
K8S_CLUSTER_NAME="${NMP_AUTHENTIK_K8S_CLUSTER_NAME:-}"
K8S_RUNTIME="${NMP_AUTHENTIK_K8S_RUNTIME:-kind}"
K8S_RUNTIME_SET="false"
K8S_KEEP_CLUSTER="${NMP_AUTHENTIK_K8S_KEEP_CLUSTER:-0}"
K8S_REUSE_CLUSTER="${NMP_AUTHENTIK_K8S_REUSE_CLUSTER:-0}"
K8S_SKIP_IMAGE_LOAD="${NMP_AUTHENTIK_K8S_SKIP_IMAGE_LOAD:-0}"
K8S_SKIP_IMAGE_LOAD_SET="false"
K8S_NGC_EXISTING_SECRET="${NMP_AUTHENTIK_K8S_NGC_EXISTING_SECRET:-}"
K8S_IMAGE_PULL_SECRET="${NMP_AUTHENTIK_K8S_IMAGE_PULL_SECRET:-}"

diagnostics_dir() {
    local mode="$1"
    local configured="${E2E_SERVICES_LOG_DIR:-}"
    local timestamp

    if [[ -n "${configured}" ]]; then
        if [[ "${configured}" = /* ]]; then
            printf "%s" "${configured}"
        else
            printf "%s/%s" "${REPO_ROOT}" "${configured#./}"
        fi
        return
    fi

    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    printf "%s/docker/logs/authentik-%s/%s" "${REPO_ROOT}" "${mode}" "${timestamp}"
}

prepare_diagnostics_dir() {
    local mode="$1"
    local output

    output="$(diagnostics_dir "${mode}")"
    if [[ "${DRY_RUN}" != "true" ]]; then
        mkdir -p "${output}"
    fi
    printf "%s" "${output}"
}

write_diagnostics_metadata() {
    local mode="$1"
    local output="$2"

    if [[ "${DRY_RUN}" == "true" ]]; then
        return
    fi

    {
        printf "mode=%s\n" "${mode}"
        printf "timestamp_utc=%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf "image=%s\n" "$(image_ref)"
        printf "test_lifecycle=%s\n" "${TEST_LIFECYCLE}"
        printf "k8s_runtime=%s\n" "${K8S_RUNTIME}"
        printf "k8s_cluster_name=%s\n" "${K8S_CLUSTER_NAME}"
        printf "k8s_gateway_port=%s\n" "${K8S_GATEWAY_PORT}"
        printf "k8s_namespace=%s\n" "${HELM_NAMESPACE}"
        printf "k8s_release=%s\n" "${HELM_RELEASE}"
    } >"${output}/run-metadata.txt"
}

usage() {
    cat <<'EOF'
Usage:
  contrib/auth/authentik/run.sh run-local [options]
  contrib/auth/authentik/run.sh down [options]
  contrib/auth/authentik/run.sh prepare-local [options]
  contrib/auth/authentik/run.sh compose [options]
  contrib/auth/authentik/run.sh render-blueprint [options]
  contrib/auth/authentik/run.sh k8s [options]

Runs the local Authentik reference example or its auth-idp test suite.

Actions:
  run-local              Start NeMo, Authentik, and the gateway in the foreground.
  down                   Remove the example Compose stack, reused test Compose stack,
                         and reused Kubernetes test cluster.
  prepare-local          Create generated local inputs without starting Compose.
  compose                Build the local test image if needed, then run Compose auth-idp tests.
  render-blueprint       Copy the checked-in Authentik blueprint into generated inputs.
  k8s                    Run the Helm-based kind/k3d Kubernetes E2E test.

Image options:
  --image IMAGE          Use an existing nmp-api image.
                         Expected format: <registry>/nmp-api:<tag>

Test options:
  --reuse                Reuse a deterministic test environment.
                         For compose, use Compose project authentik-e2e-reuse
                         on gateway port 18083.
                         For k8s, use cluster nmp-authentik-reuse with
                         the selected runtime, creating it if needed and
                         keeping it after the run.
                         The k8s runner uses gateway port 18082 by default
                         to avoid the tutorial's 18081 port. Override with
                         NMP_AUTHENTIK_K8S_GATEWAY_PORT.
  --platform PLATFORM    Platform for the default local test image build.
                         Applies to compose and k8s.
                         Default: current machine architecture.
  --runtime RUNTIME      Kubernetes runtime for k8s/down: kind or k3d.
                         Default: kind.
  --skip-image-load      Do not load the nmp-api image into the reused cluster.
                         For a fresh cluster, use only with an explicit pullable
                         --image.

Other options:
  --compose-dir DIR      Compose directory for run-local/down. Default: contrib/auth/authentik/compose.
  --dry-run              Print commands without running them.
  -h, --help             Show this help.

Examples:
  contrib/auth/authentik/run.sh run-local
  contrib/auth/authentik/run.sh run-local --image my-registry/nmp-api:local
  contrib/auth/authentik/run.sh prepare-local
  contrib/auth/authentik/run.sh compose
  contrib/auth/authentik/run.sh compose --reuse
  contrib/auth/authentik/run.sh compose --image my-registry/nmp-api:local
  contrib/auth/authentik/run.sh render-blueprint
  contrib/auth/authentik/run.sh k8s
  contrib/auth/authentik/run.sh k8s --runtime k3d
  contrib/auth/authentik/run.sh k8s --reuse
  contrib/auth/authentik/run.sh k8s --reuse --skip-image-load
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
            die "test lifecycle must be fresh or reuse"
            ;;
    esac
}

validate_k8s_runtime() {
    case "${K8S_RUNTIME}" in
        kind | k3d)
            ;;
        *)
            die "--runtime must be kind or k3d"
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

print_command() {
    printf "+ "
    quote_args "$@"
    printf "\n"
}

blueprint_output_dir() {
    local configured="${AUTHENTIK_BLUEPRINT_DIR:-./.generated/blueprints}"
    if [[ "${configured}" = /* ]]; then
        printf "%s" "${configured}"
    else
        printf "%s/%s" "${AUTHENTIK_ROOT}" "${configured#./}"
    fi
}

workload_token_private_key_file() {
    printf "%s/.generated/workload-token-private-key.pem" "${AUTHENTIK_ROOT}"
}

gateway_tls_dir() {
    local configured="${AUTHENTIK_GATEWAY_TLS_DIR:-./.generated/gateway-tls}"
    if [[ "${configured}" = /* ]]; then
        printf "%s" "${configured}"
    else
        printf "%s/%s" "${AUTHENTIK_ROOT}" "${configured#./}"
    fi
}

gateway_tls_cert_file() {
    printf "%s/tls.crt" "$(gateway_tls_dir)"
}

gateway_tls_key_file() {
    printf "%s/tls.key" "$(gateway_tls_dir)"
}

ensure_gateway_tls_certificate() {
    local output_dir
    local cert
    local key
    local openssl_config

    output_dir="$(gateway_tls_dir)"
    cert="$(gateway_tls_cert_file)"
    key="$(gateway_tls_key_file)"
    openssl_config="${output_dir}/openssl.cnf"

    if [[ -f "${cert}" && -f "${key}" ]]; then
        echo "Using gateway TLS certificate: ${cert}"
        return
    fi

    if [[ "${DRY_RUN}" == "true" ]]; then
        printf "+ mkdir -p %q\n" "${output_dir}"
        printf "+ write %q\n" "${openssl_config}"
        printf "+ openssl req -x509 -newkey rsa:2048 -nodes -keyout %q -out %q -days 365 -sha256 -config %q -extensions v3_req\n" "${key}" "${cert}" "${openssl_config}"
        printf "+ chmod 600 %q\n" "${key}"
        printf "+ chmod 644 %q\n" "${cert}"
        return
    fi

    if ! command -v openssl >/dev/null 2>&1; then
        die "openssl is required to generate the gateway TLS certificate"
    fi

    mkdir -p "${output_dir}"
    cat >"${openssl_config}" <<'EOF'
[req]
prompt = no
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = nemo-gateway

[v3_req]
basicConstraints = critical, CA:TRUE
keyUsage = critical, digitalSignature, keyEncipherment, keyCertSign
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = nemo-gateway
IP.1 = 127.0.0.1
EOF
    openssl req -x509 -newkey rsa:2048 -nodes -keyout "${key}" -out "${cert}" -days 365 -sha256 -config "${openssl_config}" -extensions v3_req >/dev/null 2>&1
    chmod 600 "${key}"
    chmod 644 "${cert}"
    echo "Generated gateway TLS certificate: ${cert}"
}

ensure_workload_token_private_key() {
    local output
    local output_dir

    output="$(workload_token_private_key_file)"
    output_dir="$(dirname -- "${output}")"

    if [[ -f "${output}" ]]; then
        echo "Using workload token signing key: ${output}"
        return
    fi

    if [[ "${DRY_RUN}" == "true" ]]; then
        printf "+ mkdir -p %q\n" "${output_dir}"
        printf "+ openssl genrsa -out %q 2048\n" "${output}"
        printf "+ chmod 600 %q\n" "${output}"
        return
    fi

    if ! command -v openssl >/dev/null 2>&1; then
        die "openssl is required to generate the workload token signing key"
    fi

    mkdir -p "${output_dir}"
    openssl genrsa -out "${output}" 2048 >/dev/null 2>&1
    chmod 600 "${output}"
    echo "Generated workload token signing key: ${output}"
}

render_blueprint() {
    local source="${AUTHENTIK_ROOT}/helm/files/blueprints/nemo.yaml"
    local output_dir
    local output

    output_dir="$(blueprint_output_dir)"
    output="${output_dir}/nemo.yaml"

    if [[ ! -f "${source}" ]]; then
        die "missing Authentik blueprint: ${source}"
    fi

    if [[ "${DRY_RUN}" == "true" ]]; then
        printf "+ mkdir -p %q\n" "${output_dir}"
        printf "+ cp %q %q\n" "${source}" "${output}"
        return
    fi

    mkdir -p "${output_dir}"
    cp "${source}" "${output}"
    echo "Copied Authentik blueprint: ${output}"
}

authentik_workload_identity_password() {
    printf "%s" "${AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD:-svc-nemo-token-secret-e2e}"
}

run_with_compose_env_in_dir() {
    local dir="$1"
    shift

    if [[ "${DRY_RUN}" == "true" ]]; then
        printf "+ cd %q && IMAGE_REGISTRY=%q BAKE_TAG=%q AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD=<redacted> " "${dir}" "${IMAGE_REGISTRY}" "${BAKE_TAG}"
        quote_args "$@"
        printf "\n"
        return
    fi

    (
        cd "${dir}" &&
            IMAGE_REGISTRY="${IMAGE_REGISTRY}" \
                BAKE_TAG="${BAKE_TAG}" \
                AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD="$(authentik_workload_identity_password)" \
                "$@"
    )
}

run_with_reuse_compose_env_in_dir() {
    local dir="$1"
    shift

    if [[ "${DRY_RUN}" == "true" ]]; then
        printf "+ cd %q && IMAGE_REGISTRY=%q BAKE_TAG=%q AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD=<redacted> " "${dir}" "${IMAGE_REGISTRY}" "${BAKE_TAG}"
        printf "COMPOSE_PROJECT_NAME=%q AUTHENTIK_GATEWAY_PORT=%q AUTHENTIK_GATEWAY_TLS_VOLUME=%q AUTHENTIK_WORKLOAD_NETWORK_NAME=%q " \
            "${REUSE_COMPOSE_PROJECT_NAME}" \
            "${REUSE_COMPOSE_GATEWAY_PORT}" \
            "${REUSE_COMPOSE_GATEWAY_TLS_VOLUME}" \
            "${REUSE_COMPOSE_WORKLOAD_NETWORK_NAME}"
        quote_args "$@"
        printf "\n"
        return
    fi

    (
        cd "${dir}" &&
            IMAGE_REGISTRY="${IMAGE_REGISTRY}" \
                BAKE_TAG="${BAKE_TAG}" \
                AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD="$(authentik_workload_identity_password)" \
                COMPOSE_PROJECT_NAME="${REUSE_COMPOSE_PROJECT_NAME}" \
                AUTHENTIK_GATEWAY_PORT="${REUSE_COMPOSE_GATEWAY_PORT}" \
                AUTHENTIK_GATEWAY_TLS_VOLUME="${REUSE_COMPOSE_GATEWAY_TLS_VOLUME}" \
                AUTHENTIK_WORKLOAD_NETWORK_NAME="${REUSE_COMPOSE_WORKLOAD_NETWORK_NAME}" \
                "$@"
    )
}

run_in_repo() {
    if [[ "${DRY_RUN}" == "true" ]]; then
        print_command_in_dir "${REPO_ROOT}" "$@"
        return
    fi

    (cd "${REPO_ROOT}" && "$@")
}

prepare_local() {
    render_blueprint
    ensure_workload_token_private_key
    ensure_gateway_tls_certificate
}

run_local() {
    echo "Using existing NeMo API image: $(image_ref)"
    prepare_local

    if [[ "${DRY_RUN}" == "true" ]]; then
        run_with_compose_env_in_dir "${COMPOSE_DIR}" docker compose up
        return
    fi

    trap 'run_with_compose_env_in_dir "${COMPOSE_DIR}" docker compose down -v' EXIT INT TERM
    run_with_compose_env_in_dir "${COMPOSE_DIR}" docker compose up
}

compose_down() {
    local status=0

    run_with_compose_env_in_dir "${COMPOSE_DIR}" docker compose down -v --remove-orphans || status="$?"
    run_with_reuse_compose_env_in_dir "${COMPOSE_DIR}" docker compose down -v --remove-orphans || status="$?"
    return "${status}"
}

delete_reuse_k8s_cluster() {
    local cluster_name="${K8S_CLUSTER_NAME:-${REUSE_K8S_CLUSTER_NAME}}"
    local -a delete_command
    local status

    validate_k8s_runtime

    case "${K8S_RUNTIME}" in
        kind)
            delete_command=(kind delete cluster --name "${cluster_name}")
            ;;
        k3d)
            delete_command=(k3d cluster delete "${cluster_name}")
            ;;
    esac

    if [[ "${DRY_RUN}" == "true" ]]; then
        print_command "${delete_command[@]}"
        return
    fi

    if ! command -v "${delete_command[0]}" >/dev/null 2>&1; then
        echo "Skipping reused Kubernetes test cluster cleanup: ${delete_command[0]} not found"
        return
    fi

    set +e
    "${delete_command[@]}"
    status="$?"
    set -e
    if [[ "${status}" -ne 0 ]]; then
        echo "Warning: failed to delete reused Kubernetes test cluster ${cluster_name} with ${K8S_RUNTIME}" >&2
    fi
}

down() {
    local status=0

    compose_down || status="$?"
    delete_reuse_k8s_cluster || status="$?"
    return "${status}"
}

build_default_test_image() {
    local platform="${TEST_PLATFORM:-$(host_platform)}"
    echo "Building auth-idp test image for ${platform}: $(image_ref)"
    run_in_repo make docker-load "DOCKER_TARGET=${TEST_DOCKER_TARGET}" "DOCKER_PLATFORMS=${platform}"
}

run_pytest_with_diagnostics() {
    local diagnostics="$1"
    local status
    shift

    if [[ "${DRY_RUN}" == "true" ]]; then
        print_command_in_dir "${REPO_ROOT}" "$@"
        return
    fi

    set +e
    (
        cd "${REPO_ROOT}"
        set +e
        "$@" 2>&1 | tee "${diagnostics}/pytest.log"
        status="${PIPESTATUS[0]}"
        set -e
        exit "${status}"
    )
    status="$?"
    set -e
    return "${status}"
}

run_tests() {
    local workload_identity_password="${AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD:-svc-nemo-token-secret-e2e}"
    local diagnostics
    local compose_project_name=""
    local compose_gateway_port=""
    local status

    validate_test_lifecycle
    ensure_workload_token_private_key
    if [[ "${TEST_LIFECYCLE}" == "reuse" ]]; then
        compose_project_name="${REUSE_COMPOSE_PROJECT_NAME}"
        compose_gateway_port="${REUSE_COMPOSE_GATEWAY_PORT}"
    fi
    diagnostics="$(prepare_diagnostics_dir compose)"
    write_diagnostics_metadata compose "${diagnostics}"
    echo "Auth-idp Compose diagnostics: ${diagnostics}"

    if [[ "${IMAGE_SELECTED}" == "true" ]]; then
        echo "Using prebuilt auth-idp test image: $(image_ref)"
    else
        build_default_test_image
    fi

    if [[ "${DRY_RUN}" == "true" ]]; then
        run_pytest_with_diagnostics "${diagnostics}" \
            env "IMAGE_REGISTRY=${IMAGE_REGISTRY}" "BAKE_TAG=${BAKE_TAG}" \
            "AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD=<redacted>" \
            "E2E_SERVICES_LOG_DIR=${diagnostics}" \
            "NMP_E2E_COMPOSE_LIFECYCLE=${TEST_LIFECYCLE}" \
            "NMP_AUTHENTIK_COMPOSE_PROJECT_NAME=${compose_project_name}" \
            "NMP_AUTHENTIK_COMPOSE_GATEWAY_PORT=${compose_gateway_port}" \
            "NMP_CLIENT_SSL_CERT_FILE=$(gateway_tls_cert_file)" \
            uv run --frozen pytest tests/auth_idp/contracts -v --auth-idp-runtime authentik-compose -m auth_idp_runtime
        return
    fi

    echo "Writing Authentik Compose diagnostics to: ${diagnostics}"
    run_pytest_with_diagnostics "${diagnostics}" \
        env "IMAGE_REGISTRY=${IMAGE_REGISTRY}" \
        "BAKE_TAG=${BAKE_TAG}" \
        "AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD=${workload_identity_password}" \
        "E2E_SERVICES_LOG_DIR=${diagnostics}" \
        "NMP_E2E_COMPOSE_LIFECYCLE=${TEST_LIFECYCLE}" \
        "NMP_AUTHENTIK_COMPOSE_PROJECT_NAME=${compose_project_name}" \
        "NMP_AUTHENTIK_COMPOSE_GATEWAY_PORT=${compose_gateway_port}" \
        "NMP_CLIENT_SSL_CERT_FILE=$(gateway_tls_cert_file)" \
        uv run --frozen pytest tests/auth_idp/contracts -v --auth-idp-runtime authentik-compose -m auth_idp_runtime
    status="$?"
    echo "Auth-idp Compose diagnostics: ${diagnostics}"
    return "${status}"
}

run_k8s_tests() {
    local diagnostics
    local k8s_diagnostics
    local workload_token_private_key
    local status

    validate_k8s_runtime
    ensure_workload_token_private_key
    workload_token_private_key="$(workload_token_private_key_file)"
    diagnostics="$(prepare_diagnostics_dir kubernetes)"
    write_diagnostics_metadata kubernetes "${diagnostics}"
    echo "Auth-idp Kubernetes diagnostics: ${diagnostics}"

    if [[ "${IMAGE_SELECTED}" == "true" ]]; then
        echo "Using prebuilt auth-idp Kubernetes test image: $(image_ref)"
    elif [[ "${K8S_REUSE_CLUSTER}" == "1" && "${K8S_SKIP_IMAGE_LOAD}" == "1" ]]; then
        echo "Reusing Kubernetes cluster without rebuilding or loading image: $(image_ref)"
    else
        build_default_test_image
    fi

    k8s_diagnostics="${diagnostics}/kubernetes"
    if [[ "${DRY_RUN}" != "true" ]]; then
        mkdir -p "${k8s_diagnostics}"
    fi

    if [[ "${DRY_RUN}" == "true" ]]; then
        run_pytest_with_diagnostics "${diagnostics}" \
            env "IMAGE_REGISTRY=${IMAGE_REGISTRY}" "BAKE_TAG=${BAKE_TAG}" \
            "E2E_SERVICES_LOG_DIR=${diagnostics}" \
            "NMP_AUTHENTIK_K8S_LOG_DIR=${k8s_diagnostics}" \
            "NMP_AUTHENTIK_K8S_HELM_RELEASE=${HELM_RELEASE}" \
            "NMP_AUTHENTIK_K8S_NAMESPACE=${HELM_NAMESPACE}" \
            "NMP_AUTHENTIK_K8S_RUNTIME=${K8S_RUNTIME}" \
            "NMP_AUTHENTIK_K8S_CLUSTER_NAME=${K8S_CLUSTER_NAME}" \
            "NMP_AUTHENTIK_K8S_GATEWAY_PORT=${K8S_GATEWAY_PORT}" \
            "NMP_AUTHENTIK_K8S_KEEP_CLUSTER=${K8S_KEEP_CLUSTER}" \
            "NMP_AUTHENTIK_K8S_REUSE_CLUSTER=${K8S_REUSE_CLUSTER}" \
            "NMP_AUTHENTIK_K8S_SKIP_IMAGE_LOAD=${K8S_SKIP_IMAGE_LOAD}" \
            "NMP_AUTHENTIK_K8S_NGC_EXISTING_SECRET=${K8S_NGC_EXISTING_SECRET}" \
            "NMP_AUTHENTIK_K8S_IMAGE_PULL_SECRET=${K8S_IMAGE_PULL_SECRET}" \
            "NMP_AUTHENTIK_K8S_WORKLOAD_TOKEN_PRIVATE_KEY_FILE=${workload_token_private_key}" \
            uv run --frozen pytest tests/auth_idp/contracts -v --auth-idp-runtime authentik-kubernetes -m auth_idp_runtime --junitxml="${K8S_JUNIT_XML}"
        return
    fi

    echo "Writing Authentik Kubernetes diagnostics to: ${diagnostics}"
    run_pytest_with_diagnostics "${diagnostics}" \
        env "IMAGE_REGISTRY=${IMAGE_REGISTRY}" "BAKE_TAG=${BAKE_TAG}" \
        "E2E_SERVICES_LOG_DIR=${diagnostics}" \
        "NMP_AUTHENTIK_K8S_LOG_DIR=${k8s_diagnostics}" \
        "NMP_AUTHENTIK_K8S_HELM_RELEASE=${HELM_RELEASE}" \
        "NMP_AUTHENTIK_K8S_NAMESPACE=${HELM_NAMESPACE}" \
        "NMP_AUTHENTIK_K8S_RUNTIME=${K8S_RUNTIME}" \
        "NMP_AUTHENTIK_K8S_CLUSTER_NAME=${K8S_CLUSTER_NAME}" \
        "NMP_AUTHENTIK_K8S_GATEWAY_PORT=${K8S_GATEWAY_PORT}" \
        "NMP_AUTHENTIK_K8S_KEEP_CLUSTER=${K8S_KEEP_CLUSTER}" \
        "NMP_AUTHENTIK_K8S_REUSE_CLUSTER=${K8S_REUSE_CLUSTER}" \
        "NMP_AUTHENTIK_K8S_SKIP_IMAGE_LOAD=${K8S_SKIP_IMAGE_LOAD}" \
        "NMP_AUTHENTIK_K8S_NGC_EXISTING_SECRET=${K8S_NGC_EXISTING_SECRET}" \
        "NMP_AUTHENTIK_K8S_IMAGE_PULL_SECRET=${K8S_IMAGE_PULL_SECRET}" \
        "NMP_AUTHENTIK_K8S_WORKLOAD_TOKEN_PRIVATE_KEY_FILE=${workload_token_private_key}" \
        uv run --frozen pytest tests/auth_idp/contracts -v --auth-idp-runtime authentik-kubernetes -m auth_idp_runtime --junitxml="${K8S_JUNIT_XML}"
    status="$?"
    echo "Auth-idp Kubernetes diagnostics: ${diagnostics}"
    return "${status}"
}

if [[ $# -eq 0 ]]; then
    usage
    exit 0
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        run-local | down | prepare-local | compose | render-blueprint | k8s)
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
        --platform)
            [[ $# -ge 2 ]] || die "--platform requires a value"
            TEST_PLATFORM="$2"
            TEST_PLATFORM_SET="true"
            shift 2
            ;;
        --runtime)
            [[ $# -ge 2 ]] || die "--runtime requires a value"
            K8S_RUNTIME="$2"
            K8S_RUNTIME_SET="true"
            shift 2
            ;;
        --runtime=*)
            K8S_RUNTIME="${1#*=}"
            K8S_RUNTIME_SET="true"
            shift
            ;;
        --reuse)
            REUSE_SET="true"
            shift
            ;;
        --skip-image-load)
            K8S_SKIP_IMAGE_LOAD="1"
            K8S_SKIP_IMAGE_LOAD_SET="true"
            shift
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

if [[ "${REUSE_SET}" == "true" ]]; then
    case "${ACTION}" in
        compose)
            TEST_LIFECYCLE="reuse"
            ;;
        k8s)
            K8S_REUSE_CLUSTER="1"
            K8S_KEEP_CLUSTER="1"
            if [[ -z "${K8S_CLUSTER_NAME}" ]]; then
                K8S_CLUSTER_NAME="${REUSE_K8S_CLUSTER_NAME}"
            fi
            ;;
        *)
            die "--reuse is only valid with compose or k8s"
            ;;
    esac
fi

if [[ "${ACTION}" == "k8s" && "${K8S_REUSE_CLUSTER}" == "1" && -z "${K8S_CLUSTER_NAME}" ]]; then
    K8S_CLUSTER_NAME="${REUSE_K8S_CLUSTER_NAME}"
fi

if [[ -z "${IMAGE_REGISTRY}" || -z "${BAKE_TAG}" ]]; then
    die "image registry and tag must be non-empty"
fi

if [[ "${ACTION}" != "compose" && "${ACTION}" != "k8s" ]]; then
    if [[ "${TEST_PLATFORM_SET}" == "true" ]]; then
        die "--platform is only valid with the compose or k8s action"
    fi
fi

if [[ "${ACTION}" != "k8s" && "${ACTION}" != "down" ]]; then
    if [[ "${K8S_RUNTIME_SET}" == "true" ]]; then
        die "--runtime is only valid with k8s or down"
    fi
fi

if [[ "${ACTION}" != "k8s" ]]; then
    if [[ "${K8S_SKIP_IMAGE_LOAD_SET}" == "true" ]]; then
        die "--skip-image-load is only valid with k8s"
    fi
fi

if [[ "${ACTION}" == "k8s" &&
    "${K8S_SKIP_IMAGE_LOAD}" == "1" &&
    "${K8S_REUSE_CLUSTER}" != "1" &&
    "${IMAGE_SELECTED}" != "true" ]]; then
    die "--skip-image-load with a fresh k8s cluster requires a pullable image selected with" \
        "--image, or a reused cluster via --reuse"
fi

if [[ "${ACTION}" != "run-local" && "${ACTION}" != "down" && "${COMPOSE_DIR_SET}" == "true" ]]; then
    die "--compose-dir is only valid with run-local or down"
fi

case "${ACTION}" in
    run-local)
        run_local
        ;;
    down)
        down
        ;;
    prepare-local)
        prepare_local
        ;;
    compose)
        run_tests
        ;;
    render-blueprint)
        render_blueprint
        ;;
    k8s)
        run_k8s_tests
        ;;
esac
