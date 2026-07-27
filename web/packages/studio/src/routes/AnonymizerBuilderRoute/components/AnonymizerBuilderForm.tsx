// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useAnonymizerCreateRunJob } from '@nemo/sdk/generated/anonymizer/api';
import type { RunJob } from '@nemo/sdk/generated/anonymizer/schema';
import {
  Banner,
  Button,
  Divider,
  Flex,
  Panel,
  SegmentedControl,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { parseAnonymizerApiError } from '@studio/routes/AnonymizerBuilderRoute/apiErrors';
import { ColumnsSection } from '@studio/routes/AnonymizerBuilderRoute/components/ColumnsSection';
import { DataSourceSection } from '@studio/routes/AnonymizerBuilderRoute/components/DataSourceSection';
import { EntitiesSection } from '@studio/routes/AnonymizerBuilderRoute/components/EntitiesSection';
import { GenerationSection } from '@studio/routes/AnonymizerBuilderRoute/components/GenerationSection';
import { ModelSettingsSection } from '@studio/routes/AnonymizerBuilderRoute/components/ModelSettingsSection';
import {
  buildAnonymizerJobRequest,
  type AnonymizerFormData,
} from '@studio/routes/AnonymizerBuilderRoute/schema';
import { useDefaultRoleModels } from '@studio/routes/AnonymizerBuilderRoute/useDefaultRoleModels';
import { getWorkspaceAnonymizerRoute, getWorkspaceJobDetailRoute } from '@studio/routes/utils';
import { useState, type FC } from 'react';
import { useFormContext } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';

const TAB_SOURCE = 'source';
const TAB_MODEL_SETTINGS = 'model-settings';

const PANEL_TABS = [
  { value: TAB_SOURCE, children: 'Source' },
  { value: TAB_MODEL_SETTINGS, children: 'Model Settings' },
];

export const AnonymizerBuilderForm: FC = () => {
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();
  const form = useFormContext<AnonymizerFormData>();
  const [activeTab, setActiveTab] = useState<string>(TAB_SOURCE);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);

  const { isLoading: isLoadingModels } = useDefaultRoleModels();

  const createJob = useAnonymizerCreateRunJob({
    mutation: {
      onSuccess: (job: RunJob) =>
        navigate(
          job.name
            ? getWorkspaceJobDetailRoute(workspace, job.name)
            : getWorkspaceAnonymizerRoute(workspace)
        ),
      onError: (error) => {
        const { fieldErrors, generalMessages } = parseAnonymizerApiError(error);
        fieldErrors.forEach(({ field, message }) =>
          form.setError(field, { type: 'server', message })
        );
        if (fieldErrors.length) setActiveTab(TAB_SOURCE);
        setSubmitError(
          generalMessages.length
            ? generalMessages.join(' ')
            : fieldErrors.length
              ? undefined
              : getErrorMessage(error, 'Failed to create anonymizer job')
        );
      },
    },
  });

  const onSubmit = form.handleSubmit(
    (values) => {
      setSubmitError(undefined);
      createJob.mutate({ workspace, data: buildAnonymizerJobRequest(values) });
    },
    (errors) => {
      const onlyModelErrors = Object.keys(errors).every((key) => key === 'roleModels');
      setActiveTab(onlyModelErrors ? TAB_MODEL_SETTINGS : TAB_SOURCE);
      setSubmitError('Please complete the required fields highlighted below.');
    }
  );

  const handleCancel = () => navigate(getWorkspaceAnonymizerRoute(workspace));

  return (
    <form className="h-full" noValidate onSubmit={onSubmit}>
      <Flex className="h-full" gap="0">
        <Panel
          className="w-[400px] h-full"
          elevation="high"
          density="standard"
          attributes={{ PanelContent: { className: 'flex-1 min-h-0 overflow-auto' } }}
          slotFooter={
            <Flex gap="density-md" justify="end">
              <Button
                kind="tertiary"
                type="button"
                disabled={createJob.isPending}
                onClick={handleCancel}
              >
                Cancel
              </Button>
              <Button
                kind="primary"
                color="brand"
                type="submit"
                disabled={createJob.isPending || isLoadingModels}
              >
                Full Run
              </Button>
            </Flex>
          }
        >
          <Stack gap="density-2xl">
            <SegmentedControl
              className="w-full"
              value={activeTab}
              onValueChange={setActiveTab}
              items={PANEL_TABS}
            />

            {submitError && (
              <Banner kind="inline" status="error">
                {submitError}
              </Banner>
            )}

            <div className={activeTab === TAB_SOURCE ? undefined : 'hidden'}>
              <Stack gap="density-2xl">
                <DataSourceSection />
                <Divider orientation="horizontal" width="small" />
                <GenerationSection />
                <Divider orientation="horizontal" width="small" />
                <ColumnsSection />
                <Divider orientation="horizontal" width="small" />
                <EntitiesSection />
              </Stack>
            </div>
            <div className={activeTab === TAB_MODEL_SETTINGS ? undefined : 'hidden'}>
              <ModelSettingsSection />
            </div>
          </Stack>
        </Panel>

        <Flex className="flex-1 h-full" align="center" justify="center">
          <Text kind="body/regular/md">Your records preview will appear here</Text>
        </Flex>
      </Flex>
    </form>
  );
};
