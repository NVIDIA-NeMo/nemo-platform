// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { useAnonymizerCreateRunJob } from '@nemo/sdk/generated/anonymizer/api';
import type { RunJob } from '@nemo/sdk/generated/anonymizer/schema';
import {
  Banner,
  Button,
  Divider,
  Flex,
  Panel,
  Stack,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ANONYMIZER_ENABLED } from '@studio/constants/environment';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { ColumnsSection } from '@studio/routes/AnonymizerBuilderRoute/components/ColumnsSection';
import { DataSourceSection } from '@studio/routes/AnonymizerBuilderRoute/components/DataSourceSection';
import { EntitiesSection } from '@studio/routes/AnonymizerBuilderRoute/components/EntitiesSection';
import { GenerationSection } from '@studio/routes/AnonymizerBuilderRoute/components/GenerationSection';
import { ModelSettingsSection } from '@studio/routes/AnonymizerBuilderRoute/components/ModelSettingsSection';
import {
  anonymizerFormSchema,
  buildAnonymizerJobRequest,
  getAnonymizerFormDefaults,
} from '@studio/routes/AnonymizerBuilderRoute/schema';
import { getAnonymizerJobRoute, getWorkspaceAnonymizerRoute } from '@studio/routes/utils';
import { FC, useState } from 'react';
import { FormProvider, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';

const TAB_SOURCE = 'source';
const TAB_MODEL_SETTINGS = 'model-settings';

export const AnonymizerBuilderRoute: FC | null = ANONYMIZER_ENABLED
  ? () => {
      const navigate = useNavigate();
      const workspace = useWorkspaceFromPath();
      const [activeTab, setActiveTab] = useState<string>(TAB_SOURCE);
      const [submitError, setSubmitError] = useState<string | undefined>(undefined);

      useBreadcrumbs({
        items: [{ slotLabel: 'Anonymizer' }, { slotLabel: 'Anonymize Data' }],
      });

      const form = useForm({
        mode: 'onChange',
        resolver: zodResolver(anonymizerFormSchema),
        defaultValues: getAnonymizerFormDefaults(),
      });

      const createJob = useAnonymizerCreateRunJob({
        mutation: {
          onSuccess: (job: RunJob) =>
            navigate(
              job.name
                ? getAnonymizerJobRoute(workspace, job.name)
                : getWorkspaceAnonymizerRoute(workspace)
            ),
          onError: (error) =>
            setSubmitError(getErrorMessage(error, 'Failed to create anonymizer job')),
        },
      });

      const onSubmit = form.handleSubmit(
        (values) => {
          setSubmitError(undefined);
          createJob.mutate({ workspace, data: buildAnonymizerJobRequest(values) });
        },
        (errors) => {
          if (errors.roleModels) setActiveTab(TAB_MODEL_SETTINGS);
        }
      );

      const handleCancel = () => navigate(getWorkspaceAnonymizerRoute(workspace));

      return (
        <AccessibleTitle title="Anonymize Data">
          <FormProvider {...form}>
            <form className="h-full" onSubmit={onSubmit}>
              <Flex className="h-full" gap="0">
                <Panel
                  className="w-[400px] h-full overflow-auto"
                  elevation="high"
                  density="standard"
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
                        disabled={createJob.isPending}
                      >
                        Full Run
                      </Button>
                    </Flex>
                  }
                >
                  <Stack gap="density-2xl">
                    <TabsRoot value={activeTab}>
                      <TabsList>
                        <TabsTrigger value={TAB_SOURCE} onClick={() => setActiveTab(TAB_SOURCE)}>
                          Source
                        </TabsTrigger>
                        <TabsTrigger
                          value={TAB_MODEL_SETTINGS}
                          onClick={() => setActiveTab(TAB_MODEL_SETTINGS)}
                        >
                          Model Settings
                        </TabsTrigger>
                      </TabsList>
                    </TabsRoot>

                    {submitError && (
                      <Banner kind="inline" status="error">
                        {submitError}
                      </Banner>
                    )}

                    {activeTab === TAB_SOURCE ? (
                      <Stack gap="density-2xl">
                        <DataSourceSection />
                        <Divider orientation="horizontal" width="small" />
                        <GenerationSection />
                        <Divider orientation="horizontal" width="small" />
                        <ColumnsSection />
                        <Divider orientation="horizontal" width="small" />
                        <EntitiesSection />
                      </Stack>
                    ) : (
                      <ModelSettingsSection />
                    )}
                  </Stack>
                </Panel>

                <Flex className="flex-1 h-full" align="center" justify="center">
                  <Text kind="body/regular/md">Your records preview will appear here</Text>
                </Flex>
              </Flex>
            </form>
          </FormProvider>
        </AccessibleTitle>
      );
    }
  : null;
