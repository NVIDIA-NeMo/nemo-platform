// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// vi.mock calls below are hoisted by vitest, so this import still resolves the mocks.
import { NewCustomizationForm } from '@studio/components/NewCustomizationForm';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import {
  CustomizationDatasetValidationResult,
  useCustomizationDatasetValidation,
} from '@studio/hooks/useCustomizationDatasetValidation';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const mutateAutomodel = vi.fn();
const mutateUnsloth = vi.fn();

vi.mock('@nemo/sdk/vendored/customizer/api', () => ({
  useCustomizationCreateAutomodelJob: () => ({ mutateAsync: mutateAutomodel, isPending: false }),
  useCustomizationCreateUnslothJob: () => ({ mutateAsync: mutateUnsloth, isPending: false }),
}));

vi.mock('@studio/hooks/useCustomizationDatasetValidation', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@studio/hooks/useCustomizationDatasetValidation')>();
  return { ...actual, useCustomizationDatasetValidation: vi.fn() };
});

const emptyValidation: CustomizationDatasetValidationResult = {
  isPending: false,
  discoveryError: null,
  format: { ok: true, fileErrors: [] },
  schema: null,
  schemaExpectedCopy: '',
  schemaMismatchedFiles: [],
  schemaShape: '',
  completeness: { ok: true, skipped: false, errors: [] },
  encoding: { ok: true, fileErrors: [] },
  hasTraining: false,
  hasValidation: false,
  autoSplitNotice: false,
  training: [],
  validation: [],
  trainingRowCount: 0,
  validationRowCount: 0,
};

describe('NewCustomizationForm', () => {
  beforeEach(() => {
    mutateAutomodel.mockReset();
    mutateUnsloth.mockReset();
    mockUseParams({ [ROUTE_PARAMS.workspace]: 'default' });
    vi.mocked(useCustomizationDatasetValidation).mockReturnValue(emptyValidation);
  });

  it('defaults to the automodel backend and shows its compute controls', async () => {
    renderRoute(<NewCustomizationForm workspace="default" />);
    // Automodel exposes multi-GPU parallelism ("GPUs per Node"), not raw indices.
    expect(await screen.findByText('GPUs per Node')).toBeInTheDocument();
    expect(screen.queryByText('GPU Indices')).not.toBeInTheDocument();
  });

  it('swaps to unsloth-specific controls when the unsloth backend is selected', async () => {
    const user = userEvent.setup();
    renderRoute(<NewCustomizationForm workspace="default" />);

    await user.click(await screen.findByRole('radio', { name: /Unsloth/i }));

    // Unsloth exposes single-node GPU indices; automodel parallelism disappears.
    expect(await screen.findByText('GPU Indices')).toBeInTheDocument();
    expect(screen.queryByText('GPUs per Node')).not.toBeInTheDocument();
  });

  it('shows the validation banner and does not submit when required fields are missing', async () => {
    const user = userEvent.setup();
    renderRoute(<NewCustomizationForm workspace="default" />);

    await user.click(await screen.findByRole('button', { name: /Start Fine-Tuning/i }));

    expect(await screen.findByText(/Please fix the following errors/i)).toBeInTheDocument();
    expect(mutateAutomodel).not.toHaveBeenCalled();
    expect(mutateUnsloth).not.toHaveBeenCalled();
  });

  it('does not block submit on the inactive backend (only the active one is validated)', async () => {
    // Regression guard: switching to unsloth must not surface stale automodel errors.
    const user = userEvent.setup();
    renderRoute(<NewCustomizationForm workspace="default" />);

    await user.click(await screen.findByRole('radio', { name: /Unsloth/i }));
    await user.click(await screen.findByRole('button', { name: /Start Fine-Tuning/i }));

    // The errors shown must be about the unsloth fields, never automodel ones.
    const banner = await screen.findByText(/Please fix the following errors/i);
    expect(banner.textContent).not.toMatch(/automodel/i);
    await waitFor(() => expect(mutateAutomodel).not.toHaveBeenCalled());
  });
});
