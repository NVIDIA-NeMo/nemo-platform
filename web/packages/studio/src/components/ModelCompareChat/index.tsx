// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { ModelChatPanel } from '@studio/components/ModelChatPanel';
import {
  PANEL_ROLE_COLORS,
  PANEL_ROLE_LABELS,
  type PanelState,
  type SharedModelEntry,
} from '@studio/routes/ModelCompareRoute/types';
import { type ReactNode, useCallback, useState, type FC } from 'react';

interface ModelCompareChatProps {
  /** Route workspace — used only as a fallback for panels without an assigned model. */
  workspace: string;
  availableModels: ModelEntity[];
  isLoadingModels: boolean;
  models: SharedModelEntry[];
  onRemoveModel: (id: number) => void;
  onSetModel: (id: number, modelURN: string | null) => void;
  /** Incremented to remount all chat panels (clears messages) without losing model selections. */
  chatResetCount?: number;
  /** Compare-mode plumbing — when set, hides per-panel composers and broadcasts. */
  hideComposer?: boolean;
  broadcast?: { seq: number; text: string };
  stopCount?: number;
  onRunningChange?: (id: number, isRunning: boolean) => void;
  /** Rendered right-aligned at the trailing end of each panel's seed-questions row. */
  composerToggle?: ReactNode;
  /** When triggerCount changes, pre-fills every panel's composer textarea with text. */
  composerSeed?: { triggerCount: number; text: string };
}

export const ModelCompareChat: FC<ModelCompareChatProps> = ({
  workspace,
  availableModels,
  isLoadingModels,
  models,
  onRemoveModel,
  onSetModel,
  chatResetCount,
  hideComposer,
  broadcast,
  stopCount,
  onRunningChange,
  composerToggle,
  composerSeed,
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
      roleColor,
      roleLabel: PANEL_ROLE_LABELS[roleColor],
      isSinglePanel,
      locked: !!m.locked,
    };
  });

  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto px-6 pt-2 pb-2">
        {panels.map((panel) => (
          <ModelChatPanel
            key={`${panel.id}-${chatResetCount ?? 0}`}
            panel={panel}
            fallbackWorkspace={workspace}
            models={availableModels}
            isLoadingModels={isLoadingModels}
            onToggle={togglePanel}
            onRemove={onRemoveModel}
            onModelChange={onSetModel}
            hideRemove={panel.locked || models.length <= 1}
            hideComposer={hideComposer}
            composerToggle={composerToggle}
            composerSeed={composerSeed}
            broadcast={broadcast}
            stopCount={stopCount}
            onRunningChange={onRunningChange}
          />
        ))}
      </div>
    </div>
  );
};
