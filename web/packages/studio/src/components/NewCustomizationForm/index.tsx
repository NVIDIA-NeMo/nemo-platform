// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import { isDefined } from '@nemo/common/src/utils/isDefined';
import { useFilesRetrieveFileset, useModelsListModels } from '@nemo/sdk/generated/platform/api';
import { type FilesetOutput as Fileset } from '@nemo/sdk/generated/platform/schema';
import { useCustomizationCreateJob } from '@nemo/sdk/vendored/customizer/api';
import { type CustomizationJob as CustomizationJobOutput } from '@nemo/sdk/vendored/customizer/schema';
import { CustomizationCreateJobBody } from '@nemo/sdk/vendored/customizer/zod';
import {
  Banner,
  Button,
  Divider,
  Flex,
  Panel,
  Stack,
  PageHeader,
} from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { CustomizationFilesetSelect } from '@studio/components/customizer/CustomizationFilesetSelect';
import {
  ComputeResources,
  GeneralParameters,
  DpoParameters,
} from '@studio/components/customizer/CustomizationHyperparameters';
import { NEW_CUSTOMIZATION_FORM_HYP_DEFAULT_VALUES } from '@studio/components/NewCustomizationForm/constants';
import { ModelSelectionSection } from '@studio/components/NewCustomizationForm/ModelSelectionSection';
import { ParameterEfficiency } from '@studio/components/NewCustomizationForm/ParameterEfficiency';
import { TrainingMethodSelect } from '@studio/components/NewCustomizationForm/TrainingMethodSelect';
import {
  refineModelName,
  refineModelNameConfig,
} from '@studio/components/NewCustomizationForm/utils';
import { DEFAULT_LARGE_PAGE_SIZE } from '@studio/constants/constants';
import { useCustomizationFilesPreview } from '@studio/hooks/useCustomizationFiles';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  getWorkspaceCustomizationJobDetailsRoute,
  getCustomizationJobListRoute,
} from '@studio/routes/utils';
import { type FC, useEffect, useMemo, useRef } from 'react';
import { FormProvider, useForm, useWatch } from 'react-hook-form';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';

/**
 * Form schema that uses the generated spec schema from the platform zod,
 * extended with UI-only validation fields (dataset file checks).
 * Keeps field paths flat (e.g., 'model', 'training.epochs')
 * so child components don't need a 'spec.' prefix.
 */
const specSchema = CustomizationCreateJobBody.shape.spec;

const baseFormSchema = specSchema.extend({
  model: z.string().min(1, 'Please select a model'),
  description: z.string().optional(),
  dataset: z.custom<Fileset | undefined>((val) => val !== undefined && val !== null, {
    message: 'Please select a dataset',
  }),
  trainingFileExists: z.boolean().refine((val) => val === true, {
    message: 'No Training Data Found',
  }),
  // Validation files are optional: Customizer auto-splits 10% from training when missing.
  // The boolean is still tracked so the UI can render an info banner, but it never blocks submit.
  validationFileExists: z.boolean(),
});

export type CustomizationFormFields = z.infer<typeof baseFormSchema>;

const formSchema = baseFormSchema.refine(refineModelName, refineModelNameConfig);

const HIDDEN_ERROR_FIELDS = new Set(['trainingFileExists', 'validationFileExists']);

