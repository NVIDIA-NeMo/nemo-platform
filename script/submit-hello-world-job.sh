#!/usr/bin/env bash

set -euo pipefail

# If the local platform was started with `script/run-hello-world-jobs.sh --auth`,
# authenticate first with:
#   .venv/bin/nemo auth login --unsigned-token --email <email>

WORKSPACE="${NMP_WORKSPACE:-default}"
JOB_NAME="${1:-hello-world-cli-job}"
MESSAGE="${2:-hello from cli}"
PROJECT="${NMP_PROJECT:-}"
IMAGE_REGISTRY="${NMP_IMAGE_REGISTRY:-my-registry}"
IMAGE_TAG="${NMP_IMAGE_TAG:-local}"
EXECUTION_PROFILE="${NMP_JOB_PROFILE:-docker}"
IMAGE="${NMP_CPU_TASKS_IMAGE:-${IMAGE_REGISTRY}/nmp-cpu-tasks:${IMAGE_TAG}}"
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

payload_file="$(mktemp)"
trap 'rm -f "${payload_file}"' EXIT

cat > "${payload_file}" <<EOF
{
  "workspace": "${WORKSPACE}",
  "name": "${JOB_NAME}",
  "source": "hello-world",
  "spec": {
    "message": "${MESSAGE}"
  },
  "platform_spec": {
    "steps": [
      {
        "name": "hello-world",
        "executor": {
          "provider": "cpu",
          "profile": "${EXECUTION_PROFILE}",
          "container": {
            "image": "${IMAGE}",
            "entrypoint": ["nemo-platform"],
            "command": ["run", "task", "--task", "nmp.hello_world.tasks.hello_world"]
          }
        },
        "config": {
          "message": "${MESSAGE}"
        }
      }
    ]
  }
}
EOF

if [[ -z "${PROJECT}" ]]; then
  python3 - <<'PY' "${payload_file}"
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    payload = json.load(f)
payload.pop("project", None)
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f)
PY
else
  python3 - <<'PY' "${payload_file}" "${PROJECT}"
import json
import sys

path, project = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    payload = json.load(f)
payload["project"] = project
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f)
PY
fi

"${NEMO_BIN}" jobs create "${JOB_NAME}" --input-file "${payload_file}"
