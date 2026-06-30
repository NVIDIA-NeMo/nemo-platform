// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { UploadModal } from '@nemo/common/src/components/UploadModal';
import { SubmitUploadType } from '@nemo/common/src/components/UploadModal/types';
import { InputFileSchemaType } from '@nemo/common/src/types';
import { extractUserFriendlyKeysFromRow } from '@nemo/common/src/utils/file';
import { validateFileFormat, detectFileStructure } from '@nemo/common/src/utils/fileValidation';
import {
  Banner,
  Button,
  Flex,
  FormField,
  Modal,
  Panel,
  Select,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { datasetFileContentQueryOptions } from '@studio/api/datasets/useDatasetFileContent';
import type {
  DatasetInputFileResult,
  DatasetKeyMapping,
} from '@studio/components/DatasetInputFile/types';
import { useDatasetInputFileReducer } from '@studio/components/DatasetInputFile/useDatasetInputFileReducer';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getDatasetDisplayNameFromFilesUrl } from '@studio/util/files';
import { logger } from '@studio/util/logger';
import { useQueryClient } from '@tanstack/react-query';
import { Plus, CircleCheck, CircleHelp, Eye, File as FileIcon, Trash2 } from 'lucide-react';
import { FC, useCallback, useEffect, useRef } from 'react';

export type { DatasetInputFileResult, DatasetKeyMapping } from './types';

interface DatasetInputFileProps {
  /** Called when file is selected and validated, or when key mapping changes */
  onChange: (result: DatasetInputFileResult | null) => void;
  /** Label for the file input. Defaults to "Input File" */
  label?: string;
  /** Whether the component is disabled */
  disabled?: boolean;
  /** Whether the prompt key is required. Defaults to true */
  requirePromptKey?: boolean;
  /** Whether the completion key is required. Defaults to true */
  requireCompletionKey?: boolean;
  /** Whether the ideal_response key is required. Defaults to false */
  requireIdealResponseKey?: boolean;
  /** Whether to show the trash/clear button next to the selected file. Defaults to true */
  showClearButton?: boolean;
  /** Whether to show the replace button next to the selected file. Defaults to false */
  showReplaceButton?: boolean;
  /** Whether to show the preview button that opens a modal with the file contents. Defaults to true */
  showPreviewButton?: boolean;
}

const SUCCESS_ICON = (
  <CircleCheck className="shrink-0" color="var(--text-color-feedback-success)" />
);
const HELP_ICON = <CircleHelp className="shrink-0" color="var(--text-color-subtle)" />;

