// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';

// Customizer uses Platform SDK status
export const CJobCancellableStatuses: PlatformJobStatus[] = [
  PlatformJobStatus.created,
  PlatformJobStatus.pending,
  PlatformJobStatus.active, // was 'running'
];
export const CJobLaunchableStatuses: PlatformJobStatus[] = [PlatformJobStatus.completed];

export const CJobTerminalStatuses: PlatformJobStatus[] = [
  PlatformJobStatus.completed,
  PlatformJobStatus.error, // was 'failed'
  PlatformJobStatus.cancelled,
];
export const PlatformJobTerminalStatuses: PlatformJobStatus[] = [
  PlatformJobStatus.completed,
  PlatformJobStatus.cancelled,
  PlatformJobStatus.error,
];
