// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { InferenceParamsSliderValues } from '@nemo/common/src/components/InferenceParamsSliders';
import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { useChatCompletion } from '@nemo/common/src/hooks/useChatCompletion';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { FileFormat, InputFileSchemaType } from '@nemo/common/src/types';
import { extractUserFriendlyKeysFromRow, resolveKeyPath } from '@nemo/common/src/utils/file';
import { detectFileStructure, validateFileFormat } from '@nemo/common/src/utils/fileValidation';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import { type FileSampleMethod, sampleIndices } from '@nemo/common/src/utils/sampleTextLines';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Modal, Select, Text } from '@nvidia/foundations-react-core';
import type { InferenceParams } from '@studio/components/chat/params';
import {
  computeWinners,
  CROWN_COLOR_CLASS,
  MetricValue,
  WINNER_ROWS,
} from '@studio/components/chat/BestPerformingSummary';
import { SAMPLE_DATASETS } from '@studio/components/chat/sampleDatasets';
import { DatasetDropdown } from '@studio/components/DatasetDropdown';
import type { DatasetInputFileResult } from '@studio/components/DatasetInputFile';
import {
  buildCountItems,
  clampRowCount,
  SAMPLE_METHOD_ITEMS,
} from '@studio/components/FileSamplingSnippet/FileSamplingMethodSelect';
import {
  PANEL_ROLE_COLORS,
  PANEL_ROLE_DOT_CLASS,
  PANEL_ROLE_LABELS,
  type SharedModelEntry,
} from '@studio/routes/ModelCompareRoute/types';
import {
  ChevronDown,
  ChevronUp,
  Crown,
  Gauge,
  Hash,
  Maximize2,
  Plus,
  Timer,
  Trash2,
} from 'lucide-react';
import {
  type ComponentProps,
  type FC,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

const DEFAULT_SAMPLE_SIZE = 5;

/** Number of inference requests to run concurrently; the rest queue. */
const INFERENCE_BATCH_SIZE = 10;

/** Sentinel value used to display a successfully uploaded file in the picker. */
const UPLOADED_FILE_VALUE = '__uploaded__';

/** Position-based role for a column index (same clamp rule the Compare grid uses). */
const roleForIndex = (idx: number) =>
  PANEL_ROLE_COLORS[Math.min(idx, PANEL_ROLE_COLORS.length - 1)];

/**
 * Colored dot + label, matching the Compare panel/summary role badges. The dot
 * color is keyed to the column role (Baseline/Comparison N); `label` overrides
 * the text (e.g. "Average") and defaults to the role name when omitted.
 */
const RoleBadge: FC<{
  index: number;
  title?: string;
  label?: string;
  textKind?: ComponentProps<typeof Text>['kind'];
}> = ({ index, title, label, textKind = 'label/semibold/sm' }) => {
  const role = roleForIndex(index);
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5" title={title}>
      <span className={`h-2 w-2 shrink-0 rounded-full ${PANEL_ROLE_DOT_CLASS[role]}`} />
      <span className="truncate">
        <Text kind={textKind}>{label ?? PANEL_ROLE_LABELS[role]}</Text>
      </span>
    </span>
  );
};

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
  if (!promptKey) {
    return {
      error: 'Could not detect a prompt column. Expected one of: prompt, question, input, text.',
    };
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
  /** Updates a model's inference params (shared with the Compare view). */
  onSetParams: (id: number, params: InferenceParams) => void;
  /** Adds another model column when the user clicks the trailing + control. */
  onAddModel?: () => void;
  /** When false, hides the trailing + control (e.g. at the max model count). */
  canAddModel?: boolean;
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
  onSetParams,
  onAddModel,
  canAddModel = false,
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
  const [summaryExpanded, setSummaryExpanded] = useState(true);
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
        // Only send params the user has touched — untouched params let the
        // provider apply its own defaults (matches the Compare tab).
        return { id: m.id, modelWorkspace, name, params: m.paramsTouched ? m.params : null };
      })
      .filter(
        (
          m
        ): m is {
          id: number;
          modelWorkspace: string;
          name: string;
          params: InferenceParams | null;
        } => m !== null
      );

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
            ...(model.params
              ? { temperature: model.params.temperature, max_tokens: model.params.max_tokens }
              : {}),
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
  const showAddColumn = canAddModel && !!onAddModel;

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
  const showFooter = hasPrompts && anyAverages;

  /**
   * Per-stat "winner" across the per-column averages. Null until at least two
   * columns have results, since a winner is only meaningful as a comparison.
   */
  const winners = useMemo(
    () =>
      computeWinners(
        models
          .map((m) => ({ id: m.id, avg: averagesByModelId[m.id] }))
          .filter(
            (e): e is { id: number; avg: ResponseStats & { count: number } } => e.avg !== null
          )
          .map((e) => ({
            id: e.id,
            stats: {
              totalMs: e.avg.totalMs,
              tokensPerSec: e.avg.tokensPerSec,
              completionTokens: e.avg.completionTokens,
            },
          }))
      ),
    [models, averagesByModelId]
  );

  const modelLabelById = useCallback(
    (id: number): string => {
      const m = models.find((mm) => mm.id === id);
      return m?.modelURN ? getPartsFromReference(m.modelURN).name : 'Model';
    },
    [models]
  );

  // Resolves a model id back to its column index, for position-based role identity.
  const idToIndex = useMemo(() => new Map(models.map((m, idx) => [m.id, idx])), [models]);

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
      const sample = SAMPLE_DATASETS.find((s) => s.id === value);
      if (!sample) return;
      setParseError(null);
      setUploadedFileName(null);
      setPickerValue(value);
      handleFileChange(sample.build());
    },
    [handleFileChange]
  );

  const handleClearDataset = useCallback(() => {
    setPickerValue(undefined);
    setUploadedFileName(null);
    setParseError(null);
    handleFileChange(null);
  }, [handleFileChange]);

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
    const items: { value: string; label: string }[] = SAMPLE_DATASETS.map((s) => ({
      value: s.id,
      label: s.label,
    }));
    if (uploadedFileName) {
      items.push({ value: UPLOADED_FILE_VALUE, label: uploadedFileName });
    }
    return items;
  }, [uploadedFileName]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden px-6 pt-2 pb-4">
      {parseError && (
        <Text kind="label/regular/sm" className="text-fg-error shrink-0">
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

      {/* Results table fills remaining height; this is the main vertical scroll region. */}
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="min-w-full table-fixed border-separate border-spacing-0">
          <colgroup>
            <col className="w-[500px] min-w-[400px]" />
            {models.map((m) => (
              <col key={m.id} className="min-w-[280px]" />
            ))}
            {showAddColumn && <col className="w-[44px]" />}
          </colgroup>
          <thead className="sticky top-0 z-10 bg-surface-raised">
            {/* Role title row — "Prompts" + Sort/Rows/Run controls, then Baseline / Comparison N. */}
            <tr>
              <th className="rounded-tl-lg border-l border-t border-r border-base px-3 pt-2 pb-1 text-left align-bottom">
                <Flex align="center" justify="between" gap="density-md">
                  <Text kind="label/semibold/md">Prompts</Text>
                  {isReady && (
                    <Flex align="center" gap="density-sm" className="shrink-0">
                      <Select
                        multiple={false}
                        items={SAMPLE_METHOD_ITEMS}
                        value={sampleMethod}
                        onValueChange={(next) => setSampleMethod(next as FileSampleMethod)}
                        disabled={isRunning}
                        size="small"
                        slotEnd={
                          <Text
                            kind="body/regular/sm"
                            className="text-[var(--text-color-placeholder)]"
                          >
                            Sort
                          </Text>
                        }
                        className="w-[150px] grow-0"
                      />
                      <Select
                        multiple={false}
                        items={buildCountItems(Math.max(1, rowCount), sampleSize)}
                        value={String(clampRowCount(sampleSize, Math.max(1, rowCount)))}
                        onValueChange={(next) => setSampleSize(Number(next))}
                        disabled={isRunning}
                        size="small"
                        slotEnd={
                          <Text
                            kind="body/regular/sm"
                            className="text-[var(--text-color-placeholder)]"
                          >
                            Rows
                          </Text>
                        }
                        className="w-[110px] grow-0"
                      />
                      <Button
                        kind="primary"
                        color="brand"
                        size="small"
                        onClick={runInference}
                        disabled={isRunning || !hasPrompts || !hasAssignedModel}
                      >
                        {isRunning ? 'Running...' : 'Run'}
                      </Button>
                    </Flex>
                  )}
                </Flex>
              </th>
              {models.map((m, idx) => (
                <th
                  key={m.id}
                  className={`border-t border-r border-base px-2 pt-2 pb-1 text-left align-bottom ${
                    idx === models.length - 1 ? 'rounded-tr-lg' : ''
                  }`}
                >
                  <Flex align="center" justify="between" gap="density-xs">
                    <div className="px-1 min-w-0">
                      <RoleBadge
                        index={idx}
                        title={modelLabelById(m.id)}
                        textKind="label/semibold/md"
                      />
                    </div>
                    <button
                      onClick={() => onRemoveModel(m.id)}
                      disabled={isRunning}
                      className="shrink-0 cursor-pointer rounded p-1"
                      aria-label="Remove model column"
                    >
                      <Trash2 size={14} />
                    </button>
                  </Flex>
                </th>
              ))}
              {showAddColumn && (
                <th className="bg-surface-sunken pl-3 pr-0 align-top">
                  <Flex justify="end">
                    <Button
                      kind="secondary"
                      size="small"
                      aria-label="Add model column"
                      title="Add model column"
                      onClick={onAddModel}
                      disabled={isRunning}
                      className="h-8 w-8 shrink-0 !px-0 !border-[var(--border-color-interaction-base)] !bg-[var(--background-color-interaction-base)] hover:!border-[var(--border-color-interaction-hover)]"
                    >
                      <Plus size={16} />
                    </Button>
                  </Flex>
                </th>
              )}
            </tr>
            {/* Model picker row — dataset dropdown + model selectors. */}
            <tr>
              <th className="border-l border-b border-r border-base px-3 pt-1 pb-2 align-middle">
                <DatasetDropdown
                  datasets={datasetItems}
                  value={pickerValue}
                  onValueChange={handleDatasetSelect}
                  onUpload={() => fileInputRef.current?.click()}
                  onClear={handleClearDataset}
                  placeholder="Select a dataset..."
                  disabled={isRunning}
                  size="small"
                  className="w-full"
                />
              </th>
              {models.map((m) => (
                <th key={m.id} className="border-b border-r border-base px-2 pb-2 pt-1 text-left">
                  <ModelColumnSelect
                    models={availableModels}
                    isLoadingModels={isLoadingModels}
                    value={m.modelURN}
                    disabled={isRunning}
                    inferenceParams={m.params}
                    onInferenceParamsChange={(p) => onSetParams(m.id, { ...m.params, ...p })}
                    onChange={(ref) => {
                      onSetModel(m.id, ref || null);
                      clearResponses(m.id);
                    }}
                  />
                </th>
              ))}
              {showAddColumn && <th aria-hidden className="bg-surface-sunken" />}
            </tr>
          </thead>
          <tbody>
            {promptRows.map((row, rowIdx) => {
              const roundBottom = rowIdx === promptRows.length - 1 && !showFooter;
              return (
                <tr key={row.sourceIndex} className="bg-surface-raised">
                  <td
                    className={`border-l border-b border-r border-base p-0 align-top ${
                      roundBottom ? 'rounded-bl-lg' : ''
                    }`}
                  >
                    <ExpandableCell
                      content={row.prompt}
                      title={`Prompt (dataset row ${row.sourceIndex})`}
                      onExpand={setExpandedCell}
                    />
                  </td>
                  {models.map((m, idx) => {
                    const response = row.responses[m.id];
                    const modelName = m.modelURN ? getPartsFromReference(m.modelURN).name : 'Model';
                    const brClass = roundBottom && idx === models.length - 1 ? 'rounded-br-lg' : '';
                    if (response === undefined) {
                      return (
                        <td
                          key={m.id}
                          className={`border-b border-r border-base px-3 py-2 align-top ${brClass}`}
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
                          className={`border-b border-r border-base px-3 py-2 align-top ${brClass}`}
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
                        className={`relative border-b border-r border-base p-0 align-top ${brClass}`}
                      >
                        <ExpandableCell
                          content={response.text}
                          title={`${modelName} response (dataset row ${row.sourceIndex})`}
                          onExpand={setExpandedCell}
                        />
                        {/* Pinned to the cell's bottom edge (the td is the
                         *  positioning context). Table cells always fill the row
                         *  height, so the stats line up across every column
                         *  regardless of response length. */}
                        <CellStats
                          stats={response.stats}
                          className="absolute inset-x-0 bottom-0 bg-surface-raised px-3 pb-2 pt-3"
                        />
                      </td>
                    );
                  })}
                  {showAddColumn && <td aria-hidden className="bg-surface-sunken" />}
                </tr>
              );
            })}
          </tbody>
          {showFooter && (
            <tfoot className="sticky bottom-0 z-10 bg-surface-sunken">
              {/* Header row — the "Best Performing" accordion toggle (col 0) and a
               *  per-model "Averages:" header. When collapsed this is the only
               *  footer row, so it carries the bottom border / rounded corners. */}
              <tr>
                <td
                  className={`border-l border-t border-r border-base px-3 py-2 align-middle ${
                    !summaryExpanded ? 'rounded-bl-lg border-b' : ''
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setSummaryExpanded((v) => !v)}
                    className="flex w-full cursor-pointer items-center justify-between gap-1.5"
                    aria-expanded={summaryExpanded}
                  >
                    <span className="inline-flex items-center gap-1.5">
                      {models.length > 1 && <Crown size={14} className={CROWN_COLOR_CLASS} />}
                      <Text kind="label/semibold/sm">
                        {models.length === 1 ? '' : 'Best Performing'}
                      </Text>
                    </span>
                    {summaryExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                </td>
                {models.map((m, idx) => (
                  <td
                    key={m.id}
                    className={`border-t border-r border-base px-3 py-2 align-middle ${
                      !summaryExpanded ? 'border-b' : ''
                    } ${!summaryExpanded && idx === models.length - 1 ? 'rounded-br-lg' : ''}`}
                  >
                    <RoleBadge index={idx} title={modelLabelById(m.id)} label="Average" />
                  </td>
                ))}
                {showAddColumn && <td aria-hidden className="bg-surface-sunken" />}
              </tr>
              {/* Metric rows — one per dimension, only when expanded. Each model's
               *  average value stacks vertically, aligned by table row, and turns
               *  brand green when that model wins the metric. */}
                {summaryExpanded &&
                WINNER_ROWS.map(({ key, label }, rowIdx) => {
                  const isLastRow = rowIdx === WINNER_ROWS.length - 1;
                  return (
                    <tr key={key}>
                      <td
                        className={`border-l border-r border-base px-3 py-2 align-middle ${
                          isLastRow ? 'rounded-bl-lg border-b' : ''
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <Text kind="body/regular/sm" className="text-fg-subdued">
                            {label}
                          </Text>
                          {winners && (
                            <RoleBadge
                              index={idToIndex.get(winners[key]) ?? 0}
                              title={modelLabelById(winners[key])}
                            />
                          )}
                        </div>
                      </td>
                      {models.map((m, idx) => {
                        const avg = averagesByModelId[m.id];
                        const isWinner = winners ? winners[key] === m.id : false;
                        const isLastModel = idx === models.length - 1;
                        return (
                          <td
                            key={m.id}
                            className={`border-r border-base px-3 py-2 align-middle ${
                              isLastRow ? 'border-b' : ''
                            } ${isLastRow && isLastModel ? 'rounded-br-lg' : ''}`}
                          >
                            {avg ? (
                              <MetricValue stats={avg} metricKey={key} highlight={isWinner} />
                            ) : (
                              <Text kind="body/regular/md" className="text-fg-subdued">
                                —
                              </Text>
                            )}
                          </td>
                        );
                      })}
                      {showAddColumn && <td aria-hidden className="bg-surface-sunken" />}
                    </tr>
                  );
                })}
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
      className={`inline-flex items-center gap-4 text-xs font-mono text-[var(--color-brand)] ${className ?? ''}`}
    >
      <span className="inline-flex items-center gap-1" title="Total time">
        <Timer size={12} />
        {seconds}s
      </span>
      <span className="inline-flex items-center gap-1" title="Tokens per second">
        <Gauge size={12} />
        {tokensPerSec} t/s
      </span>
      <span className="inline-flex items-center gap-1" title="Completion tokens">
        <Hash size={12} />
        {stats.completionTokens} tok
      </span>
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
      {/* pb-10 reserves room for the absolutely-positioned stats footer so a
       *  long response never renders underneath it. */}
      <div className="max-h-[130px] overflow-y-auto px-3 pb-10 pt-2">
        <Text kind="body/regular/md" className="whitespace-pre-wrap">
          {content}
        </Text>
      </div>
    </div>
  );
};

/** Thin wrapper around ModelSelectV2 for table header use. Mirrors the
 *  Compare tab's selector: full-width with the inline params button. */
const ModelColumnSelect: FC<{
  models: ModelEntity[];
  isLoadingModels: boolean;
  value: string | null;
  disabled?: boolean;
  inferenceParams: InferenceParams;
  onInferenceParamsChange: (params: Partial<InferenceParamsSliderValues>) => void;
  onChange: (ref: string) => void;
}> = ({
  models,
  isLoadingModels,
  value,
  disabled,
  inferenceParams,
  onInferenceParamsChange,
  onChange,
}) => {
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
      size="small"
      showParams
      showParamsLabel={false}
      triggerDisplay="urn"
      inferenceParams={inferenceParams}
      onInferenceParamsChange={onInferenceParamsChange}
    />
  );
};
