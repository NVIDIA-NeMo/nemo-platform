/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { zodResolver } from '@hookform/resolvers/zod';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { handleFormErrorsGeneric } from '@nemo/common/src/utils/forms/error';
import { getListExperimentsQueryKey, useCreateExperiment } from '@nemo/sdk/generated/platform/api';
import { FormField, Stack, TextArea, TextInput } from '@nvidia/foundations-react-core';
import { queryClient } from '@studio/api/queryClient';
import { DefaultSortControl } from '@studio/components/DefaultSortControl';
import { DEFAULT_SORT } from '@studio/components/DefaultSortControl/util';
import {
  experimentCreateSchema,
  type ExperimentCreateFormFields,
} from '@studio/components/ExperimentCreateModal/constants';
import { ExperimentFlagSwitch } from '@studio/components/ExperimentFlagSwitch';
import { AxiosError } from 'axios';
import { useState, type FC } from 'react';
import { Controller, useForm, type SubmitHandler } from 'react-hook-form';

export interface ExperimentCreateModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
}

export const ExperimentCreateModal: FC<ExperimentCreateModalProps> = ({
  open,
  onClose,
  workspace,
}) => {
  const {
    reset,
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setValue,
    setError,
    control,
  } = useForm<ExperimentCreateFormFields>({
    resolver: zodResolver(experimentCreateSchema),
    mode: 'onChange',
    defaultValues: {
      is_favorite: false,
      show_evaluations_over_time: false,
    },
  });

  const formDisabled = isSubmitting;
  // Default sort is a single `sort`-param string driven by a custom control (not a registered input),
  // so it's managed outside react-hook-form and merged into the payload in onSubmit.
  const [defaultSort, setDefaultSort] = useState<string>(DEFAULT_SORT);

  const toast = useToast();

  const { mutateAsync: createExperiment } = useCreateExperiment({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey(workspace) });
      },
    },
  });

  const resetAndClose = () => {
    reset();
    setDefaultSort(DEFAULT_SORT);
    onClose();
  };

  const onSubmit: SubmitHandler<ExperimentCreateFormFields> = async (data) => {
    try {
      await createExperiment({
        workspace,
        data: {
          name: data.name,
          description: data.description,
          default_sort: defaultSort,
          is_favorite: data.is_favorite,
          show_evaluations_over_time: data.show_evaluations_over_time,
        },
      });
      resetAndClose();
    } catch (error) {
      const errorDetail =
        error instanceof AxiosError && error.response?.data?.detail
          ? error.response.data.detail
          : undefined;

      if (
        error instanceof AxiosError &&
        error.response?.status === 409 &&
        typeof errorDetail === 'string'
      ) {
        setError('name', { message: errorDetail });
      } else {
        let errorMessage: string;
        if (Array.isArray(errorDetail) && errorDetail.length > 0 && errorDetail[0].msg) {
          errorMessage = errorDetail[0].msg;
        } else if (errorDetail && typeof errorDetail === 'string') {
          errorMessage = errorDetail;
        } else if (error instanceof Error) {
          errorMessage = error.message;
        } else {
          errorMessage = 'Unknown error';
        }

        toast.error(`Failed to create experiment: ${errorMessage}`);
      }
    }
  };

  return (
    <FormModal
      title="Create experiment"
      instruction="Group evaluations to allow easy comparison of top level and test cases"
      submitButtonText="Create"
      disabled={formDisabled}
      loading={isSubmitting}
      onSubmit={handleSubmit(
        onSubmit,
        handleFormErrorsGeneric({ title: 'Experiment Create Form Errors' })
      )}
      onClose={resetAndClose}
      open={open}
      className="w-[800px] min-h-[400px]"
    >
      <Stack gap="density-2xl" className="w-full min-w-0">
        <FormField slotLabel="Name" slotError={errors.name?.message} status={errors.name && 'error'}>
          <TextInput
            autoFocus
            disabled={formDisabled}
            status={errors.name && 'error'}
            {...register('name')}
            onChange={(e) =>
              setValue('name', (e.target as HTMLInputElement).value.replace(/[\s-]+/g, '-'), {
                shouldValidate: true,
              })
            }
          />
        </FormField>

        <FormField
          slotLabel="Description (optional)"
          slotError={errors.description?.message}
          status={errors.description && 'error'}
        >
          <TextArea
            disabled={formDisabled}
            status={errors.description && 'error'}
            {...register('description')}
          />
        </FormField>

        <DefaultSortControl value={defaultSort} onChange={setDefaultSort} disabled={formDisabled} />

        {(['show_evaluations_over_time', 'is_favorite'] as const).map((flag) => (
          <Controller
            key={flag}
            name={flag}
            control={control}
            render={({ field }) => (
              <ExperimentFlagSwitch
                flag={flag}
                checked={Boolean(field.value)}
                onCheckedChange={field.onChange}
                onBlur={field.onBlur}
                disabled={formDisabled}
              />
            )}
          />
        ))}
      </Stack>
    </FormModal>
  );
};
