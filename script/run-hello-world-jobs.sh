#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

ENABLE_AUTH=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auth)
      ENABLE_AUTH=true
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: script/run-hello-world-jobs.sh [--auth]

Options:
  --auth    Enable local auth with unsigned JWTs for development.

With --auth:
  Start the platform with unsigned JWTs enabled and seed default auth role
  bindings, then log in with:
    .venv/bin/nemo auth login --unsigned-token --email <email>
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Use --help for usage." >&2
      exit 2
      ;;
  esac
done

export NMP_CONFIG_FILE_PATH="${NMP_CONFIG_FILE_PATH:-packages/nmp_platform/config/local.yaml}"
export NMP_IMAGE_REGISTRY="${NMP_IMAGE_REGISTRY:-my-registry}"
export NMP_IMAGE_TAG="${NMP_IMAGE_TAG:-local}"

if [[ "${ENABLE_AUTH}" == "true" ]]; then
  export NMP_AUTH_ENABLED="${NMP_AUTH_ENABLED:-true}"
  export NMP_AUTH_ALLOW_UNSIGNED_JWT="${NMP_AUTH_ALLOW_UNSIGNED_JWT:-true}"
  # local.yaml sets auth.bundle_cache_seconds=0 for fast permission-propagation
  # feedback in tests. In this one-process local services setup, that causes
  # every PDP evaluation to reload policy data through the entities API, which
  # recursively triggers more PDP checks and can deadlock into timeout/retry
  # loops. Keep a nonzero cache when enabling auth from this helper script.
  export NMP_AUTH_BUNDLE_CACHE_SECONDS="${NMP_AUTH_BUNDLE_CACHE_SECONDS:-30}"
  # Seed the default local auth role bindings on startup so the unsigned-token
  # dev principal (admin@example.com by default) can perform platform actions
  # instead of failing every request with an immediate 403.
  export NMP_SEED_ON_STARTUP="${NMP_SEED_ON_STARTUP:-true}"
  # This helper starts a minimal service set without the models service. The
  # generic platform seed task waits for models readiness by default, which
  # prevents any seeding from running here. Limit startup seeding to the auth
  # role bindings we actually need for local unsigned-JWT testing.
  export NMP_PLATFORM_SEED_WAIT_FOR_READY_ENABLED="${NMP_PLATFORM_SEED_WAIT_FOR_READY_ENABLED:-false}"
  export NMP_PLATFORM_SEED_AUTH_ENABLED="${NMP_PLATFORM_SEED_AUTH_ENABLED:-true}"
  export NMP_PLATFORM_SEED_GUARDRAILS_ENABLED="${NMP_PLATFORM_SEED_GUARDRAILS_ENABLED:-false}"
  export NMP_PLATFORM_SEED_EVALUATOR_ENABLED="${NMP_PLATFORM_SEED_EVALUATOR_ENABLED:-false}"
  export NMP_PLATFORM_SEED_MODEL_PROVIDER_ENABLED="${NMP_PLATFORM_SEED_MODEL_PROVIDER_ENABLED:-false}"
fi

NEMO_BIN="${NEMO_BIN:-}"
if [[ -z "${NEMO_BIN}" ]]; then
  if [[ -x ".venv/bin/nemo" ]]; then
    NEMO_BIN=".venv/bin/nemo"
  elif command -v nemo >/dev/null 2>&1; then
    NEMO_BIN="nemo"
  else
    echo "Could not find nemo CLI. Set NEMO_BIN or create .venv/bin/nemo." >&2
    exit 127
  fi
fi

exec "${NEMO_BIN}" services run \
  --services jobs,hello-world,files,auth,entities \
  --controllers jobs
