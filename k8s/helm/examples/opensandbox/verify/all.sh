#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Run both OpenSandbox runtime verifications (shared-kernel then kata-qemu).
# kata-qemu.sh requires the Kata server overlay; it fails if that release is absent.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "==> shared-kernel"
"${DIR}/shared-kernel.sh"
echo "==> kata-qemu"
"${DIR}/kata-qemu.sh"
echo "==> PASS all OpenSandbox runtime verifications"
