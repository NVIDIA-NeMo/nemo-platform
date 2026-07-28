// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RunJob } from '@nemo/sdk/generated/anonymizer/schema';

export const ANONYMIZER_POLLING_INTERVAL_MS = 5000;

export const jobStrategy = (job: RunJob): string | undefined => {
  const config = job.spec?.request?.config;
  if (!config) return undefined;
  if (config.rewrite) return 'rewrite';
  return (config.replace as { kind?: string } | undefined)?.kind;
};

export const jobSource = (job: RunJob): string | undefined => job.spec?.request?.data?.source;
