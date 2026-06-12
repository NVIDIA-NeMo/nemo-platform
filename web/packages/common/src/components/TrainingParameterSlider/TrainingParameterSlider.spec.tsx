// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TrainingParameterSlider } from '@nemo/common/src/components/TrainingParameterSlider/index';
import { IrregularTrainingParameterSlider } from '@nemo/common/src/components/TrainingParameterSlider/IrregularTrainingParameterSlider';
import {
  CustomizerHyperparameters,
  HYPERPARAMETER_FIELD_METADATA,
} from '@nemo/common/src/components/TrainingParameterSlider/types';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormProvider, useForm } from 'react-hook-form';

// Test wrapper component to provide React Hook Form context
const TestWrapper = ({
  children,
  defaultValues = {},
}: {
  children: React.ReactNode;
  defaultValues?: Partial<CustomizerHyperparameters>;
}) => {
  const methods = useForm<CustomizerHyperparameters>({
    defaultValues: {
      batch_size: 8,
      epochs: 1,
      learning_rate: 1e-4,
      hidden_dropout: 0.1,
      attention_dropout: 0.1,
      ffn_dropout: 0.1,
      weight_decay: 0.01,
      virtual_tokens: 50,
      adapter_dim: 32,
      adapter_dropout: 0.1,
      ...defaultValues,
    },
    mode: 'onChange',
  });

  return <FormProvider {...methods}>{children}</FormProvider>;
};

