// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useChatCompletions } from '@nemo/common/src/hooks/useChatCompletions';
import { getEntityReference } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { isDefined } from '@nemo/common/src/utils/isDefined';
import { filesUploadFile } from '@nemo/sdk/generated/platform/api';
import type { FilesetFileOutput, ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { COMPLETION_PROMPT_KEY_ORDER } from '@studio/api/datasets/constants';
import { invalidateDatasetCaches } from '@studio/api/datasets/invalidateDatasetCaches';
import { TransformFileFormFields } from '@studio/components/FilesTable/TransformFileModal/types';
import { parseFileContent, Row } from '@studio/util/files';
import { useMutation, UseMutationOptions } from '@tanstack/react-query';
import Handlebars from 'handlebars';
import { ChatCompletion, ChatCompletionCreateParams } from 'openai/resources/index.mjs';
import { useCallback, useState } from 'react';

type MutationProps = {
  workspace: string;
  datasetName: string;
  filepath: TransformFileFormFields['filepath'];
  /** Destination for the transformed rows; the source file is left untouched. */
  outputFilepath: TransformFileFormFields['outputFilepath'];
  mappings: TransformFileFormFields['mappings'];
  fileContent: string;
  model?: ModelEntity;
};

type Props = Omit<UseMutationOptions<FilesetFileOutput, Error, MutationProps>, 'mutationFn'>;

export const useDatasetFileTransform = ({ onError, onSuccess }: Props) => {
  const toast = useToast();
  const { mutateAsync: createChatCompletions } = useChatCompletions();
  const [progressLabel, setProgressLabel] = useState<string>('');
  const [progressValue, setProgressValue] = useState<number>(0);
  const progPreInferValue = 20;
  const progPostInferValue = 90;

  const mutationFn = useCallback(
    async ({
      fileContent,
      filepath,
      outputFilepath,
      model,
      mappings,
      workspace,
      datasetName,
    }: MutationProps) => {
      setProgressValue(10);

      // Parse JSON objects
      const content = parseFileContent({
        content: fileContent,
        fileType: filepath.split('.').at(-1),
      });
      const { failures } = content;
      let { rows } = content;
      if (failures?.length) {
        toast.error(`${failures.length} Line(s) had parsing errors.`);
      }

      // Re-map each row to the described mappings
      if (mappings) {
        rows = rows
          .map((row, rowIndex) => {
            const newRow: Record<string, unknown> = {};
            let skipInvalidRow = false;
            mappings.forEach(({ key, value }) => {
              // Pre-process the row to stringify arrays and objects
              const processedRow = Object.fromEntries(
                Object.entries(row).map(([k, v]) => [
                  k,
                  Array.isArray(v) || (typeof v === 'object' && v !== null) ? JSON.stringify(v) : v,
                ])
              );

              const template = Handlebars.compile(value);
              // Handle nested keys (e.g. "user.profile.name")
              const keyParts = key.split('.');
              let current = newRow;

              // Process all parts except the last one
              for (let i = 0; i < keyParts.length - 1; i++) {
                const part = keyParts[i];
                if (!(part in current)) {
                  current[part] = {};
                }
                current = current[part] as Record<string, unknown>;
              }

              // Handle the last part of the key
              const lastPart = keyParts[keyParts.length - 1];
              const compiledValue = template(processedRow, { data: { row: rowIndex + 1 } });

              // Try to parse as JSON if it looks like an array or object
              try {
                if (compiledValue.trim().startsWith('[') || compiledValue.trim().startsWith('{')) {
                  current[lastPart] = JSON.parse(compiledValue);
                } else {
                  current[lastPart] = compiledValue;
                }
              } catch {
                skipInvalidRow = true;
              }
            });
            return skipInvalidRow ? undefined : newRow;
          })
          .filter(Boolean) as Row[];
      }
      setProgressValue(progPreInferValue);

      // Generate completions if necessary
      if (model) {
        const chatCompletionRequests = rows
          .map((row) => {
            let userMsg = '';
            for (const key of COMPLETION_PROMPT_KEY_ORDER) {
              if (key in row) {
                userMsg = row[key] as string;
                break;
              }
            }
            if (!userMsg) {
              return undefined;
            }
            const messages = [
              {
                role: 'user',
                content: userMsg,
              },
            ];
            if (model.prompt?.system_prompt) {
              messages.unshift({ role: 'system', content: model.prompt.system_prompt });
            }
            return {
              messages,
              model: getEntityReference(model),
            };
          })
          .filter(isDefined) as ChatCompletionCreateParams[];
        setProgressLabel(`Inferencing ${chatCompletionRequests.length} rows...`);
        const completions = (await createChatCompletions({
          requests: chatCompletionRequests,
          onTaskComplete: ({ completedTasks }) => {
            const ratioComplete = completedTasks / chatCompletionRequests.length;
            const inferProgress = ratioComplete * 70;
            setProgressLabel(`Inferencing... (${completedTasks}/${chatCompletionRequests.length})`);
            setProgressValue(progPreInferValue + inferProgress);
          },
        })) as ChatCompletion[];
        rows = completions.map((completion, index) => {
          return {
            input: { category: '', ...rows[index] },
            response: completion.choices[0].message.content,
            llm_name: model.name,
          };
        });
      }
      setProgressValue(progPostInferValue);

      // Upload file to fileset
      setProgressLabel('Uploading...');
      setProgressValue(95);
      const fileContent2 = rows.map((row) => JSON.stringify(row)).join('\n');
      const blob = new Blob([fileContent2], { type: 'application/json' });

      return filesUploadFile(workspace, datasetName, outputFilepath, blob);
    },
    [createChatCompletions, toast]
  );

  return {
    ...useMutation({
      mutationFn,
      onError: (data, variables, onMutateResult, context) => {
        onError?.(data, variables, onMutateResult, context);
      },
      onSuccess: (data, variables, onMutateResult, context) => {
        invalidateDatasetCaches(
          variables.workspace,
          variables.datasetName,
          ['files', 'content'],
          variables.outputFilepath
        );
        onSuccess?.(data, variables, onMutateResult, context);
      },
      onMutate: () => {
        setProgressLabel('');
      },
      onSettled: () => {
        setProgressLabel('');
      },
    }),
    progressLabel,
    progressValue,
  };
};
