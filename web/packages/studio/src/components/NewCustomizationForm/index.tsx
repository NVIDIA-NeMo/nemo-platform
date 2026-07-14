// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import {
  useCustomizationCreateAutomodelJob,
  useCustomizationCreateUnslothJob,
} from '@nemo/sdk/vendored/customizer/api';
import {
  Banner,
  Button,
  Divider,
  Flex,
  PageHeader,
  Panel,
  Stack,
} from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { CustomizationFilesetSelect } from '@studio/components/customizer/CustomizationFilesetSelect';
import { BackendSelectionSection } from '@studio/components/NewCustomizationForm/BackendSelectionSection';
import { ComputeResourcesSection } from '@studio/components/NewCustomizationForm/ComputeResourcesSection';
import { GeneralParametersSection } from '@studio/components/NewCustomizationForm/GeneralParametersSection';
import { LoraParametersSection } from '@studio/components/NewCustomizationForm/LoraParametersSection';
import { ModelSelectionSection } from '@studio/components/NewCustomizationForm/ModelSelectionSection';
import { TrainingMethodSection } from '@studio/components/NewCustomizationForm/TrainingMethodSection';
import { getWorkspaceCustomizationJobDetailsRoute } from '@studio/routes/utils';
import {
  FORM_DEFAULTS,
  customizationFormSchema,
  formToAutomodelCreate,
  formToUnslothCreate,
  type CustomizationFormFields,
} from '@studio/util/forms/customization';
import { FC, useEffect, useMemo, useRef, useState } from 'react';
import { type FieldErrors, FormProvider, type Resolver, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';

interface NewCustomizationFormProps {
  workspace: string;
  initialModel?: string;
}

export const NewCustomizationForm: FC<NewCustomizationFormProps> = ({
  workspace,
  initialModel,
}) => {
  const navigate = useNavigate();
  const toast = useToast();
  const errorBannerRef = useRef<HTMLDivElement>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  const defaultValues = useMemo<CustomizationFormFields>(
    () => ({
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      automodel: { ...FORM_DEFAULTS.automodel, model: initialModel ?? '' },
      unsloth: {
        ...FORM_DEFAULTS.unsloth,
        model: { ...FORM_DEFAULTS.unsloth.model, name: initialModel ?? '' },
      },
    }),
    [initialModel]
  );

  const form = useForm<CustomizationFormFields>({
    resolver: zodResolver(customizationFormSchema) as unknown as Resolver<CustomizationFormFields>,
    defaultValues,
    mode: 'onChange',
    shouldUnregister: false,
  });

  const backend = useWatch({ control: form.control, name: 'backend' });
  const automodelFinetuningType = useWatch({
    control: form.control,
    name: 'automodel.training.finetuning_type',
  });
  const unslothFinetuningType = useWatch({
    control: form.control,
    name: 'unsloth.training.finetuning_type',
  });
  const finetuningType = backend === 'automodel' ? automodelFinetuningType : unslothFinetuningType;
  const isLora = finetuningType === 'lora' || finetuningType === 'lora_merged';

  const { mutateAsync: createAutomodel, isPending: isPendingAutomodel } =
    useCustomizationCreateAutomodelJob({
      mutation: {
        onSuccess: (job) => {
          toast.success('Fine-tuning job started');
          navigate(getWorkspaceCustomizationJobDetailsRoute(workspace, job.name));
        },
        onError: (error: Error) => {
          toast.error(getErrorMessage(error, 'Failed to create fine-tuning job'));
        },
      },
    });

  const { mutateAsync: createUnsloth, isPending: isPendingUnsloth } =
    useCustomizationCreateUnslothJob({
      mutation: {
        onSuccess: (job) => {
          toast.success('Fine-tuning job started');
          navigate(getWorkspaceCustomizationJobDetailsRoute(workspace, job.name));
        },
        onError: (error: Error) => {
          toast.error(getErrorMessage(error, 'Failed to create fine-tuning job'));
        },
      },
    });

  const isPending = isPendingAutomodel || isPendingUnsloth;

  const onSubmit = async (fields: CustomizationFormFields) => {
    setValidationErrors([]);
    if (fields.backend === 'automodel') {
      await createAutomodel({ workspace, data: formToAutomodelCreate(fields) }).catch(
        () => undefined
      );
    } else {
      await createUnsloth({ workspace, data: formToUnslothCreate(fields) }).catch(() => undefined);
    }
  };

  const onInvalid = (formErrors: FieldErrors<CustomizationFormFields>) => {
    const messages: string[] = [];
    const collect = (node: unknown) => {
      if (!node || typeof node !== 'object') return;
      if ('message' in node && typeof (node as { message?: unknown }).message === 'string') {
        messages.push((node as { message: string }).message);
        return;
      }
      Object.values(node as Record<string, unknown>).forEach(collect);
    };
    collect(formErrors);
    setValidationErrors(
      messages.length ? Array.from(new Set(messages)) : ['Please complete the required fields.']
    );
  };

  useEffect(() => {
    if (validationErrors.length > 0) {
      errorBannerRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [validationErrors]);

  return (
    <AccessibleTitle title="Fine-tune a Model">
      <Stack className="h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          slotHeading="Fine-tune a Model"
          slotDescription="Select a model, choose your data, set your parameters and start training in seconds."
        />
        <FormProvider {...form}>
          <form
            className="w-full"
            aria-label="Fine-tune a Model"
            noValidate
            onSubmit={form.handleSubmit(onSubmit, onInvalid)}
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
                        {isPending ? 'Starting…' : 'Start Fine-Tuning'}
                      </Button>
                    </Flex>
                  }
                >
                  <Stack gap="density-2xl">
                    <BackendSelectionSection />
                    <Divider />
                    <ModelSelectionSection />
                    <Divider />
                    <TrainingMethodSection />
                    <Divider />
                    <CustomizationFilesetSelect disabled={isPending} />
                    <Divider />
                    <GeneralParametersSection />
                    {isLora && (
                      <>
                        <Divider />
                        <LoraParametersSection />
                      </>
                    )}
                    <Divider />
                    <ComputeResourcesSection />
                    {validationErrors.length > 0 && (
                      <Banner kind="inline" ref={errorBannerRef} status="error">
                        Please fix the following errors: {validationErrors.join(', ')}
                      </Banner>
                    )}
                  </Stack>
                </Panel>
              </Flex>
            </Stack>
          </form>
        </FormProvider>
      </Stack>
    </AccessibleTitle>
  );
};