describe('TrainingParameterSlider', () => {
  describe('Accessibility and Roles', () => {
    it('should render with correct ARIA roles and accessibility attributes', () => {
      render(
        <TestWrapper>
          <TrainingParameterSlider name="batch_size" />
        </TestWrapper>
      );

      // Validate correct roles exist
      const slider = screen.getByRole('slider');
      const textInput = screen.getByRole('spinbutton');

      // Validate ARIA attributes
      expect(slider).toHaveAttribute('aria-label', 'Controlled slider');
      expect(slider).toHaveAttribute('min', '8');
      expect(slider).toHaveAttribute('max', '128');
      expect(slider).toHaveValue('8');

      expect(textInput).toHaveAttribute('aria-label', 'batch_size-slider_text_input');

      // Verify only one of each role exists in this isolated test
      expect(screen.getAllByRole('slider')).toHaveLength(1);
      expect(screen.getAllByRole('spinbutton')).toHaveLength(1);
    });
  });

  describe('Basic Functionality', () => {
    it('should render and configure slider correctly with metadata', () => {
      render(
        <TestWrapper>
          <TrainingParameterSlider name="batch_size" />
        </TestWrapper>
      );

      const metadata = HYPERPARAMETER_FIELD_METADATA.batch_size;
      const slider = screen.getByRole('slider');
      const textInput = screen.getByRole('spinbutton');

      // Verify elements render with correct attributes
      expect(screen.getByText(metadata.name)).toBeInTheDocument();
      expect(screen.getByText(metadata.description!)).toBeInTheDocument();
      expect(slider).toHaveAttribute('min', metadata.min.toString());
      expect(slider).toHaveAttribute('max', metadata.max.toString());
      expect(textInput).toHaveValue(8);
      expect(textInput).toHaveAttribute('aria-label', 'batch_size-slider_text_input');
    });

    it('should render helper text and respect disabled state', () => {
      render(
        <TestWrapper>
          <TrainingParameterSlider name="learning_rate" disabled />
        </TestWrapper>
      );

      const slider = screen.getByRole('slider');
      const textInput = screen.getByRole('spinbutton');

      // Verify helper text and disabled state
      expect(
        screen.getByText(
          'How much to adjust the model parameters in response to the loss gradient.'
        )
      ).toBeInTheDocument();
      expect(slider).toBeDisabled();
      expect(textInput).toBeDisabled();
    });
  });

  describe('Value Changes', () => {
    it('should update value when text input changes and integrate with form', () => {
      render(
        <TestWrapper defaultValues={{ epochs: 5 }}>
          <TrainingParameterSlider name="epochs" />
        </TestWrapper>
      );

      const textInput = screen.getByRole('spinbutton');

      // Verify initial form integration
      expect(textInput).toHaveValue(5);

      // Test text input change
      fireEvent.change(textInput, { target: { value: '15' } });
      expect(textInput).toHaveValue(15);
    });
  });

  describe('Validation', () => {
    it('should validate range constraints and show appropriate errors', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <TrainingParameterSlider name="epochs" />
        </TestWrapper>
      );

      const textInput = screen.getByRole('spinbutton');

      // Test too low
      await user.clear(textInput);

      expect(
        screen.getByText('Invalid value. Please enter a number between 1 and 100.')
      ).toBeInTheDocument();

      // Test too high
      await user.clear(textInput);

      expect(
        screen.getByText('Invalid value. Please enter a number between 1 and 100.')
      ).toBeInTheDocument();
    });

    it('should validate allowed values for adapter_dim with steps', async () => {
      render(
        <TestWrapper>
          <IrregularTrainingParameterSlider name="adapter_dim" />
        </TestWrapper>
      );

      // Verify marks are rendered
      expect(screen.getByText('8')).toBeInTheDocument();
      expect(screen.getByText('64')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should handle custom error text with validation precedence', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <TrainingParameterSlider name="epochs" errorText="Custom error message" />
        </TestWrapper>
      );

      const textInput = screen.getByRole('spinbutton');

      // Custom error should show initially
      expect(screen.getByText('Custom error message')).toBeInTheDocument();

      // Validation error should take precedence
      await user.clear(textInput);

      expect(
        screen.getByText('Invalid value. Please enter a number between 1 and 100.')
      ).toBeInTheDocument();
      expect(screen.queryByText('Custom error message')).not.toBeInTheDocument();
    });
  });

  describe('Individual Hyperparameter Fields', () => {
    const testCases = [
      { name: 'batch_size', expectedValue: 8, label: 'Batch Size' },
      { name: 'epochs', expectedValue: 1, label: 'Number of Epochs' },
      { name: 'learning_rate', expectedValue: 0.0001, label: 'Learning Rate' },
      { name: 'hidden_dropout', expectedValue: 0.1, label: 'Hidden Dropout' },
      { name: 'attention_dropout', expectedValue: 0.1, label: 'Attention Dropout' },
      { name: 'ffn_dropout', expectedValue: 0.1, label: 'FFN Dropout' },
      { name: 'weight_decay', expectedValue: 0.01, label: 'Weight Decay' },
      { name: 'virtual_tokens', expectedValue: 50, label: 'Number of Virtual Tokens' },
      { name: 'adapter_dim', expectedValue: 32, label: 'Adapter Dimensions' },
      { name: 'adapter_dropout', expectedValue: 0.1, label: 'Adapter Dropout' },
    ] as const;

    testCases.forEach(({ name, expectedValue }) => {
      it(`should render correctly for ${name}`, () => {
        render(
          <TestWrapper>
            <TrainingParameterSlider name={name} />
          </TestWrapper>
        );

        const metadata = HYPERPARAMETER_FIELD_METADATA[name];

        // Verify all required elements render with metadata
        expect(screen.getByText(metadata.name)).toBeInTheDocument();
        expect(screen.getByText(metadata.description!)).toBeInTheDocument();

        // Use specific selectors to avoid ambiguity
        const slider = screen.getByRole('slider');
        const textInput = screen.getByRole('spinbutton');

        expect(slider).toHaveAttribute('min', metadata.min.toString());
        expect(slider).toHaveAttribute('max', metadata.max.toString());
        expect(textInput).toHaveValue(expectedValue);
        expect(textInput).toHaveAttribute('aria-label', `${name}-slider_text_input`);
      });
    });
  });
});
