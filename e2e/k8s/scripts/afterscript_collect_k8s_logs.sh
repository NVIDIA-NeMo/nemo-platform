#!/usr/bin/env bash
# 
# Collect logs for failed pods in the current namespace.
#
set -e

kubectl get pods
FAILED_PODS=$(kubectl get pods --field-selector=status.phase!=Running,status.phase!=Succeeded -o name --no-headers)
# Record all logs for failed job
if [ "$CI_JOB_STATUS" == "failed" ]; then
  FAILED_PODS=$(kubectl get pods -o name --no-headers)
fi
mkdir -p k8s-logs
if [ -n "$FAILED_PODS" ]; then
  for POD in $FAILED_PODS; do
    kubectl logs --all-containers "$POD" > k8s-logs/"$(basename "$POD")".log || true
    kubectl describe "$POD" > k8s-logs/"$(basename "$POD")"-description.txt || true
  done
fi
