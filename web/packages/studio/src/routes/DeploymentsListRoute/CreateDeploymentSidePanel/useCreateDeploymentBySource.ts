/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  filesCreateFileset,
  getFilesListFilesetsQueryKey,
  getModelsListDeploymentConfigsQueryKey,
  getModelsListDeploymentsQueryKey,
  getModelsListModelsQueryKey,
  modelsCreateDeployment,
  modelsCreateDeploymentConfig,
  modelsCreateModel,
} from '@nemo/sdk/generated/platform/api';
import {
  Engine,
  type CreateFilesetRequest,
  type CreateModelDeploymentConfigRequest,
} from '@nemo/sdk/generated/platform/schema';
import { getErrorMessage } from '@studio/api/common/utils';
import {
  additionalEnvsFormToApi,
  configNameFromWizardBaseName,
  deploymentNameFromWizardBaseName,
  WORKSPACE_PICKER_MODEL,
  SOURCE_HF,
  SOURCE_WORKSPACE,
  SOURCE_NGC,
  type WizardFormValues,
} from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/schema';
import {
  HUGGING_FACE_DEPLOYMENT_SOURCE_FIELD,
  HUGGING_FACE_DEPLOYMENT_SOURCE_VALUE,
  huggingFaceSourceFilesetName,
} from '@studio/routes/DeploymentsListRoute/huggingFaceDeploymentArtifacts';
import { NO_SECRET_SELECT_VALUE } from '@studio/routes/SecretsListRoute/SecretSearchableSelect';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';

type ReportStage = (message: string) => void;

function createNimDeploymentConfigRequest(
  request: Omit<CreateModelDeploymentConfigRequest, 'engine'>
): CreateModelDeploymentConfigRequest {
  return {
    ...request,
    engine: Engine.nim,
  };
}

async function createNgcDeployment(
  workspace: string,
  values: WizardFormValues,
  deploymentName: string,
  configName: string,
  reportStage: ReportStage
) {
  const additionalEnvs = additionalEnvsFormToApi(values.additionalEnvs);
  const modelName = values.name.trim();

  reportStage('Creating deployment configuration…');
  await modelsCreateDeploymentConfig(
    workspace,
    createNimDeploymentConfigRequest({
      name: configName,
      model_spec: {
        model_name: modelName,
        lora_enabled: values.loraEnabled,
      },
      executor_config: {
        gpu: values.gpu,
        image_name: values.imageName!.trim(),
        image_tag: values.imageTag!.trim(),
        disk_size: values.diskSize?.trim() || '50Gi',
        ...(additionalEnvs ? { additional_envs: additionalEnvs } : {}),
      },
    })
  );

  reportStage('Creating deployment…');
  await modelsCreateDeployment(workspace, {
    name: deploymentName,
    config: configName,
  });
}

async function createHuggingFaceDeployment(
  workspace: string,
  values: WizardFormValues,
  deploymentName: string,
  configName: string,
  reportStage: ReportStage
) {
  const baseName = values.name.trim();
  const filesetName = huggingFaceSourceFilesetName(deploymentName);
  const modelEntityName = baseName;
  const tokenSecret =
    values.hfTokenSecret && values.hfTokenSecret !== NO_SECRET_SELECT_VALUE
      ? values.hfTokenSecret
      : undefined;

  const storage: CreateFilesetRequest['storage'] = {
    type: 'huggingface',
    repo_id: values.repoId!.trim(),
    repo_type: 'model',
    ...(tokenSecret ? { token_secret: tokenSecret } : {}),
  };

  reportStage('Creating Hugging Face fileset…');
  await filesCreateFileset(workspace, {
    name: filesetName,
    storage,
  });

  reportStage('Registering model…');
  await modelsCreateModel(workspace, {
    name: modelEntityName,
    fileset: `${workspace}/${filesetName}`,
    custom_fields: {
      [HUGGING_FACE_DEPLOYMENT_SOURCE_FIELD]: HUGGING_FACE_DEPLOYMENT_SOURCE_VALUE,
    },
  });

  reportStage('Creating deployment configuration…');
  await modelsCreateDeploymentConfig(
    workspace,
    createNimDeploymentConfigRequest({
      name: configName,
      model_spec: {
        model_namespace: workspace,
        model_name: modelEntityName,
      },
      executor_config: {
        gpu: values.gpu,
      },
      model_entity_id: `${workspace}/${modelEntityName}`,
    })
  );

  reportStage('Creating deployment…');
  await modelsCreateDeployment(workspace, {
    name: deploymentName,
    config: configName,
  });
}

