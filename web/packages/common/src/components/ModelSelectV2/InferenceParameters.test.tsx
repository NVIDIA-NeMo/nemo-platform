// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { InferenceParameters } from '@nemo/common/src/components/ModelSelectV2/InferenceParameters';
import { fireEvent, render, screen } from '@testing-library/react';

const renderComponent = (props: Partial<React.ComponentProps<typeof InferenceParameters>> = {}) => {
  const onChange = vi.fn();
  render(<InferenceParameters value={{}} onChange={onChange} {...props} />);
  return { onChange };
};

describe('InferenceParameters', () => {
  it('renders temperature, max tokens, and top p fields', () => {
    renderComponent();
    expect(screen.getByText('Temperature')).toBeInTheDocument();
    expect(screen.getByText('Max Tokens')).toBeInTheDocument();
    expect(screen.getByText('Top P')).toBeInTheDocument();
  });

  it('uses 1024 as the default for max tokens', () => {
    renderComponent();
    const inputs = screen.getAllByRole('spinbutton');
    // inputs: [temperature, max_tokens, top_p]
    expect(inputs[1]).toHaveValue(1024);
  });

  it('displays provided initial values', () => {
    renderComponent({ value: { temperature: 0.5, max_tokens: 512, top_p: 0.8 } });
    const inputs = screen.getAllByRole('spinbutton');
    expect(inputs[0]).toHaveValue(0.5);
    expect(inputs[1]).toHaveValue(512);
    expect(inputs[2]).toHaveValue(0.8);
  });

  it('calls onChange with updated temperature and preserves other fields', () => {
    const { onChange } = renderComponent({ value: { max_tokens: 512, top_p: 0.9 } });
    const inputs = screen.getAllByRole('spinbutton');
    fireEvent.change(inputs[0], { target: { value: '0.7' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ temperature: 0.7, max_tokens: 512, top_p: 0.9 })
    );
  });

  it('calls onChange with updated max_tokens only (not max_completion_tokens)', () => {
    const { onChange } = renderComponent({ value: { temperature: 0.5 } });
    const inputs = screen.getAllByRole('spinbutton');
    fireEvent.change(inputs[1], { target: { value: '256' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ max_tokens: 256, temperature: 0.5 })
    );
    expect(onChange).not.toHaveBeenCalledWith(
      expect.objectContaining({ max_completion_tokens: expect.anything() })
    );
  });

  it('calls onChange with updated top_p and preserves other fields', () => {
    const { onChange } = renderComponent({ value: { temperature: 0.5, max_tokens: 256 } });
    const inputs = screen.getAllByRole('spinbutton');
    fireEvent.change(inputs[2], { target: { value: '0.9' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ top_p: 0.9, temperature: 0.5, max_tokens: 256 })
    );
  });

  it('disables all inputs when disabled', () => {
    renderComponent({ disabled: true });
    const inputs = screen.getAllByRole('spinbutton');
    inputs.forEach((input) => expect(input).toBeDisabled());
  });
});
