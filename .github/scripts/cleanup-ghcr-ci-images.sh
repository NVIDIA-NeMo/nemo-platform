#!/usr/bin/env bash
set -euo pipefail

if ! [[ "${STALE_HOURS}" =~ ^[0-9]+$ ]]; then
  echo "stale_hours must be a positive integer, got: ${STALE_HOURS}" >&2
  exit 1
fi

if [ "${STALE_HOURS}" -lt 1 ]; then
  echo "stale_hours must be at least 1, got: ${STALE_HOURS}" >&2
  exit 1
fi

owner="${GITHUB_REPOSITORY_OWNER,,}"
repo="${GITHUB_REPOSITORY#*/}"
repo="${repo,,}"

date_utc() {
  if command -v gdate >/dev/null 2>&1; then
    gdate -u -d "$1" '+%Y-%m-%dT%H:%M:%SZ'
    return
  fi

  date -u -d "$1" '+%Y-%m-%dT%H:%M:%SZ'
}

cutoff="$(date_utc "${STALE_HOURS} hours ago")"

# GitHub's package version API exposes updated_at, not a separate last-pulled timestamp.
# These are the docker-cpu images published by .github/workflows/ci.yaml.
images=(
  "nmp-api"
  "nmp-core"
  "nmp-cpu-tasks"
)

echo "Scanning ghcr.io/${owner}/${repo} image versions last updated before ${cutoff}"
echo "dry_run=${DRY_RUN}"

total_deleted=0
total_candidates=0

url_encode() {
  jq -nr --arg value "$1" '$value|@uri'
}

find_stale_versions() {
  local endpoint="$1"
  local jq_filter
  jq_filter="
    .[] |
    select(.updated_at != null and .updated_at < \"${cutoff}\") |
    select(((.metadata.container.tags // []) | index(\"latest\")) | not) |
    [.id, .name, .updated_at, ((.metadata.container.tags // []) | join(\",\"))] |
    @tsv
  "

  gh api --paginate "${endpoint}/versions?per_page=100" --jq "${jq_filter}"
}

for image in "${images[@]}"; do
  package_name="${repo}/${image}"
  encoded_package_name="$(url_encode "${package_name}")"
  endpoint="/orgs/${owner}/packages/container/${encoded_package_name}"

  echo "::group::${package_name}"

  api_error="$(mktemp)"
  if ! stale_versions="$(find_stale_versions "${endpoint}" 2>"${api_error}")"; then
    if grep -q "HTTP 404" "${api_error}"; then
      echo "Package ${package_name} was not found; skipping."
      echo "::endgroup::"
      continue
    fi

    cat "${api_error}" >&2
    exit 1
  fi

  if [ -z "${stale_versions}" ]; then
    echo "No stale package versions found."
    echo "::endgroup::"
    continue
  fi

  while IFS=$'\t' read -r version_id digest updated_at tags; do
    if [ -z "${version_id}" ]; then
      continue
    fi

    total_candidates=$((total_candidates + 1))
    tag_summary="${tags:-<untagged>}"
    echo "Candidate ${package_name}@${digest} updated_at=${updated_at} tags=${tag_summary}"

    if [ "${DRY_RUN}" = "true" ]; then
      continue
    fi

    gh api -X DELETE "${endpoint}/versions/${version_id}" >/dev/null
    total_deleted=$((total_deleted + 1))
    echo "Deleted package version ${version_id}"
  done <<< "${stale_versions}"

  echo "::endgroup::"
done

echo "Stale candidates: ${total_candidates}"
echo "Deleted versions: ${total_deleted}"
