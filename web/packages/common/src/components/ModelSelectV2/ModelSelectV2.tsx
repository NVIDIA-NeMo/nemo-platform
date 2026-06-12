// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelDropdown } from '@nemo/common/src/components/ModelSelectV2/ModelDropdown';
import { ParamsDropdown } from '@nemo/common/src/components/ModelSelectV2/ParamsDropdown';
import type { ModelSelectV2Props } from '@nemo/common/src/components/ModelSelectV2/types';
import { Group } from '@nvidia/foundations-react-core';
import { FC, useState } from 'react';

export const ModelSelectV2: FC<ModelSelectV2Props> = ({
  value,
  onValueChange,
  groups,
  loading,
  disabled,
  placeholder,
  showModelTypeToggle,
  defaultModelType,
  showParams = false,
  hideAdapters = false,
  fullWidth = false,
  dropdownSide,
  inferenceParams,
  onInferenceParamsChange,
  onOpenChange,
  'aria-label': ariaLabel,
}) => {
  const [modelOpen, setModelOpen] = useState(false);
  const [paramsOpen, setParamsOpen] = useState(false);

  const handleModelOpenChange = (open: boolean) => {
    setModelOpen(open);
    if (open) setParamsOpen(false);
    onOpenChange?.(open);
  };

  const handleParamsOpenChange = (open: boolean) => {
    setParamsOpen(open);
    if (open) setModelOpen(false);
  };

  const modelDropdown = (
    <ModelDropdown
      value={value}
      onValueChange={onValueChange}
      groups={groups}
      loading={loading}
      disabled={disabled}
      placeholder={placeholder}
      showModelTypeToggle={showModelTypeToggle}
      defaultModelType={defaultModelType}
      hideAdapters={hideAdapters}
      fullWidth={fullWidth}
      dropdownSide={dropdownSide}
      open={modelOpen}
      onOpenChange={handleModelOpenChange}
    />
  );

  if (!showParams) return modelDropdown;

  return (
    <Group
      aria-label={ariaLabel ?? 'Model selector'}
      className={`max-w-full overflow-hidden ${fullWidth ? 'w-full' : ''}`}
    >
      {modelDropdown}
      <ParamsDropdown
        disabled={disabled}
        open={paramsOpen}
        onOpenChange={handleParamsOpenChange}
        inferenceParams={inferenceParams}
        onInferenceParamsChange={onInferenceParamsChange}
      />
    </Group>
  );
};
