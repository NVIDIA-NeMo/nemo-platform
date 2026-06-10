// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AssistantMessageCompletion } from '@nemo/common/src/components/AssistantChat/types';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { Button } from '@nvidia/foundations-react-core';
import type { InferenceParams } from '@studio/components/chat/params';
import { ModelChatPanel } from '@studio/components/ModelChatPanel';
import {
  PANEL_ROLE_COLORS,
  PANEL_ROLE_LABELS,
  type PanelState,
  type SharedModelEntry,
} from '@studio/routes/ModelCompareRoute/types';
import { Plus } from 'lucide-react';
import { useCallback, useState, type FC } from 'react';

interface ModelCompareChatProps {
  /** Route workspace — used only as a fallback for panels without an assigned model. */
  workspace: string;
  availableModels: ModelEntity[];
  isLoadingModels: boolean;
  models: SharedModelEntry[];
  onRemoveModel: (id: number) => void;
  onSetModel: (id: number, modelURN: string | null) => void;
  onSetSystemPrompt: (id: number, value: string) => void;
  onSetParams: (id: number, params: InferenceParams) => void;
  onEvaluate: (id: number) => void;
  onFineTune: (id: number) => void;
  /** Per-panel "Add to Agent" action (queues a model swap on the selected agent). */
  onAddToAgent: (id: number) => void;
  /** Whether an agent is selected — gates the per-panel "Add to Agent" action. */
  canAddToAgent?: boolean;
  /** Selected agent name — drives the locked baseline panel's lock tooltip. */
  agentName?: string | null;
  /** Adds another comparison panel when the user clicks the trailing + control. */
  onAddModel?: () => void;
  /** When false, hides the trailing + control (e.g. at the max panel count). */
  canAddModel?: boolean;
  /** Compare-mode plumbing — when set, hides per-panel composers and broadcasts. */
  hideComposer?: boolean;
  broadcast?: { nonce: number; text: string };
  cancelNonce?: number;
  onRunningChange?: (id: number, isRunning: boolean) => void;
  /** Bubbles each panel's completed-turn timing stats up to the route. */
  onMetrics?: (id: number, info: AssistantMessageCompletion) => void;
  /** Callback ref for the horizontal scroll row, used to sync scroll with the
   *  performance-summary row below so the columns track together. */
  scrollRef?: (el: HTMLElement | null) => void;
}

export const ModelCompareChat: FC<ModelCompareChatProps> = ({
  workspace,
  availableModels,
  isLoadingModels,
  models,
  onRemoveModel,
  onSetModel,
  onSetSystemPrompt,
  onSetParams,
  onEvaluate,
  onFineTune,
  onAddToAgent,
  canAddToAgent = false,
  agentName,
  onAddModel,
  canAddModel = false,
  hideComposer,
  broadcast,
  cancelNonce,
  onRunningChange,
  onMetrics,
  scrollRef,
}) => {
  // Per-panel UI state that's view-local (doesn't cross over to Prompts)
  const [collapsedIds, setCollapsedIds] = useState<Set<number>>(new Set());

  const togglePanel = useCallback((id: number) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const isSinglePanel = models.length === 1;

  // Compose PanelState per-render from shared entry + per-view ephemeral state
  // + position-derived role.
  const panels: PanelState[] = models.map((m, idx) => {
    const roleColor = PANEL_ROLE_COLORS[Math.min(idx, PANEL_ROLE_COLORS.length - 1)];
    return {
      id: m.id,
      collapsed: collapsedIds.has(m.id),
      modelURN: m.modelURN,
      systemPrompt: m.systemPrompt,
      params: m.params,
      paramsTouched: m.paramsTouched,
      roleColor,
      roleLabel: PANEL_ROLE_LABELS[roleColor],
      isSinglePanel,
      locked: !!m.locked,
    };
  });

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex min-h-0 flex-1 gap-3 overflow-x-auto px-6 pt-2 pb-2">
        {panels.map((panel) => (
          <ModelChatPanel
            key={panel.id}
            panel={panel}
            fallbackWorkspace={workspace}
            models={availableModels}
            isLoadingModels={isLoadingModels}
            onToggle={togglePanel}
            onRemove={onRemoveModel}
            onModelChange={onSetModel}
            onSystemPromptChange={onSetSystemPrompt}
            onParamsChange={onSetParams}
            onEvaluate={onEvaluate}
            onFineTune={onFineTune}
            onAddToAgent={onAddToAgent}
            canAddToAgent={canAddToAgent}
            agentName={agentName}
            hideRemove={panel.locked || models.length <= 1}
            hideComposer={hideComposer}
            broadcast={broadcast}
            cancelNonce={cancelNonce}
            onRunningChange={onRunningChange}
            onMetrics={onMetrics}
          />
        ))}
        {canAddModel && onAddModel && (
          <Button
            kind="secondary"
            size="small"
            aria-label="Add comparison panel"
            title="Add comparison panel"
            onClick={onAddModel}
            className="h-8 w-8 shrink-0 self-start !px-0 !border-[var(--border-color-interaction-base)] !bg-[var(--background-color-interaction-base)] hover:!border-[var(--border-color-interaction-hover)]"
          >
            <Plus size={16} />
          </Button>
        )}
      </div>
    </div>
  );
};
