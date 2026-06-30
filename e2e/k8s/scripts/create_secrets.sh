#!/usr/bin/env bash
# Shared helper for creating platform K8s secrets.
# Sourced by setup_local_minikube_cpu.sh, setup_local_minikube_gpu.sh, and setup_local_kind_cpu.sh.

# create_platform_secrets NAMESPACE [NGC_API_KEY_VALUE]
#
# Creates the standard set of platform secrets in the given namespace:
#   - ngc-api: NGC API key (generic secret)
#   - nvcrimagepullsecret: NGC container registry pull secret
#   - ghcr-pull: GHCR pull secret (when GITHUB_TOKEN is set)
#   - huggingface-token: HF token (when HF_TOKEN is set)
#
# The NGC_API_KEY_VALUE argument defaults to $NGC_API_KEY. Pass a placeholder
# value explicitly for setups that don't require a real key.
create_platform_secrets() {
    local namespace="${1:?namespace is required}"
    local ngc_key="${2:-${NGC_API_KEY:-}}"
    local kubectl_ns=(kubectl -n "${namespace}")

    if [ -z "${ngc_key}" ]; then
        log_warn "NGC_API_KEY not set, using placeholder for ngc-api secret"
        ngc_key="local-dev-placeholder"
    fi

    log_info "Creating NGC API secret..."
    "${kubectl_ns[@]}" create secret generic ngc-api \
      --from-literal=NGC_API_KEY="${ngc_key}" \
      --dry-run=client -o yaml | "${kubectl_ns[@]}" apply -f -

    log_info "Creating NGC image pull secret..."
    "${kubectl_ns[@]}" create secret docker-registry nvcrimagepullsecret \
      --docker-server=nvcr.io \
      --docker-username='$oauthtoken' \
      --docker-password="${ngc_key}" \
      --dry-run=client -o yaml | "${kubectl_ns[@]}" apply -f -

    if [ -n "${GITHUB_TOKEN:-}" ]; then
        log_info "Creating GHCR image pull secret..."
        "${kubectl_ns[@]}" create secret docker-registry ghcr-pull \
          --docker-server=ghcr.io \
          --docker-username=x-access-token \
          --docker-password="${GITHUB_TOKEN}" \
          --dry-run=client -o yaml | "${kubectl_ns[@]}" apply -f -
    else
        log_warn "GITHUB_TOKEN not set, skipping GHCR image pull secret"
    fi

    if [ -n "${HF_TOKEN:-}" ]; then
        log_info "Creating HuggingFace token secret..."
        "${kubectl_ns[@]}" create secret generic huggingface-token \
          --from-literal=HF_TOKEN="${HF_TOKEN}" \
          --dry-run=client -o yaml | "${kubectl_ns[@]}" apply -f -
    else
        log_warn "HF_TOKEN not set, skipping HuggingFace token secret"
    fi
}