async function createWorkspaceDeployment(
  workspace: string,
  values: WizardFormValues,
  deploymentName: string,
  configName: string,
  reportStage: ReportStage
) {
  let modelNamespace: string;
  let modelName: string;

  if (values.workspacePickerType === WORKSPACE_PICKER_MODEL) {
    if (!values.modelRef) {
      throw new Error('Select a model');
    }
    const parsed = getPartsFromReference(values.modelRef);
    modelNamespace = parsed.workspace;
    modelName = parsed.name;
  } else {
    if (!values.fileset) {
      throw new Error('Select a fileset');
    }
    const fs = getPartsFromReference(values.fileset);
    const baseName = values.name.trim();
    modelNamespace = workspace;
    modelName = baseName;

    reportStage('Registering model from fileset…');
    await modelsCreateModel(workspace, {
      name: modelName,
      fileset: `${fs.workspace}/${fs.name}`,
    });
  }

  reportStage('Creating deployment configuration…');
  await modelsCreateDeploymentConfig(
    workspace,
    createNimDeploymentConfigRequest({
      name: configName,
      model_spec: {
        model_namespace: modelNamespace,
        model_name: modelName,
      },
      executor_config: {
        gpu: values.gpu,
      },
      model_entity_id: `${modelNamespace}/${modelName}`,
    })
  );

  reportStage('Creating deployment…');
  await modelsCreateDeployment(workspace, {
    name: deploymentName,
    config: configName,
  });
}

export function useCreateDeploymentBySource(workspace: string) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const invalidateDeploymentQueries = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: getModelsListDeploymentsQueryKey(workspace) });
    queryClient.invalidateQueries({ queryKey: getModelsListDeploymentConfigsQueryKey(workspace) });
    queryClient.invalidateQueries({ queryKey: getModelsListModelsQueryKey(workspace) });
    queryClient.invalidateQueries({ queryKey: getFilesListFilesetsQueryKey(workspace) });
  }, [queryClient, workspace]);

  const clearStatusMessage = useCallback(() => setStatusMessage(null), []);

  const createDeploymentFromWizard = useCallback(
    async (values: WizardFormValues, onSuccess: () => void) => {
      setSubmitError(null);
      setStatusMessage(null);
      setIsSubmitting(true);
      const baseName = values.name.trim();
      const deploymentName = deploymentNameFromWizardBaseName(baseName);
      const configName = configNameFromWizardBaseName(baseName);
      const reportStage = (message: string) => setStatusMessage(message);

      try {
        if (values.source === SOURCE_NGC) {
          await createNgcDeployment(workspace, values, deploymentName, configName, reportStage);
        } else if (values.source === SOURCE_HF) {
          await createHuggingFaceDeployment(
            workspace,
            values,
            deploymentName,
            configName,
            reportStage
          );
        } else if (values.source === SOURCE_WORKSPACE) {
          await createWorkspaceDeployment(
            workspace,
            values,
            deploymentName,
            configName,
            reportStage
          );
        }

        toast.success('Deployment created successfully.');
        invalidateDeploymentQueries();
        onSuccess();
      } catch (e) {
        setSubmitError(e instanceof Error ? getErrorMessage(e) : 'An unexpected error occurred');
        toast.error('Failed to create deployment. Check the message below and try again.');
      } finally {
        setIsSubmitting(false);
        setStatusMessage(null);
      }
    },
    [invalidateDeploymentQueries, toast, workspace]
  );

  return {
    createDeploymentFromWizard,
    isSubmitting,
    submitError,
    setSubmitError,
    statusMessage,
    clearStatusMessage,
  };
}
