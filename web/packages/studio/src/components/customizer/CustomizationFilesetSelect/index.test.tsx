// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { CustomizationFilesetSelect } from '@studio/components/customizer/CustomizationFilesetSelect';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import {
  CustomizationDatasetValidationResult,
  useCustomizationDatasetValidation,
} from '@studio/hooks/useCustomizationDatasetValidation';
import { datasets } from '@studio/mocks/datasets';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { FC, ReactNode } from 'react';
import { FormProvider, useForm } from 'react-hook-form';

vi.mock('@studio/hooks/useCustomizationDatasetValidation', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@studio/hooks/useCustomizationDatasetValidation')>();
  return { ...actual, useCustomizationDatasetValidation: vi.fn() };
});

const mockValidation = vi.mocked(useCustomizationDatasetValidation);

const buildValidation = (
  overrides: Partial<CustomizationDatasetValidationResult> = {}
): CustomizationDatasetValidationResult => ({
  isPending: false,
  discoveryError: null,
  format: { ok: true, fileErrors: [] },
  schema: { variant: 'sft-prompt-completion', label: 'SFT prompt/completion' },
  schemaExpectedCopy: 'Must contain messages (chat) or prompt and completion.',
  schemaMismatchedFiles: [],
  schemaShape: '',
  completeness: { ok: true, skipped: false, errors: [] },
  encoding: { ok: true, fileErrors: [] },
  hasTraining: true,
  hasValidation: true,
  autoSplitNotice: false,
  training: [],
  validation: [],
  trainingRowCount: 100,
  validationRowCount: 20,
  ...overrides,
});

/**
 * Wraps the picker in a real react-hook-form context so the component's
 * internal `useFormContext` + `useWatch` calls behave exactly like in the
 * production form. We don't need any specific defaults beyond `dataset`
 * being undefined (i.e., no fileset picked yet).
 */
const FormContext: FC<{
  children: ReactNode;
  dataset?: { workspace: string; name: string };
}> = ({ children, dataset }) => {
  const methods = useForm({
    defaultValues: {
      dataset,
      training: { type: 'sft' as const },
    },
  });
  return <FormProvider {...methods}>{children}</FormProvider>;
};

describe('CustomizationFilesetSelect', () => {
  beforeEach(() => {
    // Picker reads the workspace from URL params; the existing filesets msw
    // handler returns datasets for any workspace, so the param value just
    // needs to be present.
    mockUseParams({ [ROUTE_PARAMS.workspace]: 'default' });
    mockValidation.mockReturnValue(buildValidation());
  });

  it('fires onImportSubmit with the picked FilesetOutput when an existing dataset is selected', async () => {
    const user = userEvent.setup();
    const onImportSubmit = vi.fn();

    renderRoute(
      <FormContext>
        <CustomizationFilesetSelect onImportSubmit={onImportSubmit} />
      </FormContext>
    );

    // Wait for the filesets list to populate the dropdown items.
    const trigger = await screen.findByRole('combobox', { name: /dataset/i });
    await user.click(trigger);

    const firstFileset = datasets.data[0] as FilesetOutput;
    const option = await screen.findByRole('option', { name: firstFileset.name ?? '' });
    await user.click(option);

    expect(onImportSubmit).toHaveBeenCalledTimes(1);
    expect(onImportSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ name: firstFileset.name, workspace: firstFileset.workspace })
    );
  });

  it('opens the create-fileset modal when the New Dataset option is selected and does NOT fire onImportSubmit', async () => {
    const user = userEvent.setup();
    const onImportSubmit = vi.fn();

    renderRoute(
      <FormContext>
        <CustomizationFilesetSelect onImportSubmit={onImportSubmit} />
      </FormContext>
    );

    const trigger = await screen.findByRole('combobox', { name: /dataset/i });
    await user.click(trigger);

    const newDatasetOption = await screen.findByRole('option', { name: 'New Dataset' });
    await user.click(newDatasetOption);

    // CustomizationFilesetCreateModal renders a "Create New Dataset" heading
    // when open — its presence in the DOM proves the create flow opened.
    expect(await screen.findByText('Create New Dataset')).toBeInTheDocument();
    expect(onImportSubmit).not.toHaveBeenCalled();
  });

  it('shows the no-training-files error on the Dataset field and swaps the patterns tooltip label when the selected dataset has no training files', async () => {
    mockValidation.mockReturnValue(buildValidation({ hasTraining: false }));

    const firstFileset = datasets.data[0] as FilesetOutput;
    renderRoute(
      <FormContext dataset={{ workspace: firstFileset.workspace, name: firstFileset.name ?? '' }}>
        <CustomizationFilesetSelect onImportSubmit={vi.fn()} />
      </FormContext>
    );

    expect(
      await screen.findByText(/No training files were found in this dataset/)
    ).toBeInTheDocument();
    // Default patterns-tooltip label is replaced with the "no files matching"
    // prompt; the standard label should not appear.
    expect(screen.getByText('Why are no files matching?')).toBeInTheDocument();
    expect(screen.queryByText('How are files matched within the Dataset?')).not.toBeInTheDocument();
  });
});
