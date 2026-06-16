#!/usr/bin/env bash
# Create an E2E test bucket in RustFS
# Expects NAMESPACE to be set (e.g. current kubectl context namespace).
# Uses default credentials (rustfsadmin/rustfsadmin).
#
set -e

NAMESPACE="${NAMESPACE:-${NAMESPACE}}"

echo "Waiting for RustFS pod to be ready..."
if ! kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=rustfs -n "${NAMESPACE}" --timeout=300s; then
  echo "RustFS pod failed to become ready"
  kubectl describe pods -l app.kubernetes.io/name=rustfs -n "${NAMESPACE}" || true
  kubectl logs -l app.kubernetes.io/name=rustfs -n "${NAMESPACE}" --tail=50 || true
  exit 1
fi
echo "RustFS is ready"

echo "Creating E2E test bucket in RustFS..."
if ! kubectl run aws-cli --rm -i --restart=Never -n "${NAMESPACE}" \
  --image=amazon/aws-cli:2.22.35 \
  --pod-running-timeout=2m \
  --env="AWS_ACCESS_KEY_ID=rustfsadmin" \
  --env="AWS_SECRET_ACCESS_KEY=rustfsadmin" \
  -- --endpoint-url http://rustfs-svc:9000 s3 mb s3://e2e-k8s-test; then
  echo "Failed to create E2E test bucket in RustFS"
  exit 1
fi
echo "E2E test bucket created successfully"
