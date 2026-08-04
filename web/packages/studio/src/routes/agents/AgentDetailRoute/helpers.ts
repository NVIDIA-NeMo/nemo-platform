// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export function deploymentStatusColor(status?: string): 'green' | 'red' | 'yellow' | undefined {
  if (status === 'running') return 'green';
  if (status === 'error' || status === 'failed') return 'red';
  if (status === 'pending' || status === 'starting' || status === 'deleting') return 'yellow';
  return undefined;
}
