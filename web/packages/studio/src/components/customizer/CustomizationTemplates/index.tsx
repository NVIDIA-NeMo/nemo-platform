// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

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
import { getErrorMessage, swallowConflict } from '@studio/api/common/utils';
import {
  CUSTOMIZATION_TEMPLATES,
  type CustomizationTemplate,
  type CustomizationTemplateDataset,
} from '@studio/constants/customizationTemplates';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getNewCustomizationJobRoute, getSecretsRoute } from '@studio/routes/utils';
import { toError } from '@studio/util/logger';
import { useQueryClient } from '@tanstack/react-query';
import { KeyRound } from 'lucide-react';
import { type FC, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

const HF_DATASETS_API = 'https://datasets-server.huggingface.co/rows';
const HF_MAX_ROWS_PER_REQUEST = 100;

const toJsonlBlob = (rows: Record<string, unknown>[]): Blob =>
  new Blob([rows.map((row) => JSON.stringify(row)).join('\n')], {
    type: 'application/x-ndjson',
  });

const fetchAndConvertDataset = async (
  dataset: CustomizationTemplateDataset,
  onProgress: (fetched: number, total: number) => void
): Promise<{ training: Blob; validation: Blob }> => {
  const total = dataset.trainingRowCount + dataset.validationRowCount;
  const pageCount = Math.ceil(total / HF_MAX_ROWS_PER_REQUEST);
  let fetched = 0;

  const pages = await Promise.all(
    Array.from({ length: pageCount }, async (_, i) => {
      const offset = i * HF_MAX_ROWS_PER_REQUEST;
      const length = Math.min(HF_MAX_ROWS_PER_REQUEST, total - offset);
      const url = new URL(HF_DATASETS_API);
      url.searchParams.set('dataset', dataset.hfDataset);
      url.searchParams.set('config', dataset.hfConfig);
      url.searchParams.set('split', dataset.hfSplit);
      url.searchParams.set('offset', String(offset));
      url.searchParams.set('length', String(length));
      const r = await fetch(url.toString());
      if (!r.ok) throw new Error(`Failed to fetch dataset from Hugging Face: ${r.statusText}`);
      const page = (await r.json()) as { rows: Array<{ row: Record<string, unknown> }> };
      fetched += page.rows.length;
      onProgress(Math.min(fetched, total), total);
      return page;
    })
  );

  const rows = pages
    .flatMap((p) => p.rows)
    .map((r) => dataset.convertRow(r.row))
    .filter((row): row is Record<string, unknown> => row !== null);

  const trainingRows = rows.slice(0, dataset.trainingRowCount);
  const validationRows = rows.slice(
    dataset.trainingRowCount,
    dataset.trainingRowCount + dataset.validationRowCount
  );

  if (trainingRows.length === 0) throw new Error('No valid training rows were found.');
  if (dataset.validationRowCount > 0 && validationRows.length === 0) {
    throw new Error('No valid validation rows were found.');
  }

  return { training: toJsonlBlob(trainingRows), validation: toJsonlBlob(validationRows) };
};

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

      const datasetFiles = await fetchAndConvertDataset(template.dataset, (fetched, total) => {
        setStatusLabel(`Fetching dataset (${fetched}/${total})…`);
      });

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
    <Card className="h-full">
      <Stack gap="density-md" className="h-full">
        <Stack gap="density-xs" className="flex-1">
          <Flex align="center" justify="between">
            <Text kind="label/bold/sm" className="text-subtle">
              {template.trainingLabel}
            </Text>
            {requiresHfToken && (
              <Flex align="center" gap="density-xs" className="text-subtle">
                <KeyRound size={12} />
                <Text kind="label/regular/xs">HF token</Text>
              </Flex>
            )}
          </Flex>
          <Text kind="title/sm">{template.title}</Text>
          <Text kind="body/regular/sm" className="text-subtle">
            {template.description}
          </Text>
        </Stack>

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
      <Text kind="label/bold/sm" className="text-subtle uppercase tracking-wide">
        Quick Start Templates
      </Text>
      <Grid cols={{ base: 1, md: 2, lg: 4 }} gap="density-md">
        {CUSTOMIZATION_TEMPLATES.map((template) => (
          <TemplateCard key={template.id} template={template} workspace={workspace} />
        ))}
      </Grid>
    </Stack>
  );
};
