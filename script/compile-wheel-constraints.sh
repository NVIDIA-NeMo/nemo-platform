#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Regenerate the partial dependency constraints used by CI's wheel install-smoke-test
# (.github/wheel-constraints/*.txt).
#
# Why partial (constraints, not a full lock): the smoke test installs the freshly
# built nemo-platform / nemo-platform-plugin wheels. Without any pin it resolves
# the whole tree fresh from PyPI (non-reproducible, supply-chain risk). A FULL
# lock does not work here — the vendored-SDK wheel needs newer deps than
# uv.lock, and pinning the entire tree also pins packages that lack py3.14
# wheels, breaking the py3.14 matrix. So we pin only each wheel's DIRECT external
# deps (the versions we've vetted) and let deep transitives resolve normally, so
# they stay py3.14-compatible and cannot self-conflict.
#
# litellm is capped <1.92 (a transitive): litellm 1.92.0 ships a native/PyO3
# build with no py3.14 wheel. Drop the cap once litellm ships a 3.14 wheel.
#
# Usage:
#   script/compile-wheel-constraints.sh <dir-with-both-wheels>
#
# Wheels come from `uv build --package nemo-platform[-plugin]` (nemo-platform
# needs the Studio/node toolchain) or a CI "<pkg>-wheel-py3.11" artifact
# (`gh run download <run-id> -n nemo-platform-wheel-py3.11 -D <dir>`).
set -euo pipefail

WHEEL_DIR="${1:?usage: script/compile-wheel-constraints.sh <dir-with-built-wheels>}"
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.github/wheel-constraints"
LITELLM_CAP='litellm<1.92  # 1.92.0 native build has no py3.14 wheel'

# Pin each of a wheel's direct external deps to the version that resolves for it
# (with litellm capped), then append the litellm cap.
emit_constraints() {
  local wheel="$1" spec="$2" label="$3" out="$4" venv meta
  venv="$(mktemp -d)"
  meta="$(mktemp -d)"
  uv venv "${venv}" --python 3.11 --quiet
  # Resolve+install once with the cap so we snapshot consistent, py3.14-safe versions.
  printf '%s\n' "${LITELLM_CAP%% *}" >"${meta}/cap.txt"
  uv pip install --python "${venv}/bin/python" --constraint "${meta}/cap.txt" "${spec}" >/dev/null
  # Direct external deps = the wheel's own Requires-Dist, minus self-referential extras.
  python3 - "$wheel" >"${meta}/names.txt" <<'PY'
import sys, zipfile, re
names=set()
with zipfile.ZipFile(sys.argv[1]) as z:
    md=next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
    for line in z.read(md).decode().splitlines():
        if line.startswith("Requires-Dist:"):
            dep=line.split(":",1)[1].strip()
            name=re.split(r"[<>=!~;\[ ]", dep, 1)[0].strip()
            if name and not name.startswith("nemo-platform"):
                names.add(name)
print("\n".join(sorted(names)))
PY
  {
    printf '# Partial dependency constraints for the CI wheel install-smoke-test.\n'
    printf '# Pins the DIRECT external deps of the built %s wheel to vetted versions for\n' "${label}"
    printf '# reproducibility; deep transitives resolve normally (so they stay py3.14-compatible and\n'
    printf '# cannot self-conflict). litellm is capped <1.92 — its 1.92.0 native build has no py3.14 wheel.\n'
    printf '# Regenerate with: script/compile-wheel-constraints.sh <dir-with-built-wheels>\n#\n'
    while read -r name; do
      [[ -n "${name}" ]] || continue
      ver="$("${venv}/bin/python" -c "import importlib.metadata as m; print(m.version('${name}'))" 2>/dev/null || true)
      [[ -n "${ver}" ]] && printf '%s==%s\n' "${name}" "${ver}"
    done <"${meta}/names.txt" | sort
    printf '%s\n' "${LITELLM_CAP}"
  } >"${out}"
  rm -rf "${venv}" "${meta}"
  echo "wrote ${out} ($(grep -cE '^[a-z0-9].*(==|<[0-9])' "${out}") pins)"
}

np_wheel="$(find "${WHEEL_DIR}" -name 'nemo_platform-*.whl' | head -1)"
pl_wheel="$(find "${WHEEL_DIR}" -name 'nemo_platform_plugin-*.whl' | head -1)"
[[ -n "${np_wheel}" ]] || { echo "no nemo_platform-*.whl in ${WHEEL_DIR}" >&2; exit 1; }
[[ -n "${pl_wheel}" ]] || { echo "no nemo_platform_plugin-*.whl in ${WHEEL_DIR}" >&2; exit 1; }

emit_constraints "${np_wheel}" "${np_wheel}[services]" "nemo-platform[services]" "${OUT_DIR}/nemo-platform-services.txt"
emit_constraints "${pl_wheel}" "${pl_wheel}" "nemo-platform-plugin" "${OUT_DIR}/nemo-platform-plugin.txt"
