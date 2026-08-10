// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  WorkspaceModelSelect,
  type ModelSelection,
} from '@nemo/common/src/components/ModelSelectV2';
import { hasModelProvider } from '@nemo/common/src/utils/models';
import { type FC, useCallback } from 'react';

/** Thin wrapper around ModelSelectV2 for table header use */
export const ModelColumnSelect: FC<{
  workspace: string;
  value: string | null;
  disabled?: boolean;
  onChange: (ref: string) => void;
}> = ({ workspace, value, disabled, onChange }) => {
  const selectedModel: ModelSelection | null = value ? { model: value } : null;

  const handleValueChange = useCallback(
    (selection: ModelSelection) => {
      onChange(selection.model);
    },
    [onChange]
  );

  return (
    <WorkspaceModelSelect
      workspace={workspace}
      include={hasModelProvider}
      value={selectedModel}
      onValueChange={handleValueChange}
      disabled={disabled}
      hideAdapters
      fullWidth
    />
  );
};
