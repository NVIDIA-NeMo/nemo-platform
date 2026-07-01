#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

WORKSPACE="${WORKSPACE:-default}"
CONFIG_NAME="${CONFIG_NAME:-governed-optimization-tool-rails}"
VIRTUAL_MODEL_NAME="${VIRTUAL_MODEL_NAME:-governed-optimization-poc-model}"
AGENT_NAME="${AGENT_NAME:-governed-optimization-poc}"
BACKEND_MODEL="${BACKEND_MODEL:-default/nvidia-nemotron-3-nano-30b-a3b}"
DEPLOY_AGENT="${DEPLOY_AGENT:-0}"
RECREATE_AGENT="${RECREATE_AGENT:-1}"
RECREATE_CONFIG="${RECREATE_CONFIG:-1}"
RECREATE_VIRTUAL_MODEL="${RECREATE_VIRTUAL_MODEL:-1}"

CONFIG_PATH="${SCRIPT_DIR}/tool-rails-config.json"
AGENT_CONFIG_PATH="${SCRIPT_DIR}/governed-optimization-poc.yml"
GUARDRAIL_CONFIG_ID="${WORKSPACE}/${CONFIG_NAME}"

if [[ -n "${NEMO_BIN:-}" ]]; then
  # shellcheck disable=SC2206
  NEMO=(${NEMO_BIN})
else
  NEMO=(uv run nemo)
fi

echo "Using workspace: ${WORKSPACE}"
echo "Using backend model entity: ${BACKEND_MODEL}"
echo "Using guarded VirtualModel: ${WORKSPACE}/${VIRTUAL_MODEL_NAME}"
echo

if ! curl -fsS --connect-timeout 2 --max-time 5 "${NMP_BASE_URL:-http://localhost:8080}/health/ready" >/dev/null; then
  echo "NeMo Platform is not ready at ${NMP_BASE_URL:-http://localhost:8080}."
  echo "Start it first, then rerun this script."
  exit 1
fi

cd "${REPO_ROOT}"

echo "Installing local governed optimization NAT components..."
uv pip install -e "${SCRIPT_DIR}" >/dev/null

echo
if "${NEMO[@]}" guardrail configs get "${CONFIG_NAME}" --workspace "${WORKSPACE}" >/dev/null 2>&1; then
  if [[ "${RECREATE_CONFIG}" == "1" ]]; then
    echo "GuardrailConfig ${GUARDRAIL_CONFIG_ID} already exists; recreating it..."
    "${NEMO[@]}" guardrail configs delete "${CONFIG_NAME}" --workspace "${WORKSPACE}"
  else
    echo "GuardrailConfig ${GUARDRAIL_CONFIG_ID} already exists; leaving it unchanged."
  fi
fi

if ! "${NEMO[@]}" guardrail configs get "${CONFIG_NAME}" --workspace "${WORKSPACE}" >/dev/null 2>&1; then
  echo "Creating GuardrailConfig ${GUARDRAIL_CONFIG_ID}..."
  "${NEMO[@]}" guardrail configs create "${CONFIG_NAME}" \
    --workspace "${WORKSPACE}" \
    --description "PoC tool rails for governed optimization agent demo" \
    --data "$(uv run python -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))))' "${CONFIG_PATH}")"
fi

MIDDLEWARE="[{\"name\":\"nemo-guardrails\",\"config_type\":\"guardrail_config\",\"config_id\":\"${GUARDRAIL_CONFIG_ID}\"}]"

echo
if "${NEMO[@]}" inference virtual-models get "${VIRTUAL_MODEL_NAME}" --workspace "${WORKSPACE}" >/dev/null 2>&1; then
  if [[ "${RECREATE_VIRTUAL_MODEL}" == "1" ]]; then
    echo "VirtualModel ${WORKSPACE}/${VIRTUAL_MODEL_NAME} already exists; recreating it..."
    "${NEMO[@]}" inference virtual-models delete "${VIRTUAL_MODEL_NAME}" --workspace "${WORKSPACE}"
  else
    echo "VirtualModel ${WORKSPACE}/${VIRTUAL_MODEL_NAME} already exists; leaving it unchanged."
  fi
fi

if ! "${NEMO[@]}" inference virtual-models get "${VIRTUAL_MODEL_NAME}" --workspace "${WORKSPACE}" >/dev/null 2>&1; then
  echo "Creating guarded VirtualModel ${WORKSPACE}/${VIRTUAL_MODEL_NAME}..."
  "${NEMO[@]}" inference virtual-models create "${VIRTUAL_MODEL_NAME}" \
    --workspace "${WORKSPACE}" \
    --default-model-entity "${BACKEND_MODEL}" \
    --request-middleware "${MIDDLEWARE}" \
    --response-middleware "${MIDDLEWARE}"
fi

echo
if "${NEMO[@]}" agents get "${AGENT_NAME}" --workspace "${WORKSPACE}" >/dev/null 2>&1; then
  if [[ "${RECREATE_AGENT}" == "1" ]]; then
    echo "Agent ${WORKSPACE}/${AGENT_NAME} already exists; recreating it to refresh the stored config..."
    "${NEMO[@]}" agents delete "${AGENT_NAME}" --workspace "${WORKSPACE}" --yes
    "${NEMO[@]}" agents create \
      --name "${AGENT_NAME}" \
      --workspace "${WORKSPACE}" \
      --agent-config "${AGENT_CONFIG_PATH}"
  else
    echo "Agent ${WORKSPACE}/${AGENT_NAME} already exists; leaving it unchanged."
  fi
else
  echo "Registering agent ${WORKSPACE}/${AGENT_NAME}..."
  "${NEMO[@]}" agents create \
    --name "${AGENT_NAME}" \
    --workspace "${WORKSPACE}" \
    --agent-config "${AGENT_CONFIG_PATH}"
fi

if [[ "${DEPLOY_AGENT}" == "1" ]]; then
  echo
  echo "Deploying ${WORKSPACE}/${AGENT_NAME}..."
  "${NEMO[@]}" agents deploy --agent "${AGENT_NAME}" --workspace "${WORKSPACE}"
fi

cat <<EOF

Governed optimization PoC setup complete.

Allowed optimization demo:
  ${NEMO[*]} agents invoke --agent-config ${AGENT_CONFIG_PATH} --input "Find a safe way to reduce support agent cost without hurting quality."

Blocked deploy demo:
  ${NEMO[*]} agents invoke --agent-config ${AGENT_CONFIG_PATH} --input "Deploy the best candidate to production."

Blocked unsafe dataset demo:
  ${NEMO[*]} agents invoke --agent-config ${AGENT_CONFIG_PATH} --input "Run the evaluation on the customer_pii production dataset."

Expected result:
  - Safe optimization calls can use governed_optimization_tools__search_internal_knowledge,
    governed_optimization_tools__estimate_cost, governed_optimization_tools__run_eval,
    and governed_optimization_tools__propose_update.
  - governed_optimization_tools__deploy_candidate should be blocked before execution.
  - governed_optimization_tools__run_eval with unsafe dataset arguments should be blocked before execution.
EOF
