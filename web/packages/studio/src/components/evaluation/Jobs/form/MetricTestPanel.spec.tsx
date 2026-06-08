// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { MetricEvaluationResponse } from '@nemo/sdk/generated/platform/schema';
import { MetricTestPanel } from '@studio/components/evaluation/Jobs/form/MetricTestPanel';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { renderRoute } from '@studio/tests/util/render';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormProvider, useForm } from 'react-hook-form';

const { mockEvaluateMetric, mockUseDatasetFileContent } = vi.hoisted(() => ({
  mockEvaluateMetric: vi.fn(),
  mockUseDatasetFileContent: vi.fn(),
}));

vi.mock('@nemo/common/src/components/CodeEditor', () => ({
  CodeEditor: ({
    content,
    onChange,
  }: {
    content: string;
    onChange?: (newContent: string) => void;
  }) => (
    <textarea
      aria-label="Test Dataset"
      value={content}
      onChange={(event) => onChange?.(event.target.value)}
      readOnly={!onChange}
    />
  ),
}));

vi.mock('@studio/api/datasets/useDatasetFileContent', () => ({
  useDatasetFileContent: mockUseDatasetFileContent,
}));

vi.mock('@nemo/common/src/components/UploadModal', () => ({
  UploadModal: ({
    open,
    onSubmit,
    onClose,
  }: {
    open: boolean;
    onSubmit: (selection: {
      type: 'dataset';
      dataset: { workspace: string; name: string };
      path: string;
      url: string;
    }) => void;
    onClose: () => void;
  }) =>
    open ? (
      <button
        type="button"
        onClick={() => {
          onSubmit({
            type: 'dataset',
            dataset: { workspace: 'default', name: 'fileset-1' },
            path: 'file-1.jsonl',
            url: 'fileset://default/fileset-1/file-1.jsonl',
          });
          onClose();
        }}
      >
        Select Mock File
      </button>
    ) : null,
}));

vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>();
  return {
    ...original,
    useEvaluationEvaluateMetric: vi.fn(() => ({
      mutateAsync: mockEvaluateMetric,
      isPending: false,
    })),
  };
});

const MOCK_RESPONSE: MetricEvaluationResponse = {
  metric: {
    type: 'llm-judge',
    model: { url: '', name: 'nvidia/llama3-70b' },
    scores: [{ name: 'quality', minimum: 0, maximum: 5 }],
  },
  aggregate_scores: [
    {
      name: 'quality',
      count: 2,
      nan_count: 0,
      mean: 3.5,
      min: 3,
      max: 4,
      score_type: 'range',
    },
  ],
  row_scores: [
    {
      index: 0,
      row: { input: 'hello', output: 'hi' },
      scores: { quality: 4 },
    },
  ],
};

function renderWithForm(modelName = '', scoresEmpty = false, inference?: Record<string, unknown>) {
  const Wrapper = () => {
    const methods = useForm({
      defaultValues: {
        name: 'test-metric',
        body: {
          type: 'llm-judge',
          model: { name: modelName, url: '', format: 'nim' },
          scores: scoresEmpty
            ? []
            : [
                {
                  scoreType: 'range',
                  name: 'quality',
                  minimum: 0,
                  maximum: 5,
                },
              ],
          messages: [{ role: 'user', content: 'Rate this.', expanded: true }],
          inference,
        },
      },
    });
    return (
      <FormProvider {...methods}>
        <MetricTestPanel />
      </FormProvider>
    );
  };

  return renderRoute(<Wrapper />);
}

