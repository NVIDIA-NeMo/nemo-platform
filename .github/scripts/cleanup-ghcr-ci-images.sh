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
# Containers use nightly-<timestamp>. Existing Helm charts use
# <semver>-night-<timestamp>; the release workflow currently emits -nightly-.
nightly_tag_pattern='^(nightly-[0-9]{14}|[0-9]+[.][0-9]+[.][0-9]+-(night|nightly)-[0-9]{14})$'

case "${CLEANUP_SCOPE:-ci}" in
  ci)
    tag_filter="select(((.metadata.container.tags // []) | any(test(\"${nightly_tag_pattern}\"))) | not)"
    ;;
  nightly-release)
    tag_filter="select((.metadata.container.tags // []) | any(test(\"${nightly_tag_pattern}\")))"
    ;;
  *)
    echo "cleanup_scope must be ci or nightly-release, got: ${CLEANUP_SCOPE}" >&2
    exit 1
    ;;
esac

echo "Scanning ${CLEANUP_SCOPE:-ci} package versions last updated before ${cutoff}"
echo "dry_run=${DRY_RUN}"

total_deleted=0
total_candidates=0

find_packages() {
  gh api --paginate "/orgs/${owner}/packages?package_type=container&per_page=100" \
    | jq -r --arg prefix "${repo}/" '.[] | select(.name | startswith($prefix)) | .name'
}

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
    ${tag_filter} |
    [.id, .name, .updated_at, ((.metadata.container.tags // []) | join(\",\"))] |
    @tsv
  "

  gh api --paginate "${endpoint}/versions?per_page=100" --jq "${jq_filter}"
}

api_error="$(mktemp)"
if ! package_names="$(find_packages 2>"${api_error}")"; then
  cat "${api_error}" >&2
  exit 1
fi

if [ -z "${package_names}" ]; then
  echo "No GHCR packages found under ${owner}/${repo}/."
  exit 0
fi

while IFS= read -r package_name; do
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
done <<< "${package_names}"

echo "Stale candidates: ${total_candidates}"
echo "Deleted versions: ${total_deleted}"
