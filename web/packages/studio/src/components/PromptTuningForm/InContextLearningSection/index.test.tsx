// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { AccordionRoot } from '@nvidia/foundations-react-core';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { mockFileJson } from '@studio/mocks/studio-ui/files';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { render } from '@studio/tests/util/render';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { InContextLearningSection } from '.';

describe('InContextLearningSection', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    mockUseParams({
      [ROUTE_PARAMS.workspace]: DEFAULT_WORKSPACE,
    });
  });

  it('renders import button when editable', () => {
    render(
      <FormWrapper>
        <AccordionRoot defaultValue="learning-examples">
          <InContextLearningSection isEditable />
        </AccordionRoot>
      </FormWrapper>
    );

    expect(screen.getByRole('button', { name: /import examples/i })).toBeInTheDocument();
  });

  it('does not render import and upload buttons when not editable', () => {
    render(
      <FormWrapper>
        <AccordionRoot defaultValue="learning-examples">
          <InContextLearningSection isEditable={false} />
        </AccordionRoot>
      </FormWrapper>
    );

    expect(screen.queryByRole('button', { name: /import examples/i })).not.toBeInTheDocument();
  });

  describe('Preview Button', () => {
    it('opens preview panel when preview button is clicked', async () => {
      render(
        <FormWrapper>
          <AccordionRoot defaultValue="learning-examples">
            <InContextLearningSection isEditable />
          </AccordionRoot>
        </FormWrapper>
      );
      const importButton = screen.getByRole('button', { name: /import examples/i });
      await user.click(importButton);

      await user.click(screen.getByRole('tab', { name: 'Upload a File' }));
      await user.upload(screen.getByTestId('nv-upload-input-element'), mockFileJson);

      const saveButton = screen.getByRole('button', { name: 'Confirm' });
      await user.click(saveButton);

      const previewButton = await screen.findByRole('button', { name: /Preview file/i });
      await user.click(previewButton);

      // Preview panel should open with the file name in the heading
      expect(screen.getByRole('dialog', { name: mockFileJson.name })).toBeInTheDocument();
    });
  });

  describe('Import Button', () => {
    it('opens import modal when import button is clicked', async () => {
      render(
        <FormWrapper>
          <AccordionRoot defaultValue="learning-examples">
            <InContextLearningSection isEditable />
          </AccordionRoot>
        </FormWrapper>
      );

      const importButton = screen.getByRole('button', { name: /import examples/i });
      await user.click(importButton);

      expect(screen.getByRole('dialog', { name: 'Add Learning Examples' })).toBeInTheDocument();
    });

    it('closes import modal when close is clicked', async () => {
      render(
        <FormWrapper>
          <AccordionRoot defaultValue="learning-examples">
            <InContextLearningSection isEditable />
          </AccordionRoot>
        </FormWrapper>
      );

      const importButton = screen.getByRole('button', { name: /import examples/i });
      await user.click(importButton);

      const closeButton = screen.getByRole('button', { name: 'Cancel' });
      await user.click(closeButton);
      await waitFor(() =>
        expect(
          screen.queryByRole('dialog', { name: 'Add Learning Examples' })
        ).not.toBeInTheDocument()
      );
    });

    it('Adds file to list when import modal saves content', async () => {
      render(
        <FormWrapper>
          <AccordionRoot defaultValue="learning-examples">
            <InContextLearningSection isEditable />
          </AccordionRoot>
        </FormWrapper>
      );

      const importButton = screen.getByRole('button', { name: /import examples/i });
      expect(importButton).toBeEnabled();
      await user.click(importButton);

      await user.click(screen.getByRole('tab', { name: 'Upload a File' }));
      await user.upload(screen.getByTestId('nv-upload-input-element'), mockFileJson);

      const saveButton = screen.getByRole('button', { name: 'Confirm' });
      expect(saveButton).toBeEnabled();
      await user.click(saveButton);

      // File should be visible in the list
      expect(await screen.findByText(mockFileJson.name)).toBeInTheDocument();
      // Preview and delete buttons should be available
      expect(screen.getByRole('button', { name: /Preview file/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Delete file/i })).toBeInTheDocument();
    });
  });
});