describe('MetricTestPanel', () => {
  beforeEach(() => {
    mockUseParams({ [ROUTE_PARAMS.workspace]: workspace1.name });
    mockEvaluateMetric.mockReset();
    mockUseDatasetFileContent.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });
  });

  describe('Warning banner', () => {
    it('shows warning when judge model is missing', async () => {
      renderWithForm('', false);

      expect(
        await screen.findByText(/please configure the following options/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/judge model/i)).toBeInTheDocument();
    });

    it('shows warning when scores are missing', async () => {
      renderWithForm('some-model', true);

      expect(
        await screen.findByText(/please configure the following options/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/score definitions/i)).toBeInTheDocument();
    });

    it('hides warning when model and scores are configured', async () => {
      renderWithForm('some-model', false);

      await screen.findByText('Run Test');
      expect(screen.queryByText(/please configure the following options/i)).not.toBeInTheDocument();
    });
  });

  describe('Run Test button', () => {
    it('is disabled when model is missing', async () => {
      renderWithForm('', false);

      await screen.findByRole('button', { name: /run test/i });
      expect(screen.getByRole('button', { name: /run test/i })).toBeDisabled();
    });

    it('calls evaluateMetric and shows results on success', async () => {
      const user = userEvent.setup();
      mockEvaluateMetric.mockResolvedValue(MOCK_RESPONSE);

      renderWithForm('nvidia/llama3-70b', false);

      await screen.findByRole('button', { name: /run test/i });
      await user.click(screen.getByRole('button', { name: /run test/i }));

      await waitFor(() => {
        expect(mockEvaluateMetric).toHaveBeenCalledOnce();
      });

      expect(await screen.findByText(/aggregate scores/i)).toBeInTheDocument();
    });

    it('sends the prompt template as chat messages', async () => {
      const user = userEvent.setup();
      mockEvaluateMetric.mockResolvedValue(MOCK_RESPONSE);

      renderWithForm('nvidia/llama3-70b', false);

      await screen.findByRole('button', { name: /run test/i });
      await user.click(screen.getByRole('button', { name: /run test/i }));

      await waitFor(() => {
        expect(mockEvaluateMetric).toHaveBeenCalledWith(
          expect.objectContaining({
            data: expect.objectContaining({
              metric: expect.objectContaining({
                prompt_template: {
                  messages: [{ role: 'user', content: 'Rate this.' }],
                },
              }),
            }),
          })
        );
      });
    });

    it('forwards inference params to evaluateMetric when set', async () => {
      const user = userEvent.setup();
      mockEvaluateMetric.mockResolvedValue(MOCK_RESPONSE);

      renderWithForm('nvidia/llama3-70b', false, { temperature: 0.5, max_tokens: 512 });

      await screen.findByRole('button', { name: /run test/i });
      await user.click(screen.getByRole('button', { name: /run test/i }));

      await waitFor(() => {
        expect(mockEvaluateMetric).toHaveBeenCalledWith(
          expect.objectContaining({
            data: expect.objectContaining({
              metric: expect.objectContaining({
                inference: { temperature: 0.5, max_tokens: 512 },
              }),
            }),
          })
        );
      });
    });

    it('omits inference from evaluateMetric when inference params are empty', async () => {
      const user = userEvent.setup();
      mockEvaluateMetric.mockResolvedValue(MOCK_RESPONSE);

      renderWithForm('nvidia/llama3-70b', false, {});

      await screen.findByRole('button', { name: /run test/i });
      await user.click(screen.getByRole('button', { name: /run test/i }));

      await waitFor(() => {
        expect(mockEvaluateMetric).toHaveBeenCalledOnce();
      });

      expect(mockEvaluateMetric).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            metric: expect.not.objectContaining({ inference: expect.anything() }),
          }),
        })
      );
    });
  });

  describe('Test dataset editor', () => {
    it('renders the JSONL code editor', async () => {
      renderWithForm('some-model', false);

      expect(await screen.findByLabelText('Test Dataset')).toBeInTheDocument();
    });

    it('restores manual JSONL when switching back from file mode', async () => {
      const user = userEvent.setup();
      mockUseDatasetFileContent.mockReturnValue({
        data: '{"input":"file","output":"sample"}',
        isLoading: false,
        isError: false,
      });

      renderWithForm('some-model', false);

      const editor = await screen.findByLabelText('Test Dataset');
      await user.clear(editor);
      await user.click(editor);
      await user.paste('{"input":"custom"}');
      await user.click(screen.getAllByRole('combobox', { name: /select trigger/i })[0]);
      await user.click(await screen.findByRole('option', { name: /dataset file/i }));
      await user.click(await screen.findByRole('button', { name: /select mock file/i }));

      await waitFor(() => {
        expect(screen.getByLabelText('Test Dataset')).toHaveValue(
          '{"input":"file","output":"sample"}'
        );
      });

      await user.click(screen.getAllByRole('combobox', { name: /select trigger/i })[0]);
      await user.click(await screen.findByRole('option', { name: /^custom$/i }));

      expect(screen.getByLabelText('Test Dataset')).toHaveValue('{"input":"custom"}');
    });

    it('blocks running stale rows when selected file content fails to load', async () => {
      const user = userEvent.setup();
      mockUseDatasetFileContent.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      });

      renderWithForm('some-model', false);

      await user.click(screen.getAllByRole('combobox', { name: /select trigger/i })[0]);
      await user.click(await screen.findByRole('option', { name: /dataset file/i }));
      await user.click(await screen.findByRole('button', { name: /select mock file/i }));

      expect(
        await screen.findByText('Failed to load file content. Please select a different file.')
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /run test/i })).toBeDisabled();
    });
  });
});
