# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import time
from datetime import timedelta

import torch
import torch.distributed as dist


def run_nccl_test():
    """Run under torch.distributed.run (torchrun): one process per GPU, global all_reduce."""
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    rank = int(os.environ.get("RANK", "0"))
    world_size = int(os.environ.get("WORLD_SIZE", "1"))

    if not os.environ.get("MASTER_ADDR"):
        os.environ["MASTER_ADDR"] = os.environ.get("LEADER_ADDR", "127.0.0.1")

    os.environ.setdefault("MASTER_PORT", "29500")

    master_addr = os.environ.get("MASTER_ADDR", "127.0.0.1")

    print("=== NCCL Test Debug Info ===")
    print(f"Rank: {rank}")
    print(f"Local Rank: {local_rank}")
    print(f"World Size: {world_size}")
    print(f"Master Address: {master_addr}")
    print(f"CUDA Available: {torch.cuda.is_available()}")
    print(f"CUDA Device Count: {torch.cuda.device_count()}")
    if torch.cuda.is_available():
        nvis = torch.cuda.device_count()
        if nvis <= local_rank:
            print(
                f"ERROR: LOCAL_RANK={local_rank} but only {nvis} visible GPU(s)",
                file=sys.stderr,
            )
            sys.exit(1)
        torch.cuda.set_device(local_rank)
        print(f"Current CUDA Device: {torch.cuda.current_device()}")
        print(f"Device Name: {torch.cuda.get_device_name(local_rank)}")
    else:
        print("ERROR: CUDA is not available; NCCL test requires GPUs.", file=sys.stderr)
        sys.exit(1)
    print("================================")

    print("Environment variables set:")
    print(f"  MASTER_ADDR: {os.environ.get('MASTER_ADDR', '')}")
    print(f"  MASTER_PORT: {os.environ.get('MASTER_PORT', '')}")
    print(f"  RANK: {os.environ.get('RANK', '')}")
    print(f"  WORLD_SIZE: {os.environ.get('WORLD_SIZE', '')}")
    print(f"  LOCAL_RANK: {os.environ.get('LOCAL_RANK', '')}")

    print(f"Initializing NCCL backend... Rank: {rank}, World: {world_size}, Master: {master_addr}")
    dist.init_process_group(backend="nccl", timeout=timedelta(minutes=5))

    print(f"Rank: {dist.get_rank()}, World Size: {dist.get_world_size()}")
    print(f"CUDA Device: {torch.cuda.current_device()}")

    min_bw_raw = os.environ.get("NCCL_TEST_MIN_BANDWIDTH_MBPS", "0") or "0"
    try:
        min_bw = float(min_bw_raw)
    except ValueError:
        min_bw = 0.0

    test_sizes = [1, 4, 16, 64, 256, 1024, 4096]
    bw_max_large = 0

    for size_mb in test_sizes:
        elements = (size_mb * 1024 * 1024) // 4
        tensor = torch.randn(elements, device="cuda")

        print(f"Testing {size_mb}MB tensor ({elements} elements)...")

        for _ in range(5):
            dist.all_reduce(tensor)
            torch.cuda.synchronize()

        start_time = time.time()
        for _ in range(10):
            dist.all_reduce(tensor)
            torch.cuda.synchronize()
        end_time = time.time()

        avg_time = (end_time - start_time) / 10
        bandwidth = (size_mb * 2) / avg_time

        print(f"Size: {size_mb}MB, Time: {avg_time:.4f}s, Bandwidth: {bandwidth:.2f} MB/s")
        if size_mb == 1024 or size_mb == 4096:
            if bandwidth > bw_max_large:
                bw_max_large = bandwidth

    slow = min_bw > 0.0 and bw_max_large < min_bw
    if slow:
        print(
            f"ERROR: AllReduce best bandwidth at large message sizes (1024MB/4096MB) "
            f"bw_max_large={bw_max_large:.2f} MB/s is below minimum {min_bw:.2f} MB/s "
            "(slow or misconfigured interconnect; expect ~8000+ MB/s on IB + GPU Direct RDMA).",
            file=sys.stderr,
        )
        dist.destroy_process_group()
        sys.exit(1)

    print("NCCL test completed successfully!")
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    run_nccl_test()
