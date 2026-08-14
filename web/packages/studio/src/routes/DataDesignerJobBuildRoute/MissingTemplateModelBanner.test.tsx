// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MissingTemplateModelBanner } from '@studio/routes/DataDesignerJobBuildRoute/MissingTemplateModelBanner';
import type { BuilderModel } from '@studio/routes/DataDesignerJobBuildRoute/models';
import type {
  JobBuilderFormValues,
  TemplateModelIssue,
} from '@studio/routes/DataDesignerJobBuildRoute/useJobBuilder';
import { render, screen } from '@testing-library/react';
import type { FC, ReactNode } from 'react';
import { FormProvider, useForm } from 'react-hook-form';

const builderModel = (overrides: Partial<BuilderModel> = {}): BuilderModel => ({
  id: 'model-0',
  alias: 'default',
  model: 'nemotron-nano',
  provider: '',
  inferenceParams: {},
  ...overrides,
});

const ISSUE: TemplateModelIssue = { id: 'model-0', alias: 'default', requested: 'nemotron-nano' };

const renderWarning = (issues: TemplateModelIssue[], models: BuilderModel[] = [builderModel()]) => {
  const Wrapper: FC<{ children: ReactNode }> = ({ children }) => {
    const form = useForm<JobBuilderFormValues>({
      defaultValues: { name: 'ds', rows: '10', columns: [], models },
    });
    return <FormProvider {...form}>{children}</FormProvider>;
  };
  return render(<MissingTemplateModelBanner issues={issues} />, { wrapper: Wrapper });
};

describe('MissingTemplateModelBanner', () => {
  it('renders nothing without issues', () => {
    const { container } = renderWarning([]);
    expect(container).toBeEmptyDOMElement();
  });

  it('names the model the workspace is missing', () => {
    renderWarning([ISSUE]);

    expect(screen.getByText(/nemotron-nano/)).toBeInTheDocument();
    expect(screen.getByText(/Select an available model/)).toBeInTheDocument();
  });

  it('lists every missing model when more than one is unresolved', () => {
    renderWarning(
      [ISSUE, { id: 'model-1', alias: 'embedder', requested: 'nv-embed' }],
      [builderModel(), builderModel({ id: 'model-1', alias: 'embedder', model: 'nv-embed' })]
    );

    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('goes away once the model resolves to one the workspace serves', () => {
    const { container } = renderWarning(
      [ISSUE],
      [builderModel({ model: 'ws1/other', provider: 'ws1/build' })]
    );

    expect(container).toBeEmptyDOMElement();
  });
});
