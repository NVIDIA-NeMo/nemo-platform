// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { UploadModal } from '@nemo/common/src/components/UploadModal';
import type { SubmitUploadType } from '@nemo/common/src/components/UploadModal/types';
import { useChatCompletion } from '@nemo/common/src/hooks/useChatCompletion';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { FileFormat, InputFileSchemaType } from '@nemo/common/src/types';
import { extractUserFriendlyKeysFromRow, resolveKeyPath } from '@nemo/common/src/utils/file';
import { detectFileStructure, validateFileFormat } from '@nemo/common/src/utils/fileValidation';
import { type FileSampleMethod, sampleIndices } from '@nemo/common/src/utils/sampleTextLines';
import { filesDownloadFile } from '@nemo/sdk/generated/platform/api';
import { Button, Flex, Modal, Select, Text, Tooltip } from '@nvidia/foundations-react-core';
import { SAMPLE_DATASETS } from '@studio/components/chat/sampleDatasets';
import { StatsBadge } from '@studio/components/chat/StatsBadge';
import type { DatasetInputFileResult } from '@studio/components/DatasetInputFile';
import { FileSamplingMethodSelect } from '@studio/components/FileSamplingSnippet/FileSamplingMethodSelect';
import {
  PANEL_ROLE_COLORS,
  PANEL_ROLE_DOT_CLASS,
  PANEL_ROLE_LABELS,
  type SharedModelEntry,
} from '@studio/routes/ModelCompareRoute/types';
import { Maximize2, Plus, Trash2 } from 'lucide-react';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';

const DEFAULT_SAMPLE_SIZE = 5;

/** Number of inference requests to run concurrently; the rest queue. */
const INFERENCE_BATCH_SIZE = 10;

