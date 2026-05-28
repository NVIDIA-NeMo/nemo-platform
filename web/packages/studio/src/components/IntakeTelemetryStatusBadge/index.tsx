// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { SpanStatus } from '@nemo/sdk/generated/platform/schema';
import { Badge, type BadgeProps } from '@nvidia/foundations-react-core';
import { Ban, CircleCheck, CircleHelp, CircleX } from 'lucide-react';
import type { ComponentType, SVGProps } from 'react';

interface StatusConfig {
  label: string;
  color: Exclude<BadgeProps['color'], null>;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

const STATUS_CONFIG: Record<SpanStatus, StatusConfig> = {
  success: {
    label: 'Success',
    color: 'green',
    icon: CircleCheck,
  },
  error: {
    label: 'Error',
    color: 'red',
    icon: CircleX,
  },
  cancelled: {
    label: 'Cancelled',
    color: 'yellow',
    icon: Ban,
  },
  unknown: {
    label: 'Unknown',
    color: 'gray',
    icon: CircleHelp,
  },
};

export interface IntakeTelemetryStatusBadgeProps {
  status: SpanStatus | undefined;
}

export const IntakeTelemetryStatusBadge = ({ status }: IntakeTelemetryStatusBadgeProps) => {
  const config = STATUS_CONFIG[status ?? 'unknown'];
  const Icon = config.icon;

  return (
    <Badge color={config.color} kind="solid">
      <Icon width="12px" height="12px" role="img" />
      {config.label}
    </Badge>
  );
};
