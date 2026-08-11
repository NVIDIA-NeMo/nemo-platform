// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { QuickActionsMenuRoot } from '@nemo/common/src/components/QuickActionsMenu/QuickActionsMenuRoot';
import { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { modelToFormData } from '@studio/routes/PromptTuningFormRoute/utils';
import { getPromptTuningFormRoute } from '@studio/routes/utils';
import { GitFork, Trash, FolderOpen } from 'lucide-react';
import { FC } from 'react';
import { useNavigate } from 'react-router';

interface Props {
  workspace: string;
  model: ModelEntity;
  onClickOpen: (model: ModelEntity) => void;
  onClickDelete: (model: ModelEntity) => void;
}

export const ModelActionsMenu: FC<Props> = ({ workspace, model, onClickOpen, onClickDelete }) => {
  const navigate = useNavigate();
  const cloneAndEdit = () => {
    const formValues = modelToFormData(model);
    navigate(getPromptTuningFormRoute(workspace), {
      state: { ...formValues, name: `${formValues.name}_copy` },
    });
  };

  return (
    <QuickActionsMenuRoot
      actions={[
        {
          label: 'Open',
          onSelect: () => onClickOpen(model),
          icon: <FolderOpen />,
        },
        {
          label: 'Clone and Edit',
          icon: <GitFork />,
          onSelect: () => cloneAndEdit(),
        },
        {
          label: 'Delete',
          onSelect: () => onClickDelete(model),
          icon: <Trash />,
          danger: true,
        },
      ]}
    />
  );
};
