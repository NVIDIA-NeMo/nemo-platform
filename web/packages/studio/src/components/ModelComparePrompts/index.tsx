// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { useChatCompletion } from '@nemo/common/src/hooks/useChatCompletion';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { FileFormat, InputFileSchemaType } from '@nemo/common/src/types';
import { extractUserFriendlyKeysFromRow, resolveKeyPath } from '@nemo/common/src/utils/file';
import { detectFileStructure, validateFileFormat } from '@nemo/common/src/utils/fileValidation';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import { type FileSampleMethod, sampleIndices } from '@nemo/common/src/utils/sampleTextLines';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Modal, Select, Stack, Text } from '@nvidia/foundations-react-core';
import { SAMPLE_DATASETS } from '@studio/components/chat/sampleDatasets';
import type { DatasetInputFileResult } from '@studio/components/DatasetInputFile';
import { FileSamplingMethodSelect } from '@studio/components/FileSamplingSnippet/FileSamplingMethodSelect';
import type { SharedModelEntry } from '@studio/routes/ModelCompareRoute/types';
import { Loader2, Maximize2, Play, Trash2 } from 'lucide-react';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';

const DEFAULT_SAMPLE_SIZE = 5;

/** Number of inference requests to run concurrently; the rest queue. */
const INFERENCE_BATCH_SIZE = 10;

/** Sentinel item values for the dataset picker. */
const UPLOAD_ACTION_VALUE = '__upload__';
const UPLOADED_FILE_VALUE = '__uploaded__';

/** Brand green — matches the Chat tab StatsBadge. */
const STATS_GREEN = '#76b900';

interface ResponseStats {
  /** Wall-clock time from request fire to response, in ms. */
  totalMs: number;
  /** From `usage.completion_tokens` when the gateway returns it; otherwise estimated from text length. */
  completionTokens: number;
  /** Derived: completionTokens / (totalMs / 1000). */
  tokensPerSec: number;
}

interface ResponseResult {
  text: string;
  stats: ResponseStats;
}

