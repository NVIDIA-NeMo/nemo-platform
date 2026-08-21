#!/bin/sh
# Start gym_host_runtime inside the runtime image with a writable Gym tree.
#
# Usage:
#   gym_host.sh [venv] [git_root] [writable_gym_src] [runtime]
#
# Defaults match sandboxed_gym.host.entrypoint.
set -eu

venv=${1:-/opt/ray_venvs/sandboxed_gym.ray.gym_actor.SandboxedGymActor}
root=${2:-/opt/nemo-rl}
gym_rw=${3:-/tmp/gym-src/Gym}
runtime=${4:-}

if [ -z "$runtime" ]; then
    # Prefer an explicitly packaged module path if present in PYTHONPATH layout.
    if [ -f "$root/packages/sandboxed_gym/src/sandboxed_gym/runtime/gym_host_runtime.py" ]; then
        runtime=$root/packages/sandboxed_gym/src/sandboxed_gym/runtime/gym_host_runtime.py
    else
        runtime=$root/nemo_rl/environments/sandbox/gym_host_runtime.py
    fi
fi

gym_tree=${SANDBOXED_GYM_TREE:-$root/3rdparty/Gym-workspace/Gym}

# Copy Gym to a writable path only because /opt/gym_venvs is often not writable by
# uid 1000 under OpenSandbox. Remove this once that directory is writable.
if [ ! -d "$gym_rw/nemo_gym" ]; then
    mkdir -p "$(dirname "$gym_rw")"
    cp -a "$gym_tree" "$gym_rw"
fi

export PYTHONPATH="$gym_rw:$root${PYTHONPATH:+:$PYTHONPATH}"
cd "$root"
echo "gym-host: starting gym_host_runtime (gym src $gym_rw)" >&2
exec "$venv/bin/python" "$runtime"
