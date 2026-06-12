// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { useChatCompletion } from '@nemo/common/src/hooks/useChatCompletion';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { resolveKeyPath } from '@nemo/common/src/utils/file';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import { type FileSampleMethod, sampleIndices } from '@nemo/common/src/utils/sampleTextLines';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Modal, Stack, Text } from '@nvidia/foundations-react-core';
import { DatasetInputFile, type DatasetInputFileResult } from '@studio/components/DatasetInputFile';
import { FileSamplingMethodSelect } from '@studio/components/FileSamplingSnippet/FileSamplingMethodSelect';
import type { SharedModelEntry } from '@studio/routes/ModelCompareRoute/types';
import { websiteLogger } from '@studio/util/logger';
import { Loader2, Maximize2, Play, Trash2 } from 'lucide-react';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';

const DEFAULT_SAMPLE_SIZE = 5;

/** Number of inference requests to run concurrently; the rest queue. */
const INFERENCE_BATCH_SIZE = 10;

interface PromptRow {
  /** Index in the parsed dataset. */
  sourceIndex: number;
  /** Resolved prompt text */
  prompt: string;
  /** Model id -> response text (null = error, undefined = not yet run) */
  responses: Record<number, string | null | undefined>;
}

interface ExpandedCellState {
  title: string;
  content: string;
}

/** Builds prompt rows from parsed dataset rows using the shared sampling controls. */
function buildPromptRowsFromParsedRows(
  fileResult: DatasetInputFileResult,
  sampleSize: number,
  sampleMethod: FileSampleMethod
): PromptRow[] {
  const promptKey = fileResult.keyMapping.promptKey;
  if (!promptKey || !fileResult.parsedRows?.length) return [];

  const parsedRows = fileResult.parsedRows;
  const indices = sampleIndices(parsedRows.length, sampleMethod, Math.max(1, sampleSize));

  const rows: PromptRow[] = [];
  for (const idx of indices) {
    const row = parsedRows[idx];
    if (!row) continue;
    const promptValue = resolveKeyPath(row, promptKey);
    if (promptValue === null || promptValue === undefined) continue;
    const prompt = typeof promptValue === 'string' ? promptValue : JSON.stringify(promptValue);
    rows.push({
      sourceIndex: idx,
      prompt,
      responses: {},
    });
  }
  return rows;
}

interface ModelComparePromptsProps {
  workspace: string;
  availableModels: ModelEntity[];
  isLoadingModels: boolean;
  models: SharedModelEntry[];
  onRemoveModel: (id: number) => void;
  onSetModel: (id: number, modelURN: string | null) => void;
  /** Called when the view's readiness to add models changes (i.e. file is loaded with a valid prompt key) */
  onReadyChange?: (ready: boolean) => void;
}