export const NewCustomizationForm: FC = () => {
  const errorBannerRef = useRef<HTMLDivElement>(null);
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  useBreadcrumbs({
    items: [
      {
        href: getCustomizationJobListRoute(workspace),
        slotLabel: 'Custom Models',
      },
      {
        slotLabel: 'New Model',
      },
    ],
  });

  const {
    mutate: createCustomization,
    isPending,
    isError,
    error,
    reset: resetMutation,
  } = useCustomizationCreateJob({
    mutation: {
      onSuccess: (customization: CustomizationJobOutput) => {
        navigate(getWorkspaceCustomizationJobDetailsRoute(workspace, customization.name));
      },
    },
  });

  const { data: modelsPage, isFetching: isFetchingModels } = useModelsListModels(
    workspace,
    { page_size: DEFAULT_LARGE_PAGE_SIZE },
    { query: {} }
  );
  const models = modelsPage?.data?.filter(isDefined);

  const form = useForm<CustomizationFormFields>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      model: searchParams.get('model') ?? '',
      output: { name: generateDefaultName() },
      training: NEW_CUSTOMIZATION_FORM_HYP_DEFAULT_VALUES,
      trainingFileExists: false,
      validationFileExists: false,
    },
    mode: 'onChange',
    disabled: isPending,
  });
  const {
    setValue,
    handleSubmit,
    control,
    formState: { errors, submitCount },
  } = form;
  const selectedFileset = useWatch({ control, name: 'dataset' });
  const trainingType = useWatch({ control, name: 'training.type' });

  const { isSuccess: isFilesetSuccess } = useFilesRetrieveFileset(
    selectedFileset?.workspace ?? '',
    selectedFileset?.name ?? '',
    { query: { enabled: !!(selectedFileset?.workspace && selectedFileset?.name) } }
  );

  const { training, validation } = useCustomizationFilesPreview({
    fileset: getURNFromNamedEntityRef(selectedFileset),
  });

  const validationErrors = useMemo(() => {
    if (submitCount === 0) return [];
    return Object.entries(errors)
      .filter(([key]) => !HIDDEN_ERROR_FIELDS.has(key))
      .map(([, value]) =>
        value &&
        typeof value === 'object' &&
        'message' in value &&
        typeof value.message === 'string'
          ? value.message
          : undefined
      )
      .filter((msg): msg is string => msg !== undefined);
  }, [errors, submitCount]);

  useEffect(() => {
    if (isFilesetSuccess) {
      setValue('trainingFileExists', training.hasFiles, { shouldValidate: true });
      setValue('validationFileExists', validation.hasFiles, { shouldValidate: true });
    }
  }, [training.hasFiles, validation.hasFiles, isFilesetSuccess, setValue]);

  useEffect(() => {
    if (isError || validationErrors.length > 0) {
      errorBannerRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [isError, validationErrors]);

  const handleSetFileset = (fileset: Fileset) => {
    setValue('dataset', fileset, { shouldValidate: true });
  };

  const trainCustomModel = (data: CustomizationFormFields) => {
    resetMutation();
    const {
      trainingFileExists: _trainingFileExists,
      validationFileExists: _validationFileExists,
      dataset,
      output,
      description,
      ...spec
    } = data;
    void _trainingFileExists;
    void _validationFileExists;
    const datasetUri = dataset ? `fileset://${dataset.workspace}/${dataset.name}` : '';
    createCustomization({
      workspace,
      data: {
        name: output?.name,
        description,
        spec: { ...spec, dataset: datasetUri, output },
      },
    });
  };

  return (
    <Stack className="h-full" gap="density-2xl" padding="density-2xl">
      <PageHeader
        slotHeading="Fine-tune a Model"
        slotDescription="Select a model, choose your data, set your parameters and start training in seconds."
      />
      <FormProvider {...form}>
        <form
          className="w-full"
          aria-label="Fine-tune a Model"
          onSubmit={handleSubmit(trainCustomModel)}
        >
          <Stack className="overflow-auto" gap="density-2xl" padding="density-2xl">
            <Flex align="center" justify="center" className="w-full">
              <Panel
                className="max-w-3xl h-full overflow-auto"
                elevation="high"
                density="standard"
                slotFooter={
                  <Flex className="w-full justify-end gap-2">
                    <Button type="submit" disabled={isPending} color="brand">
                      Start Fine-Tuning
                    </Button>
                  </Flex>
                }
              >
                <Stack gap="density-2xl">
                  <ModelSelectionSection models={models} isFetchingModels={isFetchingModels} />

                  <Divider />

                  <TrainingMethodSelect />

                  <Divider />

                  <CustomizationFilesetSelect
                    disabled={isPending}
                    onImportSubmit={handleSetFileset}
                  />

                  <Divider />

                  <GeneralParameters />

                  <Divider />

                  <ParameterEfficiency />

                  {trainingType === 'dpo' && (
                    <>
                      {' '}
                      <Divider />
                      <DpoParameters />
                    </>
                  )}

                  <Divider />

                  <ComputeResources />

                  {validationErrors.length > 0 && (
                    <Banner kind="inline" ref={errorBannerRef} status="error">
                      Please fix the following errors: {validationErrors.join(', ')}
                    </Banner>
                  )}
                  {isError && (
                    <Banner
                      kind="inline"
                      ref={errorBannerRef}
                      status="error"
                    >{`There was an error creating this fine-tuning job: ${getErrorMessage(error)}`}</Banner>
                  )}
                </Stack>
              </Panel>
            </Flex>
          </Stack>
        </form>
      </FormProvider>
    </Stack>
  );
};
