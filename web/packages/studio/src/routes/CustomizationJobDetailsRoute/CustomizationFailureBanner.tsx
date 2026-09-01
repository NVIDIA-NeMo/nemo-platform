// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner, Button, Stack, Text } from '@nvidia/foundations-react-core';
import type { CustomizationFailure } from '@studio/util/customizationFailure';
import type { FC } from 'react';

interface Props {
  failure: CustomizationFailure;
  /** Opens the Logs tab scoped to the failing step. Omitted when the step is unknown. */
  onViewLogs?: () => void;
}

/**
 * Why a customization job failed, above the tabs so it stays visible on Overview and Logs alike.
 *
 * The message comes from `resolveCustomizationFailure`, which digs the mapped cause out of the
 * step/task status tree — the job record itself only carries generic infrastructure text.
 */
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
        {/* Mapped messages are multi-sentence prose with numbered remediation steps. */}
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
