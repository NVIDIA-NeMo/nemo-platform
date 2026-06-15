#!/usr/bin/env bash
# Script: collect_k8s_logs.sh
# Description: Collects Kubernetes pod logs and diagnostics, writing to files for archiving.
#              Safe to call even if the cluster is partially degraded — individual failures are ignored.
# Usage: ./collect_k8s_logs.sh [output-dir]
#
# Environment Variables:
#   LOG_DIR              (optional) - Directory to write logs to (defaults to k8s-logs)
#   K8S_FULL_LOGS        (optional) - Set to "true" to capture full container logs.
#                                     Default: tailed to 500 lines per container.

# Note: intentionally no -e so individual kubectl failures don't abort collection
set -uo pipefail

LOG_DIR="${1:-${LOG_DIR:-k8s-logs}}"
TAIL_ARGS=(--tail=500)
if [ "${K8S_FULL_LOGS:-false}" = "true" ]; then
    TAIL_ARGS=()
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

log_info "Collecting Kubernetes diagnostics to: ${LOG_DIR}"
mkdir -p "${LOG_DIR}"

# Cluster-wide summaries
kubectl get nodes -o wide                                          > "${LOG_DIR}/nodes.txt"      2>&1 || true
kubectl get pods --all-namespaces -o wide                         > "${LOG_DIR}/all-pods.txt"   2>&1 || true
kubectl get events --all-namespaces --sort-by='.lastTimestamp'    > "${LOG_DIR}/all-events.txt" 2>&1 || true

# Per-namespace detailed collection
NAMESPACES=$(kubectl get namespaces --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null || echo "default")

for NS in ${NAMESPACES}; do
    # Skip empty/lease namespaces that never have interesting logs
    case "${NS}" in
        kube-node-lease|kube-public) continue ;;
    esac

    NS_DIR="${LOG_DIR}/${NS}"
    mkdir -p "${NS_DIR}"

    log_info "  Collecting namespace: ${NS}"

    kubectl get pods  -n "${NS}" -o wide                        > "${NS_DIR}/pods.txt"   2>&1 || true
    kubectl get events -n "${NS}" --sort-by='.lastTimestamp'    > "${NS_DIR}/events.txt" 2>&1 || true

    PODS=$(kubectl get pods -n "${NS}" --no-headers 2>/dev/null | awk '{print $1}') || true
    for pod in ${PODS}; do
        kubectl describe pod/"${pod}" -n "${NS}" \
            > "${NS_DIR}/describe-${pod}.txt" 2>&1 || true
        kubectl logs pod/"${pod}" -n "${NS}" --all-containers "${TAIL_ARGS[@]}" \
            > "${NS_DIR}/logs-${pod}.txt" 2>&1 || true
        # Previous container logs are valuable for crash-looping pods
        kubectl logs pod/"${pod}" -n "${NS}" --all-containers --previous --tail=200 \
            > "${NS_DIR}/logs-${pod}-previous.txt" 2>&1 || true
    done
done

log_info "Log collection complete — files written to: ${LOG_DIR}"
