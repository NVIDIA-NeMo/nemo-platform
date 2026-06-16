// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { Text } from '@nvidia/foundations-react-core';
import { DEFAULT_INFERENCE_PARAMS, type InferenceParams } from '@studio/components/chat/params';
import { ParamsPopover } from '@studio/components/chat/ParamsPopover';
import { ModelChat } from '@studio/components/ModelChat';
import {
  PANEL_ROLE_DOT_CLASS,
  type PanelChatControls,
  type PanelState,
} from '@studio/routes/ModelCompareRoute/types';
import { Minimize2, Trash2 } from 'lucide-react';
import { useCallback, useState, type FC } from 'react';

interface ModelChatPanelProps extends PanelChatControls {
  panel: PanelState;
  /** Fallback workspace used only if a panel has no model assigned yet. */
  fallbackWorkspace: string;
  modelGroups: ModelWorkspaceGroup[];
  isLoadingModels: boolean;
  onToggle: (id: number) => void;
  onRemove: (id: number) => void;
  /** Receives the full URN ("workspace/name"), or null when cleared. */
  onModelChange: (id: number, modelURN: string | null) => void;
  /** Hide the trash button (locked baseline in agent overlay, or only one panel). */
  hideRemove?: boolean;
}

export const ModelChatPanel: FC<ModelChatPanelProps> = ({
  panel,
  fallbackWorkspace,
  modelGroups,
  isLoadingModels,
  onToggle,
  onRemove,
  onModelChange,
  hideRemove,
  composerMode,
  broadcast,
  stopCount,
  onRunningChange,
  onEmptyChange,
  slotComposerEnd,
  composerSeed,
  seedQuestions,
}) => {
  const selectedModel: ModelSelection | null = panel.modelURN ? { model: panel.modelURN } : null;
  const [inferenceParams, setInferenceParams] = useState<InferenceParams>(DEFAULT_INFERENCE_PARAMS);

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
    <div
      data-model-panel
      className="relative flex h-full min-w-[360px] flex-1 flex-col rounded-lg border border-base bg-surface-raised"
    >
      {/* Role label + panel actions — only in compare mode (multiple panels). */}
      {!panel.isSinglePanel && (
        <div className="flex shrink-0 items-center gap-2 border-b border-base px-3 py-2">
          <span className={`h-2 w-2 rounded-full ${PANEL_ROLE_DOT_CLASS[panel.roleColor]}`} />
          <Text kind="label/bold/md">{panel.roleLabel}</Text>
          <div className="ml-auto flex items-center gap-1">
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
      )}
      {/* Model picker + inference params — shared across single and compare modes. */}
      <div className="flex shrink-0 items-center gap-2 border-b border-base px-3 py-2">
        <div className="flex-1">
          <ModelSelectV2
            value={selectedModel}
            onValueChange={handleModelChange}
            groups={modelGroups}
            loading={isLoadingModels}
            hideAdapters
            fullWidth
            disabled={panel.locked}
          />
        </div>
        <ParamsPopover value={inferenceParams} onChange={setInferenceParams} />
      </div>

      {/* Chat surface */}
      <div className="flex min-h-0 flex-1 flex-col px-3 pb-1">
        <ModelChat
          // Remount (clears messages + metrics) when the selected model changes.
          key={panel.modelURN ?? 'none'}
          model={modelName ?? ''}
          workspace={modelWorkspace}
          disabled={!modelName}
          emptyState={!modelName ? { slotHeading: 'Select a model to start chatting' } : undefined}
          promptData={{ inference_params: inferenceParams }}
          composerMode={composerMode}
          slotComposerEnd={slotComposerEnd}
          composerSeed={composerSeed}
          seedQuestions={seedQuestions}
          broadcast={broadcast}
          stopCount={stopCount}
          onRunningChange={
            onRunningChange ? (running) => onRunningChange(panel.id, running) : undefined
          }
          onEmptyChange={onEmptyChange ? (empty) => onEmptyChange(panel.id, empty) : undefined}
        />
      </div>
    </div>
  );
};
