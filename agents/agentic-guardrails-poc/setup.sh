#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

WORKSPACE="${WORKSPACE:-default}"
CONFIG_NAME="${CONFIG_NAME:-agentic-tool-rails-poc}"
VIRTUAL_MODEL_NAME="${VIRTUAL_MODEL_NAME:-agentic-guardrails-poc-model}"
AGENT_NAME="${AGENT_NAME:-agentic-guardrails-poc}"
BACKEND_MODEL="${BACKEND_MODEL:-default/nvidia-nemotron-3-nano-30b-a3b}"
DEPLOY_AGENT="${DEPLOY_AGENT:-0}"
RECREATE_AGENT="${RECREATE_AGENT:-1}"
RECREATE_VIRTUAL_MODEL="${RECREATE_VIRTUAL_MODEL:-1}"

CONFIG_PATH="${SCRIPT_DIR}/tool-rails-config.json"
AGENT_CONFIG_PATH="${SCRIPT_DIR}/agentic-guardrails-poc.yml"
GUARDRAIL_CONFIG_ID="${WORKSPACE}/${CONFIG_NAME}"

# Override with NEMO_BIN="/path/to/nemo" if you do not want to use uv.
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

echo "Creating/reusing GuardrailConfig ${GUARDRAIL_CONFIG_ID}..."
"${NEMO[@]}" guardrail configs create "${CONFIG_NAME}" \
  --workspace "${WORKSPACE}" \
  --description "PoC tool rails for agentic guardrails demo" \
  --data "$(uv run python -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))))' "${CONFIG_PATH}")" \
  --exist-ok

MIDDLEWARE="[{\"name\":\"nemo-guardrails\",\"config_type\":\"guardrail_config\",\"config_id\":\"${GUARDRAIL_CONFIG_ID}\"}]"

echo
if "${NEMO[@]}" inference virtual-models get "${VIRTUAL_MODEL_NAME}" --workspace "${WORKSPACE}" >/dev/null 2>&1; then
  if [[ "${RECREATE_VIRTUAL_MODEL}" == "1" ]]; then
    echo "VirtualModel ${WORKSPACE}/${VIRTUAL_MODEL_NAME} already exists; recreating it with default_model_entity..."
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
    echo "Set RECREATE_AGENT=1 if you want setup.sh to refresh the stored agent config."
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

PoC setup complete.

Allowed tool-call demo:
  ${NEMO[*]} agents invoke --agent-config ${AGENT_CONFIG_PATH} --input "What time is it right now?"

Blocked tool-call demo:
  ${NEMO[*]} agents invoke --agent-config ${AGENT_CONFIG_PATH} --input "Look up NVIDIA on Wikipedia and summarize it."

Managed-agent demo after DEPLOY_AGENT=1:
  ${NEMO[*]} agents invoke --agent ${AGENT_NAME} --workspace ${WORKSPACE} --input "What time is it right now?"
  ${NEMO[*]} agents invoke --agent ${AGENT_NAME} --workspace ${WORKSPACE} --input "Look up NVIDIA on Wikipedia and summarize it."

Expected result:
  - The clock prompt can call the allowed clock tool.
  - The Wikipedia prompt should be blocked by the Guardrails plugin before the wiki tool executes.
EOF