export const DatasetInputFile: FC<DatasetInputFileProps> = ({
  onChange,
  label = 'Input File',
  disabled,
  requirePromptKey = true,
  requireCompletionKey = true,
  requireIdealResponseKey = false,
  showClearButton = true,
  showReplaceButton = false,
  showPreviewButton = true,
}) => {
  const workspace = useWorkspaceFromPath();
  const queryClient = useQueryClient();

  const [state, dispatch] = useDatasetInputFileReducer();
  const {
    uploadModalOpen,
    previewModalOpen,
    isValidating,
    fileUrl,
    datasetLocation,
    validationResult,
    detectionResult,
    availableKeys,
    keyMapping,
    fileMetadata,
  } = state;

  // Emit onChange whenever the state contains a fully-validated result, or
  // null when no file is selected / validation failed. Uses a ref so the
  // effect doesn't re-fire when the caller passes a new onChange identity.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Monotonic selection id — bumped on every file selection AND reset so any
  // in-flight fetch/validate/parse work can check that its id still matches
  // the current selection before dispatching state updates. This prevents a
  // late-arriving validation from resurrecting a file the user already cleared
  // or replaced.
  const selectionIdRef = useRef(0);
  useEffect(() => {
    if (!fileUrl || !validationResult?.isValid || !fileMetadata) {
      onChangeRef.current(null);
      return;
    }
    onChangeRef.current({
      fileUrl,
      format: fileMetadata.format,
      validationResult,
      detectionResult,
      keyMapping,
      availableKeys,
      firstRow: fileMetadata.firstRow,
      parsedRows: fileMetadata.parsedRows,
      rowCount: fileMetadata.rowCount,
    });
  }, [fileUrl, validationResult, detectionResult, keyMapping, availableKeys, fileMetadata]);

  const handleFileSelected = useCallback(
    async (file: SubmitUploadType) => {
      if (file.type === 'file') return;

      // Guard against missing dataset metadata — workspace/name are typed as
      // optional on FilesetOutput but we can't proceed without them.
      const datasetWorkspace = file.dataset?.workspace;
      const datasetName = file.dataset?.name;
      if (!datasetWorkspace || !datasetName) {
        logger.error(
          `Cannot load dataset file: missing workspace or name: ${JSON.stringify(file.dataset)}`
        );
        return;
      }

      // Capture this selection's id so late async work can detect if it's stale.
      selectionIdRef.current += 1;
      const mySelectionId = selectionIdRef.current;

      dispatch({
        type: 'FILE_SELECTED',
        payload: {
          fileUrl: file.url,
          datasetLocation: {
            workspace: datasetWorkspace,
            name: datasetName,
            path: file.path,
          },
        },
      });

      try {
        const fileContent = await queryClient.fetchQuery(
          datasetFileContentQueryOptions({
            workspace: datasetWorkspace,
            name: datasetName,
            path: file.path,
          })
        );
        if (selectionIdRef.current !== mySelectionId) return;

        const fileName = file.path.split('/').pop() || 'file';
        const fileObj = new File([fileContent], fileName, { type: 'application/json' });

        const validation = await validateFileFormat(fileObj);
        if (selectionIdRef.current !== mySelectionId) return;

        if (!validation.isValid || !validation.format) {
          dispatch({ type: 'VALIDATION_FAILED', payload: validation });
          return;
        }

        const detection = await detectFileStructure(fileObj, validation.format);
        if (selectionIdRef.current !== mySelectionId) return;

        const firstRow = detection?.firstRow || null;
        const availableKeys = firstRow ? extractUserFriendlyKeysFromRow(firstRow) : [];

        // Parse all rows from file content
        const text = await fileObj.text();
        if (selectionIdRef.current !== mySelectionId) return;
        let parsedRows: Record<string, unknown>[];
        if (validation.format === 'jsonl') {
          parsedRows = text
            .trim()
            .split('\n')
            .filter((line) => line.length > 0)
            .map((line) => JSON.parse(line) as Record<string, unknown>);
        } else {
          const parsed = JSON.parse(text);
          parsedRows = Array.isArray(parsed) ? parsed : [parsed];
        }

        // Auto-resolve key mapping from detection
        const autoMapping: DatasetKeyMapping = {
          promptKey: null,
          completionKey: null,
          idealResponseKey: null,
        };
        if (detection?.schemaType === InputFileSchemaType.CHAT_COMPLETION) {
          if (detection.detectedMessages.user) {
            autoMapping.promptKey = detection.detectedMessages.user.selector;
          }
          if (detection.detectedMessages.assistant) {
            autoMapping.completionKey = detection.detectedMessages.assistant.selector;
          }
        } else if (detection?.schemaType === InputFileSchemaType.COMPLETION) {
          if (detection.detectedFields.prompt) {
            autoMapping.promptKey = detection.detectedFields.prompt;
          }
          if (detection.detectedFields.completion) {
            autoMapping.completionKey = detection.detectedFields.completion;
          }
        }

        if (selectionIdRef.current !== mySelectionId) return;
        dispatch({
          type: 'VALIDATION_SUCCEEDED',
          payload: {
            validationResult: validation,
            detectionResult: detection,
            availableKeys,
            keyMapping: autoMapping,
            fileMetadata: {
              format: validation.format,
              firstRow: firstRow || {},
              parsedRows,
              rowCount: parsedRows.length,
            },
          },
        });
      } catch (error) {
        if (selectionIdRef.current !== mySelectionId) return;
        dispatch({
          type: 'VALIDATION_FAILED',
          payload: {
            isValid: false,
            format: null,
            error: `Failed to validate file: ${error instanceof Error ? error.message : 'Unknown error'}`,
          },
        });
      }
    },
    [dispatch, queryClient]
  );

  const handleKeyMappingChange = useCallback(
    (field: keyof DatasetKeyMapping, value: string | null) => {
      dispatch({ type: 'SET_KEY_MAPPING_FIELD', payload: { field, value: value || null } });
    },
    [dispatch]
  );

  const setUploadModalOpen = (open: boolean) =>
    dispatch({ type: 'SET_UPLOAD_MODAL_OPEN', payload: open });
  const setPreviewModalOpen = (open: boolean) =>
    dispatch({ type: 'SET_PREVIEW_MODAL_OPEN', payload: open });

  const renderValidationStatus = () => {
    if (isValidating) {
      return (
        <Banner status="info" kind="inline">
          Validating file format and structure...
        </Banner>
      );
    }

    if (!validationResult) return null;

    if (!validationResult.isValid) {
      return (
        <Banner status="error" kind="inline">
          File validation failed: {validationResult.error}
          <br />
          <small>Please ensure your file is valid JSON/JSONL.</small>
        </Banner>
      );
    }

    const schemaType = detectionResult?.schemaType;

    // "Complete" = every required key is mapped (either auto-detected or picked manually)
    const allRequiredKeysSet =
      (!requirePromptKey || !!keyMapping.promptKey) &&
      (!requireCompletionKey || !!keyMapping.completionKey) &&
      (!requireIdealResponseKey || !!keyMapping.idealResponseKey);

    const needsManualMapping = !allRequiredKeysSet;

    return (
      <Panel elevation="high">
        <Stack gap="density-md">
          <Text kind="label/bold/md">File Validation</Text>

          <Flex gap="density-md" align="center">
            {SUCCESS_ICON}
            <Text kind="body/regular/md">{validationResult.format?.toUpperCase()} is valid</Text>
          </Flex>

          <Flex gap="density-md" align="center">
            {schemaType ? SUCCESS_ICON : HELP_ICON}
            <Text kind="body/regular/md">
              {schemaType ? `Detected Schema: ${schemaType}` : 'Schema could not be auto-detected'}
            </Text>
          </Flex>

          {allRequiredKeysSet && (
            <Flex gap="density-md" align="center">
              {SUCCESS_ICON}
              <Text kind="body/regular/md">All required keys detected</Text>
            </Flex>
          )}

          {needsManualMapping && availableKeys.length > 0 && (
            <Stack gap="density-md" className="border-t-1 border-t-base pt-4">
              <Text kind="label/bold/md">Map required keys from your input data</Text>

              {requirePromptKey && (
                <FormField slotLabel="Prompt Key">
                  {({ ...args }) => (
                    <Select
                      {...args}
                      value={keyMapping.promptKey || ''}
                      items={[
                        { children: 'Select a key...', value: '' },
                        ...availableKeys.map((k) => ({ children: k.label, value: k.value })),
                      ]}
                      onValueChange={(v: string) => handleKeyMappingChange('promptKey', v)}
                      disabled={disabled}
                      placeholder="Select a key"
                    />
                  )}
                </FormField>
              )}

              {requireCompletionKey && (
                <FormField slotLabel="Completion Key">
                  {({ ...args }) => (
                    <Select
                      {...args}
                      value={keyMapping.completionKey || ''}
                      items={[
                        { children: 'Select a key...', value: '' },
                        ...availableKeys.map((k) => ({ children: k.label, value: k.value })),
                      ]}
                      onValueChange={(v: string) => handleKeyMappingChange('completionKey', v)}
                      disabled={disabled}
                      placeholder="Select a key"
                    />
                  )}
                </FormField>
              )}

              {requireIdealResponseKey && (
                <FormField slotLabel="Ideal Response Key">
                  {({ ...args }) => (
                    <Select
                      {...args}
                      value={keyMapping.idealResponseKey || ''}
                      items={[
                        { children: 'Select a key...', value: '' },
                        ...availableKeys.map((k) => ({ children: k.label, value: k.value })),
                      ]}
                      onValueChange={(v: string) => handleKeyMappingChange('idealResponseKey', v)}
                      disabled={disabled}
                      placeholder="Select a key"
                    />
                  )}
                </FormField>
              )}
            </Stack>
          )}
        </Stack>
      </Panel>
    );
  };

  return (
    <Stack gap="density-md">
      <FormField slotLabel={label}>
        {fileUrl ? (
          <Flex gap="density-sm" align="center">
            <FileIcon size={16} className="shrink-0 text-fg-subdued" />
            <Text kind="body/regular/md" className="flex-1 truncate">
              {getDatasetDisplayNameFromFilesUrl(fileUrl) ?? fileUrl}
            </Text>
            {showClearButton && (
              <Button
                kind="tertiary"
                size="small"
                onClick={() => {
                  // Bump the selection id so any in-flight validation for the
                  // previous file is discarded instead of repopulating state.
                  selectionIdRef.current += 1;
                  dispatch({ type: 'RESET' });
                }}
                disabled={disabled}
                aria-label="Clear file"
              >
                <Trash2 size={14} />
              </Button>
            )}
            {showPreviewButton && (
              <Button
                kind="tertiary"
                size="small"
                onClick={() => setPreviewModalOpen(true)}
                disabled={disabled}
                aria-label="Preview file"
              >
                <Eye size={14} />
              </Button>
            )}
            {showReplaceButton && (
              <Button
                kind="tertiary"
                size="small"
                onClick={() => setUploadModalOpen(true)}
                disabled={disabled}
              >
                Replace
              </Button>
            )}
          </Flex>
        ) : (
          <Button
            kind="secondary"
            type="button"
            onClick={() => setUploadModalOpen(true)}
            disabled={disabled}
            className="w-full"
          >
            <Plus size={16} />
            Select File
          </Button>
        )}
      </FormField>

      {renderValidationStatus()}

      <UploadModal
        workspace={workspace}
        open={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        includeDataset
        onSubmit={handleFileSelected}
        submitButtonText="Add selected file"
      />

      {showPreviewButton && (
        <Modal
          open={previewModalOpen}
          onOpenChange={setPreviewModalOpen}
          slotHeading={
            fileUrl
              ? (getDatasetDisplayNameFromFilesUrl(fileUrl) ?? 'File Preview')
              : 'File Preview'
          }
          className="w-[90vw] max-w-[1000px]"
          slotFooter={
            <Flex justify="end" align="center" className="w-full">
              <Button kind="tertiary" onClick={() => setPreviewModalOpen(false)}>
                Close
              </Button>
            </Flex>
          }
        >
          {(() => {
            if (!datasetLocation || !fileMetadata) {
              return <Text>No file selected</Text>;
            }
            const cachedContent = queryClient.getQueryData<string>(
              datasetFileContentQueryOptions(datasetLocation).queryKey
            );
            if (!cachedContent) {
              return <Text>File content not available</Text>;
            }
            return (
              <CodeEditor
                contentType={fileMetadata.format === 'json' ? ContentType.JSON : ContentType.JSONL}
                content={cachedContent}
                readOnly
              />
            );
          })()}
        </Modal>
      )}
    </Stack>
  );
};
