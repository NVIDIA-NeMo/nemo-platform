#!/usr/bin/env bash
#
# Smoke-test Helm NetworkPolicy enforcement from inside the Kubernetes cluster.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"

NAMESPACE="${NAMESPACE:-${KUBE_NAMESPACE:-default}}"
HELM_RELEASE_NAME="${HELM_RELEASE_NAME:-nemo-platform}"
PROBE_IMAGE="${NETWORK_POLICY_PROBE_IMAGE:-curlimages/curl:8.11.1}"
DENY_NAMESPACE="${NETWORK_POLICY_DENY_NAMESPACE:-${NAMESPACE}-network-policy-deny}"
TIMEOUT_SECONDS="${NETWORK_POLICY_PROBE_TIMEOUT_SECONDS:-8}"
CHART_NAME_LABEL="${NETWORK_POLICY_CHART_NAME_LABEL:-nemo-platform}"

KUBECTL_NS=(kubectl -n "${NAMESPACE}")

cleanup() {
    "${KUBECTL_NS[@]}" delete pod \
        nmp-np-release-api \
        nmp-np-managed-job-api \
        nmp-np-release-controller \
        nmp-np-denied-api \
        nmp-np-denied-controller \
        --ignore-not-found --wait=false >/dev/null 2>&1 || true
    kubectl -n "${DENY_NAMESPACE}" delete pod \
        nmp-np-denied-cross-api \
        --ignore-not-found --wait=false >/dev/null 2>&1 || true
    kubectl delete namespace "${DENY_NAMESPACE}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

first_jsonpath() {
    local resource="$1"
    local selector="$2"
    local jsonpath="$3"

    kubectl -n "${NAMESPACE}" get "${resource}" -l "${selector}" -o "jsonpath={.items[0]${jsonpath}}"
}

run_probe() {
    local namespace="$1"
    local name="$2"
    local labels="$3"
    local url="$4"

    kubectl -n "${namespace}" delete pod "${name}" --ignore-not-found --wait=true >/dev/null 2>&1 || true
    kubectl -n "${namespace}" run "${name}" \
        --attach=true \
        --restart=Never \
        --image="${PROBE_IMAGE}" \
        --pod-running-timeout=2m \
        --labels="${labels}" \
        --command -- curl -fsS --connect-timeout "${TIMEOUT_SECONDS}" --max-time "${TIMEOUT_SECONDS}" "${url}"
}

expect_allowed() {
    local description="$1"
    shift

    log_info "Expect allowed: ${description}"
    "$@"
}

expect_denied() {
    local description="$1"
    shift

    log_info "Expect denied: ${description}"
    if "$@"; then
        log_error "Unexpectedly allowed: ${description}"
        return 1
    fi
}

require_policy() {
    local selector="$1"
    local expected="$2"
    local count

    count="$(kubectl -n "${NAMESPACE}" get networkpolicy -l "${selector}" -o jsonpath='{.items[*].metadata.name}' | wc -w | tr -d ' ')"
    if [ "${count}" != "${expected}" ]; then
        log_error "Expected ${expected} NetworkPolicy resource(s) for selector ${selector}, found ${count}"
        kubectl -n "${NAMESPACE}" get networkpolicy -o wide || true
        exit 1
    fi
}

log_info "Validating NetworkPolicy resources in namespace ${NAMESPACE}"
require_policy "app.kubernetes.io/component=nmp-api,app.kubernetes.io/instance=${HELM_RELEASE_NAME}" 1
require_policy "app.kubernetes.io/component=nmp-core-controller,app.kubernetes.io/instance=${HELM_RELEASE_NAME}" 1
require_policy "app.kubernetes.io/component=nmp-core-jobs,app.kubernetes.io/instance=${HELM_RELEASE_NAME}" 1

api_service="$(first_jsonpath svc "app.kubernetes.io/component=nmp-api,app.kubernetes.io/instance=${HELM_RELEASE_NAME}" ".metadata.name")"
api_port="$(first_jsonpath svc "app.kubernetes.io/component=nmp-api,app.kubernetes.io/instance=${HELM_RELEASE_NAME}" ".spec.ports[0].port")"
controller_service="$(first_jsonpath svc "app.kubernetes.io/component=nmp-core-controller,app.kubernetes.io/instance=${HELM_RELEASE_NAME}" ".metadata.name")"
controller_port="$(first_jsonpath svc "app.kubernetes.io/component=nmp-core-controller,app.kubernetes.io/instance=${HELM_RELEASE_NAME}" ".spec.ports[0].port")"

if [ -z "${api_service}" ] || [ -z "${api_port}" ] || [ -z "${controller_service}" ] || [ -z "${controller_port}" ]; then
    log_error "Could not discover API/controller services for release ${HELM_RELEASE_NAME}"
    kubectl -n "${NAMESPACE}" get svc -o wide || true
    exit 1
fi

same_release_labels="app.kubernetes.io/name=${CHART_NAME_LABEL},app.kubernetes.io/instance=${HELM_RELEASE_NAME}"
managed_job_labels="app=nemo-job,nmp.nvidia.com/managed_by=jobs-controller"
untrusted_labels="app=nmp-network-policy-probe"
api_url="http://${api_service}.${NAMESPACE}.svc.cluster.local:${api_port}/health/ready"
controller_url="http://${controller_service}.${NAMESPACE}.svc.cluster.local:${controller_port}/health/ready"

kubectl create namespace "${DENY_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

expect_allowed "same-release pod to Platform API" \
    run_probe "${NAMESPACE}" nmp-np-release-api "${same_release_labels}" "${api_url}"
expect_allowed "managed job pod to Platform API" \
    run_probe "${NAMESPACE}" nmp-np-managed-job-api "${managed_job_labels}" "${api_url}"
expect_allowed "same-release pod to core controller" \
    run_probe "${NAMESPACE}" nmp-np-release-controller "${same_release_labels}" "${controller_url}"

expect_denied "unlabelled same-namespace pod to Platform API" \
    run_probe "${NAMESPACE}" nmp-np-denied-api "${untrusted_labels}" "${api_url}"
expect_denied "unlabelled same-namespace pod to core controller" \
    run_probe "${NAMESPACE}" nmp-np-denied-controller "${untrusted_labels}" "${controller_url}"
expect_denied "cross-namespace pod to Platform API" \
    run_probe "${DENY_NAMESPACE}" nmp-np-denied-cross-api "${untrusted_labels}" "${api_url}"

log_info "NetworkPolicy smoke test passed"
