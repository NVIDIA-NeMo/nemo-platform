// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AssistantMessageCompletion } from '@nemo/common/src/components/AssistantChat/types';
import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import type { InferenceParamsSliderValues } from '@nemo/common/src/components/InferenceParamsSliders';
import {
  DropdownContent,
  DropdownItem,
  DropdownRoot,
  DropdownTrigger,
  Text,
  TextArea,
  Tooltip,
} from '@nvidia/foundations-react-core';
import type { InferenceParams } from '@studio/components/chat/params';
import { useFineTunedGroup } from '@studio/components/chat/useFineTunedGroup';
import { ModelChat } from '@studio/components/ModelChat';
import { PANEL_ROLE_DOT_CLASS, type PanelState } from '@studio/routes/ModelCompareRoute/types';
import {
  ChevronDown,
  ChevronUp,
  EllipsisVertical,
  MessageSquare,
  Minimize2,
  Trash2,
} from 'lucide-react';
import { useCallback, useMemo, useState, type FC } from 'react';

interface ModelChatPanelProps {
  panel: PanelState;
  /** Fallback workspace used only if a panel has no model assigned yet. */
  fallbackWorkspace: string;
  models: ModelEntity[];
  isLoadingModels: boolean;
  onToggle: (id: number) => void;
  onRemove: (id: number) => void;
  /** Receives the full URN ("workspace/name"), or null when cleared. */
  onModelChange: (id: number, modelURN: string | null) => void;
  onSystemPromptChange: (id: number, value: string) => void;
  onParamsChange: (id: number, params: InferenceParams) => void;
  /** Per-panel actions surfaced in the header kebab menu. */
  onEvaluate: (id: number) => void;
  onFineTune: (id: number) => void;
  onAddToAgent: (id: number) => void;
  /** Whether an agent is selected — gates the "Add to Agent" action. */
  canAddToAgent?: boolean;
  /** Selected agent name. When set on the locked baseline panel, the model
   *  selector gets a tooltip explaining why it's pinned. */
  agentName?: string | null;
  /** Hide the trash button (locked baseline in agent overlay, or only one panel). */
  hideRemove?: boolean;
  /** Compare-mode plumbing — page-level composer drives each panel's chat. */
  hideComposer?: boolean;
  broadcast?: { nonce: number; text: string };
  cancelNonce?: number;
  onRunningChange?: (id: number, isRunning: boolean) => void;
  /** Bubbles each completed turn's timing stats up with this panel's id. */
  onMetrics?: (id: number, info: AssistantMessageCompletion) => void;
}

