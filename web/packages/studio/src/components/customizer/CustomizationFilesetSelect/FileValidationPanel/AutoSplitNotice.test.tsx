// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AutoSplitNotice } from '@studio/components/customizer/CustomizationFilesetSelect/FileValidationPanel/AutoSplitNotice';
import { render, screen } from '@testing-library/react';

describe('AutoSplitNotice', () => {
  it('omits the row-count breakdown when training is empty', () => {
    render(<AutoSplitNotice trainingRowCount={0} />);
    expect(screen.queryByText(/examples will be used for training/)).not.toBeInTheDocument();
    expect(screen.queryByText(/examples will be used for validation/)).not.toBeInTheDocument();
  });

  it('renders 90% / 10% split with comma-formatted counts', () => {
    // 1000 -> validation = round(1000 * 0.1) = 100, training = 900
    render(<AutoSplitNotice trainingRowCount={1000} />);
    expect(screen.getByText('90% (900) examples will be used for training.')).toBeInTheDocument();
    expect(screen.getByText('10% (100) examples will be used for validation.')).toBeInTheDocument();
  });

  it('formats large counts with thousands separators', () => {
    // 12000 chosen for unambiguous rounding (12000 * 0.1 = 1200 exactly).
    // Both numbers are large enough to exercise the comma separator.
    render(<AutoSplitNotice trainingRowCount={12000} />);
    expect(
      screen.getByText('90% (10,800) examples will be used for training.')
    ).toBeInTheDocument();
    expect(
      screen.getByText('10% (1,200) examples will be used for validation.')
    ).toBeInTheDocument();
  });

  it('rounds the validation count to the nearest integer', () => {
    // 7 -> validation = round(0.7) = 1 ; training = 6
    render(<AutoSplitNotice trainingRowCount={7} />);
    expect(screen.getByText('90% (6) examples will be used for training.')).toBeInTheDocument();
    expect(screen.getByText('10% (1) examples will be used for validation.')).toBeInTheDocument();
  });
});