interface PromptRow {
  /** Index in the parsed dataset. */
  sourceIndex: number;
  /** Resolved prompt text */
  prompt: string;
  /** Model id -> response data (null = error, undefined = not yet run) */
  responses: Record<number, ResponseResult | null | undefined>;
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

/**
 * Inline upload parser. Mirrors `DatasetInputFile`'s file path but runs without
 * its full validation UI — errors surface as a small inline banner under the
 * picker. We can't reuse `DatasetInputFile` here because we want a single
 * dropdown that owns both sample selection and upload.
 */
async function parseUploadedFile(file: File): Promise<DatasetInputFileResult | { error: string }> {
  const validation = await validateFileFormat(file);
  if (!validation.isValid || !validation.format) {
    return { error: validation.error ?? 'Invalid file format' };
  }
  const detection = await detectFileStructure(file, validation.format);
  const text = await file.text();
  let parsedRows: Record<string, unknown>[];
  try {
    if (validation.format === FileFormat.JSONL) {
      parsedRows = text
        .trim()
        .split('\n')
        .filter((line) => line.length > 0)
        .map((line) => JSON.parse(line) as Record<string, unknown>);
    } else {
      const parsed: unknown = JSON.parse(text);
      parsedRows = Array.isArray(parsed) ? (parsed as Record<string, unknown>[]) : [parsed as Record<string, unknown>];
    }
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to parse file contents' };
  }
  if (parsedRows.length === 0) {
    return { error: 'File contains no rows' };
  }
  const firstRow = (detection?.firstRow as Record<string, unknown> | undefined) ?? parsedRows[0];
  const availableKeys = firstRow ? extractUserFriendlyKeysFromRow(firstRow) : [];

  // Auto-detect prompt key: prefer the detector's answer, then fall back to common keys.
  let promptKey: string | null = null;
  if (detection?.schemaType === InputFileSchemaType.COMPLETION) {
    promptKey = detection.detectedFields.prompt ?? null;
  } else if (detection?.schemaType === InputFileSchemaType.CHAT_COMPLETION) {
    promptKey = detection.detectedMessages.user?.selector ?? null;
  }
  if (!promptKey) {
    const candidates = ['prompt', 'question', 'input', 'text'];
    promptKey =
      candidates.find((k) => typeof firstRow[k] === 'string') ?? null;
  }
  if (!promptKey) {
    return { error: 'Could not detect a prompt column. Expected one of: prompt, question, input, text.' };
  }
  return {
    fileUrl: `upload://${file.name}`,
    format: validation.format,
    validationResult: validation,
    detectionResult: detection,
    availableKeys,
    keyMapping: { promptKey, completionKey: null, idealResponseKey: null },
    firstRow,
    parsedRows,
    rowCount: parsedRows.length,
  };
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
  /**
   * When set, default-select the matching `SAMPLE_DATASETS` entry on mount so
   * the user lands on the agent's golden-prompts dataset without a click.
   * Matching is by id equality (e.g. agent name "calculator-agent" matches the
   * "calculator-agent" sample). Other samples remain pickable.
   */
  agentName?: string | null;
}

export const ModelComparePrompts: FC<ModelComparePromptsProps> = ({
  workspace,
  availableModels,
  isLoadingModels,
  models,
  onRemoveModel,
  onSetModel,
  onReadyChange,
  agentName,
}) => {
  const [fileResult, setFileResult] = useState<DatasetInputFileResult | null>(null);
  const [promptRows, setPromptRows] = useState<PromptRow[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [sampleSize, setSampleSize] = useState<number>(DEFAULT_SAMPLE_SIZE);
  const [sampleMethod, setSampleMethod] = useState<FileSampleMethod>('random');
  const [expandedCell, setExpandedCell] = useState<ExpandedCellState | null>(null);
  const [pickerValue, setPickerValue] = useState<string | undefined>(undefined);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

    // Writes a single cell's result, but only if this run is still current.
    const writeCell = (sourceIndex: number, modelId: number, result: ResponseResult | null) => {
      if (runIdRef.current !== myRunId) return;
      setPromptRows((prev) =>
        prev.map((row) =>
          row.sourceIndex === sourceIndex
            ? { ...row, responses: { ...row.responses, [modelId]: result } }
            : row
        )
      );
    };

    // Build task factories (not yet fired). Each one updates its own cell as
    // soon as it resolves so results stream in.
    const taskFactories: Array<() => Promise<void>> = [];
    snapshotActiveModels.forEach((model) => {
      snapshotPromptRows.forEach((row) => {
        taskFactories.push(() => {
          const startTime = performance.now();
          return createCompletion({
            model: model.name,
            workspace: model.modelWorkspace || workspace,
            messages: [{ role: 'user', content: row.prompt }],
            stream: false,
          })
            .then((result) => {
              const totalMs = performance.now() - startTime;
              const content =
                result && 'choices' in result
                  ? (result.choices[0]?.message?.content ?? null)
                  : null;
              if (content === null) {
                writeCell(row.sourceIndex, model.id, null);
                return;
              }
              const usage = result && 'usage' in result ? result.usage : undefined;
              // Fallback estimate: ~4 chars per token. Good enough for the badge when
              // the gateway elides usage stats.
              const completionTokens =
                usage?.completion_tokens ?? Math.max(1, Math.round(content.length / 4));
              const tokensPerSec = totalMs > 0 ? completionTokens / (totalMs / 1000) : 0;
              writeCell(row.sourceIndex, model.id, {
                text: content,
                stats: { totalMs, completionTokens, tokensPerSec },
              });
            })
            .catch((error) => {
              console.error('Inference request failed:', error);
              writeCell(row.sourceIndex, model.id, null);
            });
        });
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

  /**
   * Per-column averages across all completed responses. `tokensPerSec` is
   * weighted (sum tokens / sum seconds) rather than a mean-of-means so short
   * responses don't over-influence the rate. Returns null for columns with
   * zero completed responses so the footer can render an em-dash.
   */
  const averagesByModelId = useMemo(() => {
    const result: Record<number, ResponseStats & { count: number } | null> = {};
    models.forEach((m) => {
      let totalMs = 0;
      let totalTokens = 0;
      let count = 0;
      promptRows.forEach((row) => {
        const r = row.responses[m.id];
        if (!r) return;
        totalMs += r.stats.totalMs;
        totalTokens += r.stats.completionTokens;
        count += 1;
      });
      if (count === 0) {
        result[m.id] = null;
        return;
      }
      result[m.id] = {
        totalMs: totalMs / count,
        completionTokens: totalTokens / count,
        tokensPerSec: totalMs > 0 ? totalTokens / (totalMs / 1000) : 0,
        count,
      };
    });
    return result;
  }, [models, promptRows]);

  const anyAverages = Object.values(averagesByModelId).some((a) => a !== null);

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

  // Auto-select the agent's matching sample when the user lands on Run Prompts
  // via the agent overlay. Tracks the last-auto-selected agent in a ref so we
  // don't re-fire after the user clears the picker or picks a different file.
  const autoSelectedAgentRef = useRef<string | null>(null);
  useEffect(() => {
    if (!agentName) {
      autoSelectedAgentRef.current = null;
      return;
    }
    if (autoSelectedAgentRef.current === agentName) return;
    const match = SAMPLE_DATASETS.find((s) => s.id === agentName);
    if (!match) return;
    autoSelectedAgentRef.current = agentName;
    setPickerValue(match.id);
    setUploadedFileName(null);
    setParseError(null);
    handleFileChange(match.build());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentName]);

  /**
   * Single picker handler. Three branches:
   *  - sample id → synthesize the result via `sample.build()` (in-memory)
   *  - upload sentinel → click the hidden native file input
   *  - uploaded sentinel → no-op (it's the displayed value after a successful upload)
   */
  const handleDatasetSelect = useCallback(
    (value: string) => {
      if (!value) return;
      if (value === UPLOAD_ACTION_VALUE) {
        fileInputRef.current?.click();
        return;
      }
      if (value === UPLOADED_FILE_VALUE) return;
      const sample = SAMPLE_DATASETS.find((s) => s.id === value);
      if (!sample) return;
      setParseError(null);
      setUploadedFileName(null);
      setPickerValue(value);
      handleFileChange(sample.build());
    },
    [handleFileChange]
  );

  const handleFileUploadInput = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      // Reset the input so the same file can be re-picked later.
      event.target.value = '';
      if (!file) return;
      setParseError(null);
      const result = await parseUploadedFile(file);
      if ('error' in result) {
        setParseError(result.error);
        return;
      }
      setUploadedFileName(file.name);
      setPickerValue(UPLOADED_FILE_VALUE);
      handleFileChange(result);
    },
    [handleFileChange]
  );

  const datasetItems = useMemo(() => {
    const items: { value: string; children: string }[] = SAMPLE_DATASETS.map((s) => ({
      value: s.id,
      children: s.label,
    }));
    if (uploadedFileName) {
      items.push({ value: UPLOADED_FILE_VALUE, children: `Uploaded: ${uploadedFileName}` });
    }
    items.push({ value: UPLOAD_ACTION_VALUE, children: 'Upload from disk…' });
    return items;
  }, [uploadedFileName]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-6 py-4">
      <Stack gap="density-xs" className="max-w-lg min-w-0 shrink-0">
        <Text kind="label/bold/sm">Dataset</Text>
        <Select
          items={datasetItems}
          value={pickerValue}
          onValueChange={handleDatasetSelect}
          placeholder="Pick a sample or upload your own…"
          disabled={isRunning}
          className="w-full"
        />
        {parseError && (
          <Text kind="label/regular/sm" className="text-fg-error">
            {parseError}
          </Text>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,.jsonl"
          className="hidden"
          onChange={handleFileUploadInput}
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
                        content={response.text}
                        title={`${modelName} response (dataset row ${row.sourceIndex})`}
                        onExpand={setExpandedCell}
                        footer={<CellStats stats={response.stats} className="px-3 pb-2" />}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          {hasPrompts && anyAverages && (
            <tfoot className="sticky bottom-0 z-10 bg-surface-sunken">
              <tr>
                <td className="border-l border-t border-b border-r border-base px-3 py-2 align-middle font-medium">
                  Average
                </td>
                {models.map((m) => {
                  const avg = averagesByModelId[m.id];
                  return (
                    <td
                      key={m.id}
                      className="border-t border-b border-r border-base px-3 py-2 align-middle"
                    >
                      {avg ? (
                        <CellStats stats={avg} />
                      ) : (
                        <Text kind="body/regular/md" className="text-fg-subdued">
                          —
                        </Text>
                      )}
                    </td>
                  );
                })}
              </tr>
            </tfoot>
          )}
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

/**
 * Compact stats line — brand green, same look as the Chat tab's StatsBadge.
 * No padding by default; parents wrap with the padding that fits their slot
 * (response cells add their own horizontal padding; the footer row's td
 * already pads). Pass `className` to override.
 */
const CellStats: FC<{ stats: ResponseStats; className?: string }> = ({ stats, className }) => {
  const seconds = (stats.totalMs / 1000).toFixed(1);
  const tokensPerSec = Math.max(0, Math.round(stats.tokensPerSec));
  return (
    <div
      className={`text-xs font-mono ${className ?? ''}`}
      style={{ color: STATS_GREEN }}
    >
      {seconds}s · {stats.completionTokens} tok · {tokensPerSec} t/s
    </div>
  );
};

/** Table cell with vertical scroll and an expand-to-modal button */
const ExpandableCell: FC<{
  content: string;
  title: string;
  onExpand: (state: ExpandedCellState) => void;
  footer?: React.ReactNode;
}> = ({ content, title, onExpand, footer }) => {
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
      {footer}
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