export const ModelChatPanel: FC<ModelChatPanelProps> = ({
  panel,
  fallbackWorkspace,
  models,
  isLoadingModels,
  onToggle,
  onRemove,
  onModelChange,
  onSystemPromptChange,
  onParamsChange,
  onEvaluate,
  onFineTune,
  onAddToAgent,
  canAddToAgent = false,
  agentName,
  hideRemove,
  hideComposer,
  broadcast,
  cancelNonce,
  onRunningChange,
  onMetrics,
}) => {
  const workspaceGroups = useMemo(() => groupModelsByWorkspace(models, { sort: true }), [models]);
  const fineTunedGroups = useFineTunedGroup(models);
  // Fine-tuned models surface FIRST in the picker — they're the user's own
  // artifacts, more relevant than the auto-discovered base catalog below.
  const modelGroups = useMemo(
    () => [...fineTunedGroups, ...workspaceGroups],
    [fineTunedGroups, workspaceGroups]
  );

  const selectedModel: ModelSelection | null = panel.modelURN ? { model: panel.modelURN } : null;

  const handleModelChange = useCallback(
    (selection: ModelSelection) => {
      onModelChange(panel.id, selection.model);
    },
    [panel.id, onModelChange]
  );

  // Derive display label + inference identity from the URN so the chat path
  // uses the model's actual workspace, not a route fallback.
  const parts = panel.modelURN ? getPartsFromReference(panel.modelURN) : null;
  const modelName = parts?.name ?? null;
  const modelWorkspace = parts?.workspace || fallbackWorkspace;

  const handleInferenceParamsChange = useCallback(
    (params: Partial<InferenceParamsSliderValues>) => {
      onParamsChange(panel.id, { ...panel.params, ...params });
    },
    [onParamsChange, panel.id, panel.params]
  );

  const [systemOpen, setSystemOpen] = useState(false);

  const modelSelect = (
    <ModelSelectV2
      value={selectedModel}
      onValueChange={handleModelChange}
      groups={modelGroups}
      loading={isLoadingModels}
      placeholder={isLoadingModels ? 'Loading models…' : 'Select a model…'}
      hideAdapters
      fullWidth
      size="small"
      showParams
      triggerDisplay="urn"
      inferenceParams={panel.params}
      onInferenceParamsChange={handleInferenceParamsChange}
      disabled={panel.locked}
    />
  );

  // The baseline panel is pinned to the selected agent's model. Explain the
  // lock inline via a tooltip on the selector (replaces the old page banner).
  const lockedTooltip =
    panel.locked && agentName
      ? `Testing models for agent ${agentName}. Baseline is locked to ${panel.modelURN ?? '—'}.`
      : null;

  if (panel.collapsed) {
    return (
      <button
        onClick={() => onToggle(panel.id)}
        className="flex h-full shrink-0 cursor-pointer flex-col items-center gap-3 rounded-lg border border-base bg-surface-raised px-2 py-4 hover:bg-surface-sunken"
        aria-label={`Expand ${panel.roleLabel}`}
      >
        <span className={`mt-1 h-2 w-2 rounded-full ${PANEL_ROLE_DOT_CLASS[panel.roleColor]}`} />
        <span className="text-sm font-medium [writing-mode:vertical-rl]">{panel.roleLabel}</span>
      </button>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 min-w-[360px] flex-1 flex-col rounded-lg border border-base bg-surface-raised">
      {/* Header — unified for every panel: role label + per-panel actions. */}
      <div className="flex shrink-0 items-center gap-2 border-b border-base px-3 py-2">
        <span className={`h-2 w-2 rounded-full ${PANEL_ROLE_DOT_CLASS[panel.roleColor]}`} />
        <Text kind="label/semibold/md">{panel.roleLabel}</Text>
        <div className="ml-auto flex items-center gap-1">
          {!hideRemove && (
            <button
              onClick={() => onRemove(panel.id)}
              className="text-fg-subdued hover:text-fg-base cursor-pointer rounded p-1.5 hover:bg-surface-sunken"
              aria-label={`Remove ${panel.roleLabel}`}
            >
              <Trash2 size={16} />
            </button>
          )}
          <button
            onClick={() => onToggle(panel.id)}
            className="text-fg-subdued hover:text-fg-base cursor-pointer rounded p-1.5 hover:bg-surface-sunken"
            aria-label={`Collapse ${panel.roleLabel}`}
          >
            <Minimize2 size={16} />
          </button>
          <DropdownRoot>
            <DropdownTrigger asChild showChevron={false}>
              <button
                aria-label="Panel actions"
                className="text-fg-subdued hover:text-fg-base cursor-pointer rounded p-1.5 hover:bg-surface-sunken"
              >
                <EllipsisVertical size={16} />
              </button>
            </DropdownTrigger>
            <DropdownContent align="end">
              <DropdownItem disabled={!panel.modelURN} onClick={() => onFineTune(panel.id)}>
                Fine-tune
              </DropdownItem>
              <DropdownItem disabled={!panel.modelURN} onClick={() => onEvaluate(panel.id)}>
                Evaluate
              </DropdownItem>
              <Tooltip
                side="left"
                slotContent="Coming soon. Agent model swap is queued for the next release."
              >
                <DropdownItem disabled={!canAddToAgent} onClick={() => onAddToAgent(panel.id)}>
                  Create Agent
                </DropdownItem>
              </Tooltip>
            </DropdownContent>
          </DropdownRoot>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2 border-b border-base px-3 py-2">
        {lockedTooltip ? (
          <Tooltip side="bottom" slotContent={lockedTooltip}>
            <div className="min-w-0 flex-1">{modelSelect}</div>
          </Tooltip>
        ) : (
          <div className="min-w-0 flex-1">{modelSelect}</div>
        )}
      </div>

      {/* System prompt — collapsed by default. */}
      <div className="shrink-0">
        <button
          onClick={() => setSystemOpen((v) => !v)}
          className="text-fg-base hover:bg-surface-sunken flex w-full cursor-pointer items-center gap-2 px-4 py-3 text-sm"
        >
          <MessageSquare size={16} className="text-fg-subdued shrink-0" />
          <span className="font-medium">System prompt</span>
          <span className="ml-auto text-fg-subdued">
            {systemOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </span>
        </button>
        {systemOpen && (
          <div className="border-b border-base px-4 pb-4 pt-2">
            <TextArea
              value={panel.systemPrompt}
              onValueChange={(value) => onSystemPromptChange(panel.id, value ?? '')}
              rows={2}
              placeholder="Set the assistant's role and constraints…"
            />
          </div>
        )}
      </div>

      {/* Chat surface — panel extends to the bottom; floating composer clearance is on ModelChat. */}
      <div className="flex min-h-0 flex-1 flex-col px-4 pt-2 pb-2">
        {modelName ? (
          <ModelChat
            model={modelName}
            workspace={modelWorkspace}
            systemPrompt={panel.systemPrompt}
            params={panel.paramsTouched ? panel.params : undefined}
            hideComposer={hideComposer}
            broadcast={broadcast}
            cancelNonce={cancelNonce}
            onRunningChange={
              onRunningChange ? (running) => onRunningChange(panel.id, running) : undefined
            }
            onMetrics={onMetrics ? (info) => onMetrics(panel.id, info) : undefined}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-fg-subdued">
            Select a model to start chatting
          </div>
        )}
      </div>
    </div>
  );
};
