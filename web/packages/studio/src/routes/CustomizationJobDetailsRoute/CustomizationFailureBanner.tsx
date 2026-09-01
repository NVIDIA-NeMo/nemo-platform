// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Button, Stack, Text } from '@nvidia/foundations-react-core';
import type { CustomizationFailure } from '@studio/util/customizationFailure';
import type { FC } from 'react';

interface Props {
  failure: CustomizationFailure;
  onViewLogs?: () => void;
}

export const CustomizationFailureBanner: FC<Props> = ({ failure, onViewLogs }) => {
  const { message, failingStepLabel, errorType, isGeneric } = failure;

  const context = [failingStepLabel && `Failed during ${failingStepLabel}`, errorType]
    .filter(Boolean)
    .join(' · ');

  return (
    <Banner
      kind="inline"
      status="error"
      className="shrink-0"
      data-testid="customization-error-banner"
      slotActions={
        onViewLogs ? (
          <Button kind="secondary" size="small" onClick={onViewLogs}>
            View {failingStepLabel ?? 'job'} logs
          </Button>
        ) : undefined
      }
    >
      <Stack gap="density-xs">
        <Text kind="body/regular/sm" className="whitespace-pre-wrap">
          {message}
        </Text>
        {context && (
          <Text kind="body/regular/sm" className="text-secondary">
            {context}
          </Text>
        )}
        {isGeneric && (
          <Text kind="body/regular/sm" className="text-secondary">
            No specific cause was reported. The logs below have the full output.
          </Text>
        )}
      </Stack>
    </Banner>
  );
};
