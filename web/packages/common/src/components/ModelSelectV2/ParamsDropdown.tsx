// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  DEFAULT_INFERENCE_PARAMS,
  InferenceParamsSliders,
  type InferenceParamsSliderValues,
} from '@nemo/common/src/components/InferenceParamsSliders';
import {
  Button,
  DropdownContent,
  DropdownRoot,
  DropdownTrigger,
  Flex,
  Text,
} from '@nvidia/foundations-react-core';
import { ChevronDown, SlidersHorizontal } from 'lucide-react';
import { FC, useMemo } from 'react';

export interface ParamsDropdownProps {
  disabled?: boolean;
  size?: 'small' | 'medium' | 'large';
  /** Show the "Params" text label next to the icon. Defaults to true. */
  showLabel?: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  inferenceParams?: Partial<InferenceParamsSliderValues>;
  onInferenceParamsChange?: (params: Partial<InferenceParamsSliderValues>) => void;
}

export const ParamsDropdown: FC<ParamsDropdownProps> = ({
  disabled = false,
  size = 'medium',
  showLabel = true,
  open,
  onOpenChange,
  inferenceParams = {},
  onInferenceParamsChange,
}) => {
  const resolvedParams = useMemo(
    (): InferenceParamsSliderValues => ({
      ...DEFAULT_INFERENCE_PARAMS,
      ...inferenceParams,
    }),
    [inferenceParams]
  );

  return (
    <DropdownRoot open={open} onOpenChange={onOpenChange}>
      <DropdownTrigger asChild showChevron={false}>
        <Button
          kind="secondary"
          size={size}
          disabled={disabled}
          aria-label="Model parameters"
          data-testid="params-dropdown-trigger"
          className="shrink-0 !border-[var(--border-color-interaction-base)] !bg-[var(--background-color-interaction-base)] hover:!border-[var(--border-color-interaction-hover)] [&[data-state=open]]:!border-[var(--border-color-interaction-selected)]"
        >
          <Flex align="center" gap="density-sm">
            <SlidersHorizontal size={16} />
            {showLabel && (
              <Text kind={size === 'small' ? 'label/regular/sm' : 'label/regular/md'}>Params</Text>
            )}
            <ChevronDown size={16} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
          </Flex>
        </Button>
      </DropdownTrigger>
      <DropdownContent
        align="end"
        side="bottom"
        className="p-0"
        data-testid="params-dropdown-content"
      >
        <InferenceParamsSliders
          value={resolvedParams}
          onChange={(next) => onInferenceParamsChange?.(next)}
          disabled={disabled}
          defaults={DEFAULT_INFERENCE_PARAMS}
        />
      </DropdownContent>
    </DropdownRoot>
  );
};
