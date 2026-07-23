// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  StatusBadge,
  type StatusConfigEntry,
} from '@nemo/common/src/components/StatusBadge';
import type { EvalAuthorRunStatus } from '@studio/api/optimizer';
import { Ban, CircleCheck, CircleDashed, CircleX, LoaderCircle } from 'lucide-react';
import type { FC } from 'react';

const STATUS_CONFIG: Record<EvalAuthorRunStatus, StatusConfigEntry> = {
  created: { label: 'Created', color: 'gray', icon: CircleDashed },
  running: { label: 'Running', color: 'blue', icon: LoaderCircle },
  succeeded: { label: 'Succeeded', color: 'green', icon: CircleCheck },
  failed: { label: 'Failed', color: 'red', icon: CircleX },
  cancelled: { label: 'Cancelled', color: 'yellow', icon: Ban },
};

export const EvalAuthorRunStatusBadge: FC<{ status: EvalAuthorRunStatus }> = ({ status }) => (
  <StatusBadge status={status} statusConfig={STATUS_CONFIG} />
);
