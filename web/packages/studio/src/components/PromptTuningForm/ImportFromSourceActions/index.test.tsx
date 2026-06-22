// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ImportFromSourceActions } from '@studio/components/PromptTuningForm/ImportFromSourceActions';
import { render } from '@studio/tests/util/render';
import { fireEvent, screen } from '@testing-library/react';

describe('ImportFromSourceActions', () => {
  const filename = 'filename';
  const onClickMock = vitest.fn();
  const onDismissMock = vitest.fn();
  const onStartEditingMock = vitest.fn();
  const onRevertMock = vitest.fn();
  beforeEach(() => {});
  afterEach(() => {
    onClickMock.mockReset();
    onDismissMock.mockReset();
    onStartEditingMock.mockReset();
    onRevertMock.mockReset();
  });

  it('should render normally', () => {
    render(
      <ImportFromSourceActions
        chipTitle={filename}
        onButtonClick={onClickMock}
        onDismiss={onDismissMock}
      />
    );
    expect(screen.getByText(`Copy of ${filename}`)).toBeInTheDocument();
    expect(screen.getByText('Import from Library')).toBeInTheDocument();
  });

  it('calls onButtonClick', () => {
    render(
      <ImportFromSourceActions
        chipTitle={filename}
        onButtonClick={onClickMock}
        onDismiss={onDismissMock}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Import from Library' }));
    expect(onClickMock).toHaveBeenCalledOnce();
  });

  it('import click disabled', () => {
    render(
      <ImportFromSourceActions
        chipTitle={filename}
        importButtonDisabled
        onButtonClick={onClickMock}
        onDismiss={onDismissMock}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Import from Library' }));
    expect(onClickMock).not.toHaveBeenCalledOnce();
  });

  it('calls onDismiss', () => {
    render(
      <ImportFromSourceActions
        chipTitle={filename}
        onButtonClick={onClickMock}
        onDismiss={onDismissMock}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: `Copy of ${filename}` }));
    expect(onDismissMock).toHaveBeenCalledOnce();
  });
});