/** Sentinel item values for the dataset picker. */
const UPLOADED_FILE_VALUE = '__uploaded__';
const FILESET_PICKER_VALUE = '__fileset_picker__';

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
  stats?: ResponseStats;
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
      parsedRows = Array.isArray(parsed)
        ? (parsed as Record<string, unknown>[])
        : [parsed as Record<string, unknown>];
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
    promptKey = candidates.find((k) => typeof firstRow[k] === 'string') ?? null;
  }
  // If detection couldn't find a prompt column we still return the parsed file
  // (with `promptKey: null`) so the inline column picker can let the user choose.
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
  modelGroups: ModelWorkspaceGroup[];
  isLoadingModels: boolean;
  models: SharedModelEntry[];
  onRemoveModel: (id: number) => void;
  onSetModel: (id: number, modelURN: string | null) => void;
  /** Called when the view's readiness to add models changes (i.e. file is loaded with a valid prompt key) */
  onReadyChange?: (ready: boolean) => void;
  /** Called when the user clicks the Add Model button. Omit to hide the button. */
  onAddModel?: () => void;
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
  modelGroups,
  isLoadingModels,
  models,
  onRemoveModel,
  onSetModel,
  onReadyChange,
  agentName,
  onAddModel,
}) => {
  const [fileResult, setFileResult] = useState<DatasetInputFileResult | null>(null);
  const [promptRows, setPromptRows] = useState<PromptRow[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [sampleSize, setSampleSize] = useState<number>(DEFAULT_SAMPLE_SIZE);
  const [sampleMethod, setSampleMethod] = useState<FileSampleMethod>('random');
  const [expandedCell, setExpandedCell] = useState<ExpandedCellState | null>(null);
  const [pickerValue, setPickerValue] = useState<string | undefined>(undefined);
  // Bumped to remount the dataset Select after the "Select from dataset file..."
  // sentinel is chosen, so the action can be retriggered (re-selecting the same
  // option otherwise fires no change event).
  const [pickerSelectKey, setPickerSelectKey] = useState(0);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [isFilesetPickerOpen, setIsFilesetPickerOpen] = useState(false);
  // True when the loaded file's prompt column was auto-detected. In that case
  // we hide the manual column picker; we only surface it when detection failed.
  const [promptKeyAutoDetected, setPromptKeyAutoDetected] = useState(false);
  const { mutateAsync: createCompletion } = useChatCompletion();

  // Monotonic run id. Incremented on invalidation; guards stale writeCell calls.
  const runIdRef = useRef(0);
  // AbortController for the active run; aborted when a new run starts,
  // dataset/sampling changes, or the component unmounts.
  const runAbortRef = useRef<AbortController | null>(null);

  const rowCount = fileResult?.rowCount ?? 0;

  const handleFileChange = useCallback((result: DatasetInputFileResult | null) => {
    runIdRef.current += 1;
    runAbortRef.current?.abort();
    setFileResult(result);
    setPromptRows([]);
    setPromptKeyAutoDetected(result?.keyMapping.promptKey != null);
    if (result) {
      setSampleSize(Math.min(DEFAULT_SAMPLE_SIZE, result.rowCount || DEFAULT_SAMPLE_SIZE));
    }
  }, []);

  // Override the auto-detected prompt column. Updating `keyMapping.promptKey`
  // triggers the row-rebuild effect below; fresh rows clear stale responses.
  const handlePromptKeyChange = useCallback((key: string) => {
    setFileResult((prev) =>
      prev ? { ...prev, keyMapping: { ...prev.keyMapping, promptKey: key } } : prev
    );
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

    runAbortRef.current?.abort();
    const runController = new AbortController();
    runAbortRef.current = runController;

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
            signal: runController.signal,
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
    try {
      for (let i = 0; i < taskFactories.length; i += INFERENCE_BATCH_SIZE) {
        if (runController.signal.aborted) break;
        const batch = taskFactories.slice(i, i + INFERENCE_BATCH_SIZE).map((fn) => fn());
        await Promise.allSettled(batch);
      }
    } finally {
      if (runAbortRef.current === runController) {
        runAbortRef.current = null;
        setIsRunning(false);
      }
    }
  }, [models, promptRows, workspace, createCompletion, clearResponses]);

  // Cancel an in-flight run without clearing results. Bumping the run id makes
  // any writes from aborted (rejected) requests no-op, so completed cells keep
  // their results and still-pending cells stay blank. A later Run clears all.
  const cancelRun = useCallback(() => {
    runIdRef.current += 1;
    runAbortRef.current?.abort();
    runAbortRef.current = null;
    setIsRunning(false);
  }, []);

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
    const result: Record<number, (ResponseStats & { count: number }) | null> = {};
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

  // Abort any active run on unmount (e.g. tab switch, navigation).
  useEffect(() => {
    return () => {
      runAbortRef.current?.abort();
    };
  }, []);

  // Drive the prompt table from parsed preview rows + sampling controls (no separate file preview).
  useEffect(() => {
    if (!fileResult?.keyMapping.promptKey || !fileResult.parsedRows?.length) return;

    runIdRef.current += 1;
    runAbortRef.current?.abort();
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
    // We intentionally re-run only on `agentName` change. Including
    // `handleFileChange` (or the various setters) would re-fire this effect
    // every time the parent re-renders and produce a seed loop — the agentRef
    // guard above would still no-op the work, but the effect would still run
    // and we want the dependencies to read true.
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
      if (value === UPLOADED_FILE_VALUE) return;
      if (value === FILESET_PICKER_VALUE) {
        setIsFilesetPickerOpen(true);
        setPickerSelectKey((k) => k + 1);
        return;
      }
      const sample = SAMPLE_DATASETS.find((s) => s.id === value);
      if (!sample) return;
      setParseError(null);
      setUploadedFileName(null);
      setPickerValue(value);
      handleFileChange(sample.build());
    },
    [handleFileChange]
  );

  const handleFilesetPickerSubmit = useCallback(
    async (data: SubmitUploadType) => {
      if (data.type !== 'dataset') return;
      setIsFilesetPickerOpen(false);
      setParseError(null);
      try {
        // `data.url` is a `fileset://` URI, not an HTTP URL — download via the
        // SDK using the dataset's workspace/name and the file path.
        const response = await filesDownloadFile(
          data.dataset.workspace,
          data.dataset.name,
          data.path
        );
        if (!response) {
          setParseError('Failed to download file');
          return;
        }
        const text = await response.text();
        const filename = data.path.split('/').pop() ?? 'dataset.json';
        const file = new File([text], filename);
        const result = await parseUploadedFile(file);
        if ('error' in result) {
          setParseError(result.error);
          return;
        }
        setUploadedFileName(`${data.dataset.name}/${data.path}`);
        setPickerValue(UPLOADED_FILE_VALUE);
        handleFileChange(result);
      } catch (err) {
        setParseError(err instanceof Error ? err.message : 'Failed to load file');
      }
    },
    [handleFileChange]
  );

  const datasetItems = useMemo(() => {
    const items: { value: string; children: string }[] = SAMPLE_DATASETS.map((s) => ({
      value: s.id,
      children: s.label,
    }));
    if (uploadedFileName) {
      items.push({ value: UPLOADED_FILE_VALUE, children: uploadedFileName });
    }
    items.push({ value: FILESET_PICKER_VALUE, children: 'Select from dataset file...' });
    return items;
  }, [uploadedFileName]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden px-6 py-2">
      {/* Results table fills remaining height; this is the main vertical scroll region. */}
      <div className="flex min-h-0 flex-1">
        <div className="max-h-full flex-1 self-start overflow-auto rounded-lg border border-base bg-surface-raised">
          <table className="min-w-full table-fixed border-separate border-spacing-0">
            <colgroup>
              <col className="w-[320px] min-w-[280px]" />
              {models.map((m) => (
                <col key={m.id} className="w-[320px] min-w-[280px]" />
              ))}
            </colgroup>
            <thead className="sticky top-0 z-10 bg-surface-raised">
              {/* Row 1: sampling controls + role labels */}
              <tr>
                <th className="border-b border-r border-base px-3 py-2 text-left align-middle">
                  <Flex align="center" justify="between" gap="density-sm">
                    <Text kind="label/bold/md" className="shrink-0">
                      Prompts
                    </Text>
                    <FileSamplingMethodSelect
                      value={sampleMethod}
                      onValueChange={setSampleMethod}
                      size="medium"
                      rowCountGroup={{
                        value: sampleSize,
                        onValueChange: setSampleSize,
                        maxRows: Math.max(1, rowCount),
                        disabled: isRunning || rowCount === 0,
                      }}
                      attributes={{ select: { disabled: isRunning || rowCount === 0 } }}
                    />
                    {isRunning ? (
                      <Button kind="primary" color="danger" onClick={cancelRun}>
                        Stop
                      </Button>
                    ) : (
                      <Button
                        kind="primary"
                        color="brand"
                        onClick={runInference}
                        disabled={!hasPrompts || !hasAssignedModel}
                      >
                        Run
                      </Button>
                    )}
                  </Flex>
                </th>
                {models.map((m, idx) => {
                  const roleColor = PANEL_ROLE_COLORS[Math.min(idx, PANEL_ROLE_COLORS.length - 1)];
                  const colBorder = idx < models.length - 1 ? 'border-r ' : '';
                  return (
                    <th
                      key={m.id}
                      className={`border-b ${colBorder}border-base px-3 py-2 align-middle`}
                    >
                      <Flex align="center" justify="between">
                        <Flex align="center" gap="density-xs">
                          <span
                            className={`h-2 w-2 shrink-0 rounded-full ${PANEL_ROLE_DOT_CLASS[roleColor]}`}
                          />
                          <Text kind="label/bold/md">{PANEL_ROLE_LABELS[roleColor]}</Text>
                        </Flex>
                        <button
                          onClick={() => onRemoveModel(m.id)}
                          disabled={isRunning}
                          className="cursor-pointer rounded p-1 text-fg-subdued hover:bg-surface-sunken hover:text-fg-base"
                          aria-label="Remove model column"
                        >
                          <Trash2 size={14} />
                        </button>
                      </Flex>
                    </th>
                  );
                })}
              </tr>
              {/* Row 2: dataset picker + model selects */}
              <tr>
                <th
                  className={`${hasPrompts ? 'border-b ' : ''}border-r border-base px-3 py-2 align-top`}
                >
                  <Select
                    // Remount after the picker sentinel is chosen so its internal
                    // selection resets to the real value — otherwise re-clicking
                    // "Select from dataset file..." is a no-op (already selected).
                    key={pickerSelectKey}
                    items={datasetItems}
                    value={pickerValue}
                    onValueChange={handleDatasetSelect}
                    placeholder="Select prompts"
                    disabled={isRunning}
                    className="w-full"
                  />
                  {parseError && (
                    <Text kind="label/regular/sm" className="mt-1 text-fg-error">
                      {parseError}
                    </Text>
                  )}
                  {fileResult && !promptKeyAutoDetected && fileResult.availableKeys.length > 0 && (
                    <Flex align="center" gap="density-sm" className="mt-2">
                      <Text kind="label/regular/sm" className="shrink-0 text-fg-subdued">
                        Prompt Field
                      </Text>
                      <Select
                        items={fileResult.availableKeys.map((k) => ({
                          value: k.value,
                          children: k.label,
                        }))}
                        value={fileResult.keyMapping.promptKey ?? undefined}
                        onValueChange={handlePromptKeyChange}
                        placeholder="Select a field"
                        disabled={isRunning}
                        size="small"
                        className="w-full"
                      />
                    </Flex>
                  )}
                </th>
                {models.map((m, idx) => (
                  <th
                    key={m.id}
                    className={`${hasPrompts ? 'border-b ' : ''}${idx < models.length - 1 ? 'border-r ' : ''}border-base px-2 py-2 align-top`}
                  >
                    <ModelColumnSelect
                      modelGroups={modelGroups}
                      isLoadingModels={isLoadingModels}
                      value={m.modelURN}
                      disabled={isRunning}
                      onChange={(ref) => {
                        onSetModel(m.id, ref || null);
                        clearResponses(m.id);
                      }}
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {promptRows.map((row, rowIdx) => {
                const rowBottom = rowIdx < promptRows.length - 1 || anyAverages ? 'border-b ' : '';
                return (
                  <tr key={row.sourceIndex} className="bg-surface-raised">
                    <td className={`${rowBottom}border-r border-base p-0 align-top`}>
                      <ExpandableCell
                        content={row.prompt}
                        title={`Prompt (dataset row ${row.sourceIndex})`}
                        onExpand={setExpandedCell}
                        boldContent
                      />
                    </td>
                    {models.map((m, idx) => {
                      const response = row.responses[m.id];
                      const modelName = m.modelURN
                        ? getPartsFromReference(m.modelURN).name
                        : 'Model';
                      const colBorder = idx < models.length - 1 ? 'border-r ' : '';
                      if (response === undefined) {
                        return (
                          <td
                            key={m.id}
                            className={`${rowBottom}${colBorder}border-base px-3 py-2 align-top`}
                          >
                            <Text kind="body/regular/md" className="text-fg-subdued">
                              -
                            </Text>
                          </td>
                        );
                      }
                      if (response === null) {
                        return (
                          <td
                            key={m.id}
                            className={`${rowBottom}${colBorder}border-base px-3 py-2 align-top`}
                          >
                            <Text kind="body/regular/md" className="text-fg-error">
                              Error
                            </Text>
                          </td>
                        );
                      }
                      return (
                        <td
                          key={m.id}
                          className={`${rowBottom}${colBorder}border-base p-0 align-top`}
                        >
                          <ExpandableCell
                            content={response.text}
                            title={`${modelName} response (dataset row ${row.sourceIndex})`}
                            onExpand={(state) =>
                              setExpandedCell({ ...state, stats: response.stats })
                            }
                            footer={<StatsBadge metrics={response.stats} className="px-3 pb-2" />}
                          />
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
            {hasPrompts && anyAverages && (
              <tfoot className="sticky bottom-0 z-10 bg-surface-raised">
                <tr>
                  <td className="border-t-2 border-r border-base px-3 py-2 align-middle">
                    <Text kind="label/bold/md">Average</Text>
                  </td>
                  {models.map((m, idx) => {
                    const avg = averagesByModelId[m.id];
                    return (
                      <td
                        key={m.id}
                        className={`border-t-2 ${idx < models.length - 1 ? 'border-r ' : ''}border-base px-3 py-2 align-middle`}
                      >
                        {avg ? (
                          <StatsBadge metrics={avg} emphasis tone="brand" />
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
        {onAddModel && (
          <div className="flex shrink-0 self-start pl-1">
            <Tooltip slotContent="Add model">
              <button
                onClick={onAddModel}
                className="flex cursor-pointer items-center justify-center rounded border border-base bg-surface-raised p-1.5 text-fg-subdued transition-colors hover:bg-surface-sunken hover:text-fg-base"
                aria-label="Add model"
              >
                <Plus size={16} />
              </button>
            </Tooltip>
          </div>
        )}
      </div>

      <UploadModal
        workspace={workspace}
        open={isFilesetPickerOpen}
        includeDataset
        allowNewDataset
        title="Select File"
        submitButtonText="Select File"
        onClose={() => setIsFilesetPickerOpen(false)}
        onSubmit={handleFilesetPickerSubmit}
      />

      <Modal
        open={expandedCell !== null}
        onOpenChange={(open) => {
          if (!open) setExpandedCell(null);
        }}
        slotHeading={expandedCell?.title ?? 'Cell Content'}
        className="w-[90vw] max-w-[1000px]"
        slotFooter={
          <Flex justify="between" align="center" className="w-full">
            {expandedCell?.stats ? <StatsBadge metrics={expandedCell.stats} emphasis /> : <span />}
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
  footer?: React.ReactNode;
  boldContent?: boolean;
}> = ({ content, title, onExpand, footer, boldContent }) => {
  return (
    <div className="group relative flex h-full flex-col">
      <button
        onClick={() => onExpand({ title, content })}
        className="absolute right-1 top-1 z-10 cursor-pointer rounded bg-surface-base/80 p-1 opacity-0 hover:bg-surface-sunken group-hover:opacity-100"
        aria-label="Expand cell"
      >
        <Maximize2 size={12} />
      </button>
      <div className="max-h-[130px] overflow-y-auto px-3 py-2">
        <Text
          kind="body/regular/md"
          className={`whitespace-pre-wrap${boldContent ? ' font-bold' : ''}`}
        >
          {content}
        </Text>
      </div>
      {footer && <div className="mt-auto">{footer}</div>}
    </div>
  );
};

/** Thin wrapper around ModelSelectV2 for table header use */
const ModelColumnSelect: FC<{
  modelGroups: ModelWorkspaceGroup[];
  isLoadingModels: boolean;
  value: string | null;
  disabled?: boolean;
  onChange: (ref: string) => void;
}> = ({ modelGroups, isLoadingModels, value, disabled, onChange }) => {
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
      hideAdapters
      fullWidth
    />
  );
};
