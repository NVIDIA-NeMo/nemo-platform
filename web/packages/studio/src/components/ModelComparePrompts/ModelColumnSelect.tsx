// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { type FC, useCallback } from 'react';

/** Thin wrapper around ModelSelectV2 for table header use */
export const ModelColumnSelect: FC<{
  modelGroups: ModelWorkspaceGroup[];
  isLoadingModels: boolean;
  value: string | null;
  disabled?: boolean;
  onChange: (ref: string) => void;
}> = ({ modelGroups, isLoadingModels, value, disabled, onChange }) => {
  const selectedModel: ModelSelection | null = value ? { model: value } : null;

  const handleValueChange = useCallback(
    (selection: ModelSelection) => {
      onChange(selection.model);
    },
    [onChange]
  );

  return (
    <ModelSelectV2
      value={selectedModel}
      onValueChange={handleValueChange}
      groups={modelGroups}
      loading={isLoadingModels}
      disabled={disabled}
      hideAdapters
      fullWidth
    />
  );
};
