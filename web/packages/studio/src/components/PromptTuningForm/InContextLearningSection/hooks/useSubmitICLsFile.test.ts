// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { clearMockToasts, getMockToasts } from '@nemo/common/src/tests/toast';
import { suppressConsoleWarn } from '@nemo/testing/utils/suppress-console';
import { ImportFileContentFormFields } from '@studio/components/ImportFileContent/validation';
import { useSubmitICLsFile } from '@studio/components/PromptTuningForm/InContextLearningSection/hooks/useSubmitICLsFile';
import type { PromptTuningFormFields } from '@studio/routes/PromptTuningFormRoute/utils';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { act, renderHook } from '@testing-library/react';
import { useForm } from 'react-hook-form';

// Mock ICL examples (in-context learning examples are conversation examples in JSONL format)
const mockICLExample1 = { role: 'user', content: 'Hello' };
const mockICLExample2 = { role: 'assistant', content: 'Hi there!' };
const mockICLExample3 = { role: 'user', content: 'How are you?' };
const mockICLExample4 = { role: 'assistant', content: 'I am doing well, thanks!' };

describe('useSubmitICLsFile', () => {
  beforeEach(() => {
    clearMockToasts();
  });
  it('should return false and show error if a file with the same name already exists', async () => {
    const existingICL = {
      content: JSON.stringify(mockICLExample1) + '\n' + JSON.stringify(mockICLExample2),
      fileName: 'existing-examples.jsonl',
    };

    const { result } = renderHook(
      () => {
        const parentForm = useForm<PromptTuningFormFields>({
          defaultValues: {
            iclFewShotExamples: [existingICL],
            systemPromptTemplate: 'System prompt',
            systemPrompt: 'System prompt',
          },
        });
        const importFileForm = useForm<ImportFileContentFormFields>();
        const onSubmit = useSubmitICLsFile(parentForm, importFileForm);
        return { onSubmit, parentForm, importFileForm };
      },
      { wrapper: TestProviders }
    );

    // Create a file with the same name
    const fileContent = JSON.stringify(mockICLExample3) + '\n' + JSON.stringify(mockICLExample4);
    const file = new File([fileContent], 'existing-examples.jsonl', {
      type: 'application/json',
    });
    await act(async () => result.current.onSubmit({ file }));
    expect(getMockToasts()).toHaveLength(1);
    expect(getMockToasts()[0].message).toBe('File already exists');
  });

  it('should successfully add a new ICL file', async () => {
    const existingICL = {
      content: JSON.stringify(mockICLExample1) + '\n' + JSON.stringify(mockICLExample2),
      fileName: 'first-examples.jsonl',
    };

    const { result } = renderHook(
      () => {
        const parentForm = useForm<PromptTuningFormFields>({
          defaultValues: {
            iclFewShotExamples: [existingICL],
            systemPromptTemplate: 'System prompt {{iclFewShotExamples}}',
            systemPrompt: 'System prompt',
          },
        });
        const importFileForm = useForm<ImportFileContentFormFields>();
        const onSubmit = useSubmitICLsFile(parentForm, importFileForm);
        return { onSubmit, parentForm, importFileForm };
      },
      { wrapper: TestProviders }
    );

    // Create a new file with different examples
    const fileContent = JSON.stringify(mockICLExample3) + '\n' + JSON.stringify(mockICLExample4);
    const file = new File([fileContent], 'second-examples.jsonl', {
      type: 'application/json',
    });
    let success = false;
    await act(async () => {
      success = await result.current.onSubmit({ file });
    });

    expect(success).toBe(true);
    // Should have both ICL files
    const iclExamples = result.current.parentForm.getValues('iclFewShotExamples');
    expect(iclExamples).toHaveLength(2);
    expect(iclExamples?.[0].fileName).toBe('first-examples.jsonl');
    expect(iclExamples?.[1].fileName).toBe('second-examples.jsonl');
  });

  it('should update system prompt when adding ICL examples', async () => {
    const { result } = renderHook(
      () => {
        const parentForm = useForm<PromptTuningFormFields>({
          defaultValues: {
            iclFewShotExamples: [],
            systemPromptTemplate: 'Base prompt {{iclFewShotExamples}}',
            systemPrompt: 'Base prompt',
          },
        });
        const importFileForm = useForm<ImportFileContentFormFields>();
        const onSubmit = useSubmitICLsFile(parentForm, importFileForm);
        return { onSubmit, parentForm, importFileForm };
      },
      { wrapper: TestProviders }
    );

    const fileContent = JSON.stringify(mockICLExample1) + '\n' + JSON.stringify(mockICLExample2);
    const file = new File([fileContent], 'examples.jsonl', { type: 'application/json' });

    let success = false;
    await act(async () => {
      success = await result.current.onSubmit({ file });
    });
    expect(success).toBe(true);
    const systemPrompt = result.current.parentForm.getValues('systemPrompt');
    expect(systemPrompt).toContain('Base prompt');
    expect(systemPrompt).toContain(JSON.stringify(mockICLExample1));
  });

  describe('File validation', () => {
    beforeEach(() => {
      // parseFileContent logs a warning for each invalid JSON row — expected in validation tests
      suppressConsoleWarn('Invalid JSON row ignored');
    });

    it('should reject file with empty/invalid content (no valid JSON rows)', async () => {
      const { result } = renderHook(
        () => {
          const parentForm = useForm<PromptTuningFormFields>({
            defaultValues: {
              iclFewShotExamples: [],
              systemPromptTemplate: 'System prompt',
              systemPrompt: 'System prompt',
            },
          });
          const importFileForm = useForm<ImportFileContentFormFields>();
          const onSubmit = useSubmitICLsFile(parentForm, importFileForm);
          return { onSubmit, parentForm, importFileForm };
        },
        { wrapper: TestProviders }
      );

      // Create a file with plain text (invalid JSON)
      const fileContent = 'this is a random text file\nit does not contain structured data';
      const file = new File([fileContent], 'invalid.jsonl', { type: 'application/json' });

      let success = false;
      await act(async () => {
        success = await result.current.onSubmit({ file });
      });

      // Should return false and not add any examples
      expect(success).toBe(false);
      const iclExamples = result.current.parentForm.getValues('iclFewShotExamples');
      expect(iclExamples).toHaveLength(0);
    });

    it('should reject JSON file with invalid content', async () => {
      const { result } = renderHook(
        () => {
          const parentForm = useForm<PromptTuningFormFields>({
            defaultValues: {
              iclFewShotExamples: [],
              systemPromptTemplate: 'System prompt',
              systemPrompt: 'System prompt',
            },
          });
          const importFileForm = useForm<ImportFileContentFormFields>();
          const onSubmit = useSubmitICLsFile(parentForm, importFileForm);
          return { onSubmit, parentForm, importFileForm };
        },
        { wrapper: TestProviders }
      );

      // Create a JSON file with malformed content
      const fileContent = '{"invalid": "json", broken';
      const file = new File([fileContent], 'invalid.json', { type: 'application/json' });

      let success = false;
      await act(async () => {
        success = await result.current.onSubmit({ file });
      });

      // Should return false and not add any examples
      expect(success).toBe(false);
      const iclExamples = result.current.parentForm.getValues('iclFewShotExamples');
      expect(iclExamples).toHaveLength(0);
    });

    it('should reject JSONL file with all invalid lines', async () => {
      const { result } = renderHook(
        () => {
          const parentForm = useForm<PromptTuningFormFields>({
            defaultValues: {
              iclFewShotExamples: [],
              systemPromptTemplate: 'System prompt',
              systemPrompt: 'System prompt',
            },
          });
          const importFileForm = useForm<ImportFileContentFormFields>();
          const onSubmit = useSubmitICLsFile(parentForm, importFileForm);
          return { onSubmit, parentForm, importFileForm };
        },
        { wrapper: TestProviders }
      );

      // Create a JSONL file where all lines are invalid JSON
      const fileContent = 'not valid json line 1\nnot valid json line 2\n';
      const file = new File([fileContent], 'invalid.jsonl', { type: 'application/json' });

      let success = false;
      await act(async () => {
        success = await result.current.onSubmit({ file });
      });

      // Should return false and not add any examples
      expect(success).toBe(false);
      const iclExamples = result.current.parentForm.getValues('iclFewShotExamples');
      expect(iclExamples).toHaveLength(0);
    });

    it('should accept JSONL with some invalid lines but at least one valid line', async () => {
      const { result } = renderHook(
        () => {
          const parentForm = useForm<PromptTuningFormFields>({
            defaultValues: {
              iclFewShotExamples: [],
              systemPromptTemplate: 'System prompt',
              systemPrompt: 'System prompt',
            },
          });
          const importFileForm = useForm<ImportFileContentFormFields>();
          const onSubmit = useSubmitICLsFile(parentForm, importFileForm);
          return { onSubmit, parentForm, importFileForm };
        },
        { wrapper: TestProviders }
      );

      // Create a JSONL file with one valid line and one invalid line
      const fileContent = `${JSON.stringify(mockICLExample1)}\ninvalid json line\n`;
      const file = new File([fileContent], 'mixed.jsonl', { type: 'application/json' });

      let success = false;
      await act(async () => {
        success = await result.current.onSubmit({ file });
      });

      expect(success).toBe(true);
      const iclExamples = result.current.parentForm.getValues('iclFewShotExamples');
      expect(iclExamples).toHaveLength(1);
      expect(iclExamples?.[0].fileName).toBe('mixed.jsonl');
    });
  });
});
