// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { Button, TextArea } from '@nvidia/foundations-react-core';
import type { InferenceParams } from '@studio/components/chat/params';
import { ParamsPopover } from '@studio/components/chat/ParamsPopover';
import { useFineTunedGroup } from '@studio/components/chat/useFineTunedGroup';
import { ModelChat } from '@studio/components/ModelChat';
import { PANEL_ROLE_DOT_CLASS, type PanelState } from '@studio/routes/ModelCompareRoute/types';
import { ChevronDown, ChevronUp, Minimize2, Sparkles, Target, Trash2 } from 'lucide-react';
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
  /** Per-panel CTAs surfaced in single-panel mode. */
  onEvaluate: (id: number) => void;
  onFineTune: (id: number) => void;
  /** Hide the trash button (locked baseline in agent overlay, or only one panel). */
  hideRemove?: boolean;
  /** Compare-mode plumbing — page-level composer drives each panel's chat. */
  hideComposer?: boolean;
  broadcast?: { nonce: number; text: string };
  cancelNonce?: number;
  onRunningChange?: (id: number, isRunning: boolean) => void;
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
  hideRemove,
  hideComposer,
  broadcast,
  cancelNonce,
  onRunningChange,
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

  const [systemOpen, setSystemOpen] = useState(false);

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
    <div className="relative flex h-full min-w-[360px] flex-1 flex-col rounded-lg border border-base bg-surface-raised">
      {/* Header — role label (compare mode) OR per-panel CTAs (single mode) */}
      {panel.isSinglePanel ? (
        <div className="flex shrink-0 items-center gap-2 border-b border-base px-3 py-2">
          <div className="flex flex-1 items-center gap-2">
            <div className="flex-1">
              <ModelSelectV2
                value={selectedModel}
                onValueChange={handleModelChange}
                groups={modelGroups}
                loading={isLoadingModels}
                placeholder={isLoadingModels ? 'Loading models…' : 'Select a model…'}
                hideAdapters
                fullWidth
                disabled={panel.locked}
              />
            </div>
            <ParamsPopover value={panel.params} onChange={(p) => onParamsChange(panel.id, p)} />
          </div>
          <Button
            kind="tertiary"
            color="brand"
            size="small"
            onClick={() => onEvaluate(panel.id)}
            disabled={!panel.modelURN}
          >
            <Target size={14} />
            Evaluate
          </Button>
          <Button
            kind="secondary"
            color="brand"
            size="small"
            onClick={() => onFineTune(panel.id)}
            disabled={!panel.modelURN}
          >
            <Sparkles size={14} />
            Fine-tune
          </Button>
        </div>
      ) : (
        <>
          <div className="flex shrink-0 items-center gap-2 border-b border-base px-3 py-2">
            <span className={`h-2 w-2 rounded-full ${PANEL_ROLE_DOT_CLASS[panel.roleColor]}`} />
            <span className="text-sm font-semibold">{panel.roleLabel}</span>
            <div className="ml-auto flex items-center gap-1">
              {panel.modelURN && (
                <button
                  onClick={() => onFineTune(panel.id)}
                  className="text-fg-subdued hover:text-fg-base cursor-pointer rounded p-1.5 hover:bg-surface-sunken"
                  aria-label="Fine-tune this model"
                  title="Fine-tune this model"
                >
                  <Sparkles size={16} />
                </button>
              )}
              <button
                onClick={() => onToggle(panel.id)}
                className="text-fg-subdued hover:text-fg-base cursor-pointer rounded p-1.5 hover:bg-surface-sunken"
                aria-label={`Collapse ${panel.roleLabel}`}
              >
                <Minimize2 size={16} />
              </button>
              {!hideRemove && (
                <button
                  onClick={() => onRemove(panel.id)}
                  className="text-fg-subdued hover:text-fg-base cursor-pointer rounded p-1.5 hover:bg-surface-sunken"
                  aria-label={`Remove ${panel.roleLabel}`}
                >
                  <Trash2 size={16} />
                </button>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 border-b border-base px-3 py-2">
            <div className="flex-1">
              <ModelSelectV2
                value={selectedModel}
                onValueChange={handleModelChange}
                groups={modelGroups}
                loading={isLoadingModels}
                placeholder={isLoadingModels ? 'Loading models…' : 'Select a model…'}
                hideAdapters
                fullWidth
                disabled={panel.locked}
              />
            </div>
            <ParamsPopover value={panel.params} onChange={(p) => onParamsChange(panel.id, p)} />
          </div>
        </>
      )}

      {/* System prompt — collapsed by default. Quiet single-line label;
       *  the panel border above is the only divider — no second border below. */}
      <div className="shrink-0">
        <button
          onClick={() => setSystemOpen((v) => !v)}
          className="text-fg-subdued hover:text-fg-base flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-sm"
        >
          {systemOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          System prompt
        </button>
        {systemOpen && (
          <div className="px-3 pb-3">
            <TextArea
              value={panel.systemPrompt}
              onValueChange={(value) => onSystemPromptChange(panel.id, value ?? '')}
              rows={2}
              placeholder="Set the assistant's role and constraints…"
            />
          </div>
        )}
      </div>

      {/* Chat surface */}
      <div className="flex min-h-0 flex-1 flex-col px-3 pb-3">
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
