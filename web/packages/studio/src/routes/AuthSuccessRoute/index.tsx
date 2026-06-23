// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { entitiesCreateWorkspace, entitiesGetWorkspace } from '@nemo/sdk/generated/platform/api';
import { Loading } from '@studio/components/Layouts/Loading';
import { useAuthProfile } from '@studio/providers/auth';
import { logger } from '@studio/util/logger';
import { isAxiosError } from 'axios';
import { FC, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

async function createWorkspaceIfNotExists(workspace: string, name: string) {
  try {
    await entitiesGetWorkspace(workspace);
  } catch (error) {
    if (isAxiosError(error) && (error.response?.status === 404 || error.response?.status === 403)) {
      await entitiesCreateWorkspace({
        name: workspace,
        description: `Automatically created workspace for ${name}`,
      });
    } else {
      throw error;
    }
  }
}

export const AuthSuccessRoute: FC = () => {
  const profile = useAuthProfile();
  const navigate = useNavigate();
  const toast = useToast();

  const handleAuthenticated = useCallback(async () => {
    if (profile) {
      const { workspace, name } = profile;
      try {
        await createWorkspaceIfNotExists(workspace, name);
      } catch (error) {
        toast.error(`Failed to create workspace ${workspace}: ${error}`);
        logger.error(`Failed to create workspace ${workspace}: ${error}`);
      }

      if (profile.state?.path) {
        navigate({
          pathname: profile.state.path,
          search: profile.state.search,
        });
      } else {
        navigate('/');
      }
    }
  }, [toast, navigate, profile]);

  useEffect(() => {
    handleAuthenticated();
  }, [handleAuthenticated]);

  return <Loading />;
};