export const ModelComparePrompts: FC<ModelComparePromptsProps> = ({
  workspace,
  availableModels,
  isLoadingModels,
  models,
  onRemoveModel,
  onSetModel,
  onReadyChange,
}) => {
  const [fileResult, setFileResult] = useState<DatasetInputFileResult | null>(null);
  const [promptRows, setPromptRows] = useState<PromptRow[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [sampleSize, setSampleSize] = useState<number>(DEFAULT_SAMPLE_SIZE);
  const [sampleMethod, setSampleMethod] = useState<FileSampleMethod>('random');
  const [expandedCell, setExpandedCell] = useState<ExpandedCellState | null>(null);

  const { mutateAsync: createCompletion } = useChatCompletion();

  // Monotonic run id. Incremented when a run starts and when prompts
  // change, so any in-flight run that finishes later checks runIdRef before
  // writing results and drops the update if it's stale.
  const runIdRef = useRef(0);

  const rowCount = fileResult?.rowCount ?? 0;

  const handleFileChange = useCallback((result: DatasetInputFileResult | null) => {
    runIdRef.current += 1; // invalidate any in-flight run
    setFileResult(result);
    setPromptRows([]);
    if (result) {
      setSampleSize(Math.min(DEFAULT_SAMPLE_SIZE, result.rowCount || DEFAULT_SAMPLE_SIZE));
    }
  }, []);

  /**
   * Clear cached inference responses. If `columnId` is provided, only that
   * column's responses are cleared (e.g. when a new model is picked for the
   * column). If omitted, all responses across all columns are cleared
   * (e.g. on Run, or when picking new random prompts).
   */
  const clearResponses = useCallback((columnId?: number) => {
    setPromptRows((prev) =>
      prev.map((row) => {
        if (columnId === undefined) {
          return { ...row, responses: {} };
        }
        const next = { ...row.responses };
        delete next[columnId];
        return { ...row, responses: next };
      })
    );
  }, []);

  const runInference = useCallback(async () => {
    const activeModels = models
      .map((m) => {
        if (!m.modelURN) return null;
        const { workspace: modelWorkspace, name } = getPartsFromReference(m.modelURN);
        return { id: m.id, modelWorkspace, name };
      })
      .filter((m): m is { id: number; modelWorkspace: string; name: string } => m !== null);

    if (activeModels.length === 0 || promptRows.length === 0) return;

    // Snapshot inputs at start of run; any later change invalidates this run.
    const snapshotPromptRows = promptRows;
    const snapshotActiveModels = activeModels;
    runIdRef.current += 1;
    const myRunId = runIdRef.current;

    setIsRunning(true);
    clearResponses();

    // Writes a single cell's response, but only if this run is still current.
    const writeCell = (sourceIndex: number, modelId: number, content: string | null) => {
      if (runIdRef.current !== myRunId) return;
      setPromptRows((prev) =>
        prev.map((row) =>
          row.sourceIndex === sourceIndex
            ? { ...row, responses: { ...row.responses, [modelId]: content } }
            : row
        )
      );
    };

    // Build task factories (not yet fired). Each one updates its own cell as
    // soon as it resolves so results stream in.
    const taskFactories: Array<() => Promise<void>> = [];
    snapshotActiveModels.forEach((model) => {
      snapshotPromptRows.forEach((row) => {
        taskFactories.push(() =>
          createCompletion({
            model: model.name,
            workspace: model.modelWorkspace || workspace,
            messages: [{ role: 'user', content: row.prompt }],
            stream: false,
          })
            .then((result) => {
              const content =
                result && 'choices' in result
                  ? (result.choices[0]?.message?.content ?? null)
                  : null;
              writeCell(row.sourceIndex, model.id, content);
            })
            .catch((error) => {
              websiteLogger.error('Inference request failed', error);
              writeCell(row.sourceIndex, model.id, null);
            })
        );
      });
    });

    // Run tasks in capped-size batches so we don't flood the gateway.
    for (let i = 0; i < taskFactories.length; i += INFERENCE_BATCH_SIZE) {
      if (runIdRef.current !== myRunId) break; // stale run: stop firing more
      const batch = taskFactories.slice(i, i + INFERENCE_BATCH_SIZE).map((fn) => fn());
      await Promise.allSettled(batch);
    }

    if (runIdRef.current === myRunId) {
      setIsRunning(false);
    }
  }, [models, promptRows, workspace, createCompletion, clearResponses]);

  const hasPromptKey = fileResult?.keyMapping.promptKey != null;
  const hasAssignedModel = models.some((m) => m.modelURN !== null);
  const hasPrompts = promptRows.length > 0;

  // Notify parent when readiness changes. "Ready" means the table is active
  // (file is loaded and has a valid prompt key mapped).
  const isReady = !!fileResult && hasPromptKey;
  useEffect(() => {
    onReadyChange?.(isReady);
  }, [isReady, onReadyChange]);

  // Drive the prompt table from parsed preview rows + sampling controls (no separate file preview).
  useEffect(() => {
    if (!fileResult?.keyMapping.promptKey || !fileResult.parsedRows?.length) return;

    runIdRef.current += 1;
    setPromptRows(buildPromptRowsFromParsedRows(fileResult, sampleSize, sampleMethod));
  }, [fileResult, sampleSize, sampleMethod]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-6 py-4">
      <Stack gap="density-lg" className="max-w-lg min-w-0 shrink-0">
        <DatasetInputFile
          onChange={handleFileChange}
          label="Dataset File"
          disabled={isRunning}
          requirePromptKey
          requireCompletionKey={false}
          requireIdealResponseKey={false}
        />
      </Stack>

      {fileResult && hasPromptKey && (
        <Stack gap="density-md" className="min-h-0">
          <FileSamplingMethodSelect
            value={sampleMethod}
            onValueChange={setSampleMethod}
            rowCountGroup={{
              value: sampleSize,
              onValueChange: setSampleSize,
              maxRows: Math.max(1, rowCount),
              disabled: isRunning,
            }}
            attributes={{ select: { disabled: isRunning } }}
          />
        </Stack>
      )}
      {/* Results table fills remaining height; this is the main vertical scroll region. */}
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="min-w-full table-fixed border-separate border-spacing-0">
          <colgroup>
            <col className="w-[500px] min-w-[400px]" />
            {models.map((m) => (
              <col key={m.id} className="w-[320px] min-w-[280px]" />
            ))}
          </colgroup>
          <thead className="sticky top-0 z-10 bg-surface-raised">
            <tr>
              <th className="border border-base px-3 py-2 text-left font-medium align-middle">
                <Flex align="center" justify="between" gap="density-md">
                  <span>Prompts</span>
                  {fileResult && hasPromptKey && (
                    <Button
                      kind="primary"
                      size="small"
                      onClick={runInference}
                      disabled={isRunning || !hasPrompts || !hasAssignedModel}
                      className="bg-green-600 hover:bg-green-700"
                    >
                      {isRunning ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Play size={14} />
                      )}
                      {isRunning ? 'Running...' : 'Run'}
                    </Button>
                  )}
                </Flex>
              </th>
              {models.map((m) => (
                <th key={m.id} className="border-t border-b border-r border-base px-2 py-1">
                  <Flex gap="density-xs" align="center">
                    <div className="flex-1 min-w-0">
                      <ModelColumnSelect
                        models={availableModels}
                        isLoadingModels={isLoadingModels}
                        value={m.modelURN}
                        disabled={isRunning}
                        onChange={(ref) => {
                          onSetModel(m.id, ref || null);
                          clearResponses(m.id);
                        }}
                      />
                    </div>
                    <button
                      onClick={() => onRemoveModel(m.id)}
                      disabled={isRunning}
                      className="cursor-pointer rounded p-1"
                      aria-label="Remove model column"
                    >
                      <Trash2 size={14} />
                    </button>
                  </Flex>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {promptRows.map((row) => (
              <tr key={row.sourceIndex} className="bg-surface-raised">
                <td className="border-l border-b border-r border-base p-0 align-top">
                  <ExpandableCell
                    content={row.prompt}
                    title={`Prompt (dataset row ${row.sourceIndex})`}
                    onExpand={setExpandedCell}
                  />
                </td>
                {models.map((m) => {
                  const response = row.responses[m.id];
                  const modelName = m.modelURN ? getPartsFromReference(m.modelURN).name : 'Model';
                  if (response === undefined) {
                    return (
                      <td key={m.id} className="border-b border-r border-base px-3 py-2 align-top">
                        <Text kind="body/regular/md" className="text-fg-subdued">
                          -
                        </Text>
                      </td>
                    );
                  }
                  if (response === null) {
                    return (
                      <td key={m.id} className="border-b border-r border-base px-3 py-2 align-top">
                        <Text kind="body/regular/md" className="text-fg-error">
                          Error
                        </Text>
                      </td>
                    );
                  }
                  return (
                    <td key={m.id} className="border-b border-r border-base p-0 align-top">
                      <ExpandableCell
                        content={response}
                        title={`${modelName} response (dataset row ${row.sourceIndex})`}
                        onExpand={setExpandedCell}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        open={expandedCell !== null}
        onOpenChange={(open) => {
          if (!open) setExpandedCell(null);
        }}
        slotHeading={expandedCell?.title ?? 'Cell Content'}
        className="w-[90vw] max-w-[1000px]"
        slotFooter={
          <Flex justify="end" align="center" className="w-full">
            <Button kind="tertiary" onClick={() => setExpandedCell(null)}>
              Close
            </Button>
          </Flex>
        }
      >
        <div className="max-h-[70vh] overflow-auto">
          <Text kind="body/regular/md" className="whitespace-pre-wrap">
            {expandedCell?.content}
          </Text>
        </div>
      </Modal>
    </div>
  );
};

/** Table cell with vertical scroll and an expand-to-modal button */
const ExpandableCell: FC<{
  content: string;
  title: string;
  onExpand: (state: ExpandedCellState) => void;
}> = ({ content, title, onExpand }) => {
  return (
    <div className="group relative">
      <button
        onClick={() => onExpand({ title, content })}
        className="absolute right-1 top-1 z-10 cursor-pointer rounded bg-surface-base/80 p-1 opacity-0 hover:bg-surface-sunken group-hover:opacity-100"
        aria-label="Expand cell"
      >
        <Maximize2 size={12} />
      </button>
      <div className="max-h-[130px] overflow-y-auto px-3 py-2">
        <Text kind="body/regular/md" className="whitespace-pre-wrap">
          {content}
        </Text>
      </div>
    </div>
  );
};

/** Thin wrapper around ModelSelectV2 for table header use */
const ModelColumnSelect: FC<{
  models: ModelEntity[];
  isLoadingModels: boolean;
  value: string | null;
  disabled?: boolean;
  onChange: (ref: string) => void;
}> = ({ models, isLoadingModels, value, disabled, onChange }) => {
  const modelGroups = useMemo(() => groupModelsByWorkspace(models, { sort: true }), [models]);
  const selectedModel: ModelSelection | null = value ? { model: value } : null;

  const handleValueChange = useCallback(
    (selection: ModelSelection) => {
      onChange(selection.model);
    },
    [onChange]
  );

  return (
    <ModelSelectV2
      value={selectedModel}
      onValueChange={handleValueChange}
      groups={modelGroups}
      loading={isLoadingModels}
      disabled={disabled}
      placeholder={isLoadingModels ? 'Loading models...' : 'Select model...'}
      hideAdapters
      fullWidth
    />
  );
};
