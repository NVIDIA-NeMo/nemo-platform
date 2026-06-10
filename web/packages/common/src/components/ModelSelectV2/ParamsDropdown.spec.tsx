// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ParamsDropdown } from '@nemo/common/src/components/ModelSelectV2/ParamsDropdown';
import { render, screen } from '@testing-library/react';

const renderOpen = (props: Partial<React.ComponentProps<typeof ParamsDropdown>> = {}) => {
  const onOpenChange = vi.fn();
  const onInferenceParamsChange = vi.fn();
  render(
    <ParamsDropdown
      open
      onOpenChange={onOpenChange}
      onInferenceParamsChange={onInferenceParamsChange}
      {...props}
    />
  );
  return { onOpenChange, onInferenceParamsChange };
};

describe('ParamsDropdown', () => {
  it('renders the trigger button', () => {
    render(<ParamsDropdown open={false} onOpenChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Model parameters' })).toBeInTheDocument();
  });

  describe('when open', () => {
    it('renders all inference parameter sliders', async () => {
      renderOpen();
      expect(await screen.findByText('Inference Params')).toBeInTheDocument();
      expect(screen.getByText('temperature')).toBeInTheDocument();
      expect(screen.getByText('top_p')).toBeInTheDocument();
      expect(screen.getByText('top_k')).toBeInTheDocument();
      expect(screen.getByText('max_tokens')).toBeInTheDocument();
    });

    it('uses playground defaults when inferenceParams are omitted', async () => {
      renderOpen();
      await screen.findByText('temperature');
      expect(screen.getByLabelText('temperature_text_input')).toHaveValue(0.7);
      expect(screen.getByLabelText('max_tokens_text_input')).toHaveValue(512);
    });

    it('displays inferenceParams initial values', async () => {
      renderOpen({ inferenceParams: { temperature: 0.5, max_tokens: 256, top_p: 0.8, top_k: 20 } });
      await screen.findByText('temperature');
      expect(screen.getByLabelText('temperature_text_input')).toHaveValue(0.5);
      expect(screen.getByLabelText('max_tokens_text_input')).toHaveValue(256);
      expect(screen.getByLabelText('top_p_text_input')).toHaveValue(0.8);
      expect(screen.getByLabelText('top_k_text_input')).toHaveValue(20);
    });

    it('disables all sliders when disabled', async () => {
      renderOpen({ disabled: true });
      await screen.findByText('temperature');
      screen.getAllByRole('slider').forEach((slider) => expect(slider).toBeDisabled());
    });

    it('renders reset buttons for each parameter', async () => {
      renderOpen();
      await screen.findByText('temperature');
      expect(
        screen.getByRole('button', { name: 'Reset temperature to default value' })
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Reset max_tokens to default value' })
      ).toBeInTheDocument();
    });
  });
});
