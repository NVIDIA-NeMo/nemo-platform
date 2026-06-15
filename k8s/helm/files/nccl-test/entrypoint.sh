#!/bin/bash
set -e

echo "=== NCCL Multi-node RDMA Test ==="
echo "Node: $(hostname)"
echo "Date: $(date)"

if [ -f /platform-config/nccl-env.sh ]; then
  echo "Loading universal NCCL configuration..."
  # shellcheck source=/dev/null
  source /platform-config/nccl-env.sh
else
  echo "Warning: No universal config found"
fi

for platform_config in /platform-config/*-env.sh; do
  if [ -f "$platform_config" ]; then
    echo "Loading platform-specific config: $(basename "$platform_config")"
    # shellcheck source=/dev/null
    source "$platform_config"
  fi
done

echo "=== Environment Setup ==="
echo "NCCL_DEBUG: $NCCL_DEBUG"
echo "NCCL_SOCKET_IFNAME: $NCCL_SOCKET_IFNAME"

echo "=== Hardware Detection ==="
nvidia-smi -L

echo "=== Network Device Detection ==="
if command -v ip >/dev/null 2>&1; then
  ip addr show | grep -E "^[0-9]+:" | head -10
fi

# RDMA / IB checks (aligned with rdma-debug-test.yaml and network-operator README)
echo "=== RDMA Debug (in-pod) ==="
if command -v lspci >/dev/null 2>&1; then
  echo "--- PCI Mellanox (lspci) ---"
  lspci 2>/dev/null | grep -i mellanox || echo "(no Mellanox PCI lines)"
else
  echo "(lspci not installed; skip PCI check)"
fi

if [ -d /sys/class/infiniband ] && [ "$(ls -A /sys/class/infiniband 2>/dev/null)" ]; then
  echo "--- /sys/class/infiniband ---"
  ls -la /sys/class/infiniband/ || true
  echo "--- RDMA / infiniband devices under /dev ---"
  find /dev -maxdepth 2 \( -name "umad*" -o -name "uverbs*" -o -path "/dev/infiniband/*" \) 2>/dev/null | head -30 || true
  if [ -d /dev/infiniband ]; then
    ls -la /dev/infiniband/ || true
  else
    echo "(no /dev/infiniband directory)"
  fi
  if command -v ibv_devinfo >/dev/null 2>&1; then
    echo "--- ibv_devinfo ---"
    ibv_devinfo || true
  else
    echo "(ibv_devinfo not in PATH)"
  fi
else
  echo "(no InfiniBand class devices visible in this pod — expected on socket/AWS-only setups)"
fi

if command -v lsmod >/dev/null 2>&1; then
  echo "--- Kernel modules (mlx / ib_ / rdma) ---"
  lsmod | grep -E "(mlx|ib_|rdma)" || echo "(none matched in this mount namespace)"
fi

if [ "${NCCL_TEST_STRICT_IB_PORT_ACTIVE:-false}" = "true" ]; then
  if [ -d /sys/class/infiniband ] && [ "$(ls -A /sys/class/infiniband 2>/dev/null)" ]; then
    if command -v ibv_devinfo >/dev/null 2>&1; then
      if ibv_devinfo > /tmp/ibv_precheck.out 2>&1; then
        if ! grep -q "PORT_ACTIVE" /tmp/ibv_precheck.out; then
          echo "ERROR: InfiniBand devices present but ibv_devinfo shows no PORT_ACTIVE (see network-operator README)."
          cat /tmp/ibv_precheck.out
          exit 1
        fi
        echo "✓ ibv_devinfo reports PORT_ACTIVE"
      fi
    fi
  fi
fi

if command -v fi_info >/dev/null 2>&1; then
  echo "=== EFA Devices ==="
  fi_info -p efa || echo "No EFA provider found"
fi

# NODE_RANK 0 is the rendezvous leader node; LEADER_ADDR is rank-0 pod IP. Skip waiting for self-DNS on that node.
NUM_NODES="${NUM_NODES:-1}"
NPROC_PER_NODE="${NPROC_PER_NODE:-1}"
NODE_RANK="${NODE_RANK:-0}"

if [ "${NODE_RANK}" = "0" ]; then
  echo "NODE_RANK 0 (leader node): skipping wait for LEADER_ADDR DNS ($LEADER_ADDR)"
else
  echo "Waiting for $LEADER_ADDR to be available"
  while true; do
    if getent hosts "$LEADER_ADDR" >/dev/null 2>&1; then
      resolved_ip=$(getent hosts "$LEADER_ADDR" | awk '{print $1}')
      echo "Successfully resolved $LEADER_ADDR to $resolved_ip"
      break
    fi
    echo "Failed to resolve $LEADER_ADDR, retrying in 2 seconds..."
    sleep 2
  done
fi

echo "=== Starting NCCL AllReduce Test ==="
echo "torch.distributed.run: nnodes=${NUM_NODES} node_rank=${NODE_RANK} nproc_per_node=${NPROC_PER_NODE} master=${LEADER_ADDR}:${MASTER_PORT}"

# One process per GPU; global world size = NUM_NODES * NPROC_PER_NODE
if ! python3 -m torch.distributed.run \
  --nnodes="${NUM_NODES}" \
  --node_rank="${NODE_RANK}" \
  --nproc_per_node="${NPROC_PER_NODE}" \
  --master_addr="${LEADER_ADDR}" \
  --master_port="${MASTER_PORT}" \
  /scripts/nccl_test.py; then
  echo "ERROR: torch.distributed.run / nccl_test.py failed" >&2
  exit 1
fi

echo "=== NCCL Test Complete ==="

log_file="${NCCL_DEBUG_FILE:-/tmp/nccl_debug.log}"

if [ -f "$log_file" ]; then
  echo "--- NCCL debug log (NET transport lines) ---"
  grep "NET/" "$log_file" 2>/dev/null || true
fi

if [ "${NCCL_TEST_EXPECT_IB_TRANSPORT:-false}" = "true" ]; then
  if [ ! -f "$log_file" ]; then
    echo "ERROR: expected NET/IB check but $log_file is missing"
    exit 1
  fi
  if ! grep -q "NET/IB" "$log_file"; then
    echo "ERROR: expected NCCL NET/IB (InfiniBand); multicloud expects e.g. NET/IB : Using ... mlx5_* . Got:"
    grep "NET/" "$log_file" 2>/dev/null || echo "(no NET/ lines)"
    exit 1
  fi
  echo "✓ NCCL debug log contains NET/IB"
fi

cat "$log_file" 2>/dev/null || echo "No NCCL debug log found"
