// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getErrorMessage, swallowConflict } from '@nemo/common/src/api/common/utils';
import { toError } from '@nemo/common/src/utils/logger';
import {
  getFilesListFilesetsQueryKey,
  getModelsListModelsQueryKey,
  useFilesCreateFileset,
  useFilesUploadFile,
  useModelsCreateModel,
  useModelsUpdateModel,
} from '@nemo/sdk/generated/platform/api';
import { FilesetPurpose } from '@nemo/sdk/generated/platform/schema';
import {
  Banner,
  Button,
  Card,
  Flex,
  Grid,
  Spinner,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import {
  CUSTOMIZATION_TEMPLATES,
  type CustomizationTemplate,
} from '@studio/constants/customizationTemplates';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getNewCustomizationJobRoute, getSecretsRoute } from '@studio/routes/utils';
import { fetchAndConvertDataset } from '@studio/util/huggingFaceDataset';
import { useQueryClient } from '@tanstack/react-query';
import { KeyRound } from 'lucide-react';
import { type FC, useState } from 'react';
import { Link, useNavigate } from 'react-router';

interface TemplateCardProps {
  template: CustomizationTemplate;
  workspace: string;
}

const TemplateCard: FC<TemplateCardProps> = ({ template, workspace }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [statusLabel, setStatusLabel] = useState<string>('');

  const isPending = statusLabel !== '';

  const { mutateAsync: createFileset } = useFilesCreateFileset();
  const { mutateAsync: uploadFile } = useFilesUploadFile();
  const { mutateAsync: createModel } = useModelsCreateModel();
  const { mutateAsync: updateModel } = useModelsUpdateModel();

  const requiresHfToken = template.models.some((m) => m.requiresHfToken);

  const handleUseTemplate = async () => {
    setError(null);
    setStatusLabel('Setting up…');
    try {
      for (const model of template.models) {
        setStatusLabel(`Registering ${model.name}…`);
        await swallowConflict(
          createFileset({
            workspace,
            data: {
              name: model.name,
              purpose: FilesetPurpose.model,
              storage: {
                type: 'huggingface',
                repo_id: model.hfRepoId,
                repo_type: 'model',
                ...(model.requiresHfToken ? { token_secret: 'hf-token' } : {}),
              },
            },
          })
        );
        const modelEntity = {
          name: model.name,
          fileset: `${workspace}/${model.name}`,
          ...(model.trustRemoteCode !== undefined
            ? { trust_remote_code: model.trustRemoteCode }
            : {}),
        };
        const createdModel = await swallowConflict(
          createModel({
            workspace,
            data: modelEntity,
          })
        );
        if (!createdModel) {
          await updateModel({
            workspace,
            name: model.name,
            data: {
              fileset: modelEntity.fileset,
              ...(model.trustRemoteCode !== undefined
                ? { trust_remote_code: model.trustRemoteCode }
                : {}),
            },
          });
        }
      }

      const datasetFiles = await fetchAndConvertDataset(
        queryClient,
        template.dataset,
        (fetched, total) => {
          setStatusLabel(`Fetching dataset (${fetched}/${total})…`);
        }
      );

      setStatusLabel('Uploading dataset…');
      await swallowConflict(
        createFileset({
          workspace,
          data: { name: template.dataset.name, purpose: FilesetPurpose.dataset },
        })
      );

      await uploadFile({
        workspace,
        name: template.dataset.name,
        path: 'training.jsonl',
        data: datasetFiles.training,
      });

      await uploadFile({
        workspace,
        name: template.dataset.name,
        path: 'validation.jsonl',
        data: datasetFiles.validation,
      });

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: getModelsListModelsQueryKey(workspace) }),
        queryClient.invalidateQueries({ queryKey: getFilesListFilesetsQueryKey(workspace) }),
      ]);

      const datasetRef = `${workspace}/${template.dataset.name}`;
      navigate(getNewCustomizationJobRoute(workspace), {
        state: { initialValues: template.buildFormSpec(workspace, datasetRef) },
      });
    } catch (e) {
      setError(getErrorMessage(toError(e), 'Failed to set up template'));
    } finally {
      setStatusLabel('');
    }
  };

  return (
    <Card>
      <Stack gap="density-md" className="h-full">
        <Stack gap="density-xs" className="flex-1">
          <Text kind="label/regular/sm" className="text-secondary">
            {template.publisher}
          </Text>
          <Text kind="body/bold/xl">{template.title}</Text>
          <Text kind="body/regular/sm" className="text-secondary">
            {template.description}
          </Text>
        </Stack>

        {/* Footer stats — same three, same order, on every card so the collection
            can be compared by scanning down a column. */}
        <Flex align="center" gap="density-md">
          <Text kind="label/regular/sm" className="text-placeholder">
            {`${template.stats.totalParams} params · ${template.stats.activeParams} active · ${template.stats.gpus} GPUs`}
          </Text>
          {requiresHfToken && (
            <Flex align="center" gap="density-xs" className="text-placeholder">
              <KeyRound size={12} />
              <Text kind="label/regular/sm">HF token</Text>
            </Flex>
          )}
        </Flex>

        <Stack gap="density-sm">
          {error && (
            <Banner kind="inline" status="error">
              {error}
              {/secret|token|auth/i.test(error) ? (
                <>
                  {' '}
                  <Link to={getSecretsRoute(workspace)} className="underline">
                    Set up secrets
                  </Link>
                </>
              ) : null}
            </Banner>
          )}
          <Button
            kind="secondary"
            onClick={() => void handleUseTemplate()}
            disabled={isPending}
            className="w-full"
          >
            {isPending ? (
              <Flex align="center" gap="density-xs">
                <Spinner size="small" className="w-4 h-4" aria-label="Setting up" />
                {statusLabel}
              </Flex>
            ) : (
              'Use Template'
            )}
          </Button>
        </Stack>
      </Stack>
    </Card>
  );
};

export const CustomizationTemplates: FC = () => {
  const workspace = useWorkspaceFromPath();

  return (
    <Stack gap="density-md">
      <Stack gap="density-xs">
        <Text kind="body/regular/sm" className="text-subtle">
          Each recipe fine-tunes a Nemotron mixture-of-experts model to read a database schema and
          turn a plain-English question into a working SQL query, training on BIRD-SQL. The
          expert-parallel and LoRA settings come from the NVIDIA Nemotron cookbook, so you only
          pick a size and start.
        </Text>
      </Stack>
      <Grid cols={{ base: 1, md: 3 }} gap="density-md">
        {CUSTOMIZATION_TEMPLATES.map((template) => (
          <TemplateCard key={template.id} template={template} workspace={workspace} />
        ))}
      </Grid>
    </Stack>
  );
};
