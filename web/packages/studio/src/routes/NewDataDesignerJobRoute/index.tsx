// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { CreateFilesetStart } from '@studio/components/CreateFilesetStart';
import type { StartOptionId } from '@studio/components/CreateFilesetStart/types';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getDataDesignerJobBuildRoute, getDataDesignerJobListRoute } from '@studio/routes/utils';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';

export const NewDataDesignerJobRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();

  useBreadcrumbs({
    items: [
      { href: getDataDesignerJobListRoute(workspace), slotLabel: 'Data Designer' },
      { slotLabel: 'New fileset' },
    ],
  });

  const handleContinue = (optionId: StartOptionId, templateId?: string) => {
    if (optionId === 'scratch') {
      navigate(getDataDesignerJobBuildRoute(workspace));
    } else if (optionId === 'template' && templateId) {
      navigate(`${getDataDesignerJobBuildRoute(workspace)}?template=${templateId}`);
    }
  };

  return (
    <AccessibleTitle title="Create a fileset">
      <CreateFilesetStart onContinue={handleContinue} />
    </AccessibleTitle>
  );
};
