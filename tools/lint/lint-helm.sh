#!/usr/bin/env bash

set -xeo pipefail

HELM_FOLDER=${HELM_FOLDER:-k8s/helm}
HELM_RELEASE_NAME=${HELM_RELEASE_NAME:-nemo-platform}
OPENSHIFT_VERSION=${OPENSHIFT_VERSION:-4.1.0}

# Cache dir for kubeconform so schemas are downloaded once per run instead of per file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CI_PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
KUBECONFORM_CACHE="${KUBECONFORM_CACHE:-${PROJECT_ROOT}/.kubeconform-cache}"
mkdir -p "${KUBECONFORM_CACHE}"

# Fetch chart dependencies so subchart templates (e.g. postgresql) are available during lint/template
helm dependency update "${HELM_FOLDER}"

# Lint the Helm chart
helm lint --strict "${HELM_FOLDER}"

# Validate the Helm chart by rendering templates with all values files in ci/ directory
shopt -s nullglob
for value_file in "${HELM_FOLDER}"/ci/*.yaml; do
  echo "Validating Helm chart templating with values file: ${value_file}"
  helm template "${HELM_RELEASE_NAME}" "${HELM_FOLDER}" -f "${value_file}" > "${value_file}.output"
  echo "Validating Helm chart kubeconform with values file: ${value_file}"
  helm template "${HELM_RELEASE_NAME}" "${HELM_FOLDER}" -f "${value_file}" \
    | kubeconform -cache "${KUBECONFORM_CACHE}" -schema-location default \
      -schema-location "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json" \
      -schema-location "https://raw.githubusercontent.com/yannh/kubernetes-json-schema/master/{{.NormalizedKubernetesVersion}}/{{.ResourceKind}}.json" \
      -summary -output json > "${value_file}.kubeconform.json"
done

# If all successful, cleanup the created files
rm -f "${HELM_FOLDER}"/ci/*.output "${HELM_FOLDER}"/ci/*.kubeconform.json "${HELM_FOLDER}"/ci/*.kubeconform-openshift.json
