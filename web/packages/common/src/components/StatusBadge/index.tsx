// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  badgeStatus,
  type BadgeStatus,
  type StatusConfigEntry,
} from '@nemo/common/src/components/StatusBadge/badgeStatus';
import { Badge } from '@nvidia/foundations-react-core';

export type { BadgeStatus, StatusConfigEntry };

type AnyEntry = {
  label: string;
  color?: StatusConfigEntry['color'];
  icon?: StatusConfigEntry['icon'];
};

const CONFIG_DEFAULT: AnyEntry = { label: 'Unknown', color: 'gray' };

interface StatusBadgeProps<T = string> {
  status: BadgeStatus<T> | string | undefined;
  statusConfig?: Record<string, StatusConfigEntry>;
  fallback?: StatusConfigEntry;
  label?: string;
}

export const StatusBadge = <T extends string = string>({
  status,
  statusConfig,
  fallback,
  label: labelOverride,
}: StatusBadgeProps<T>) => {
  let config: AnyEntry;

  if (statusConfig) {
    config =
      (status !== undefined ? statusConfig[status] : undefined) ?? fallback ?? CONFIG_DEFAULT;
  } else {
    if (!status) {
      config = badgeStatus.default;
    } else {
      const statusKey = String(status).toLowerCase();
      config =
        statusKey in badgeStatus
          ? badgeStatus[statusKey as keyof typeof badgeStatus]
          : badgeStatus.default;
    }
  }

  const label = labelOverride ?? config.label;
  const Icon = config.icon;

  return (
    <Badge color={config.color} kind="solid">
      {Icon ? <Icon width="12px" height="12px" aria-hidden="true" /> : null}
      {label}
    </Badge>
  );
};
