// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  BASIC_ALL_MODELS_DROPDOWN_FILTER,
  buildWorkspaceGroup,
  type ModelWorkspaceGroup,
  useAllModels,
} from '@nemo/common/src/api/models/useModels';
import { ComposerMode } from '@nemo/common/src/components/AssistantChat';
import type { BroadcastSignal } from '@nemo/common/src/components/AssistantChat/types';
import { PageHeader, Tabs, Tooltip } from '@nvidia/foundations-react-core';
import { ChatEmptyState } from '@studio/components/chat/ChatEmptyState';
import { CompareComposer } from '@studio/components/chat/CompareComposer';
import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import { ModelCompareChat } from '@studio/components/ModelCompareChat';
import { ModelComparePrompts } from '@studio/components/ModelComparePrompts';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import type { ComposerSeed, SharedModelEntry } from '@studio/routes/ModelCompareRoute/types';
import { MessageSquareShare, MessagesSquare } from 'lucide-react';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

type CompareView = 'compare' | 'prompts';

const MAX_MODELS = 4;

const makeDefaultEntry = (
  id: number,
  modelURN: string | null = null,
  locked = false
): SharedModelEntry => ({
  id,
  modelURN,
  locked,
});

export const ModelCompareRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { data, isFetching: isLoadingModels } = useAllModels({
    workspace: workspace ?? undefined,
    query: BASIC_ALL_MODELS_DROPDOWN_FILTER,
  });
  const modelGroups = useMemo((): ModelWorkspaceGroup[] => {
    if (!workspace) return [];
    const allModels = data?.pages.flatMap((p) => (Array.isArray(p.data) ? p.data : [])) ?? [];
    const available = allModels.filter(
      (m) => Array.isArray(m.model_providers) && m.model_providers.length > 0
    );
    return available.length > 0 ? [buildWorkspaceGroup(workspace, available)] : [];
  }, [data, workspace]);
  const [searchParams] = useSearchParams();
  const [activeView, setActiveView] = useState<CompareView>('compare');
  const [perPanelInput, setPerPanelInput] = useState(false);
  const [models, setModels] = useState<SharedModelEntry[]>(() => [
    makeDefaultEntry(0),
    makeDefaultEntry(1),
  ]);
  const nextIdRef = useRef(2);
  const didPreselectRef = useRef(false);

  // Preselect panel 0 from ?model= query param once models load.
  useEffect(() => {
    if (didPreselectRef.current || isLoadingModels || modelGroups.length === 0) return;
    const param = searchParams.get('model');
    if (!param) {
      didPreselectRef.current = true;
      return;
    }
    const match = modelGroups
      .flatMap((g) => g.models)
      .find((m) => `${m.workspace}/${m.name}` === param || m.name === param);
    if (match) {
      setModels((prev) =>
        prev.map((m, i) => (i === 0 ? { ...m, modelURN: `${match.workspace}/${match.name}` } : m))
      );
    }
    didPreselectRef.current = true;
  }, [isLoadingModels, modelGroups, searchParams]);

  // Seed transfer: broadcast→panels and panel→broadcast.
  const compareComposerDraftRef = useRef('');
  const [panelSeed, setPanelSeed] = useState<ComposerSeed | null>(null);
  const [composerSeed, setComposerSeed] = useState<ComposerSeed | null>(null);

  // Compare-mode plumbing: broadcast carries the prompt to every panel via
  // sequence-keyed effect; stopCount flips to stop them all.
  const [chatResetCount, setChatResetCount] = useState(0);
  const [broadcast, setBroadcast] = useState<BroadcastSignal | null>(null);
  const [stopCount, setStopCount] = useState(0);
  const [runningById, setRunningById] = useState<Map<number, boolean>>(() => new Map());
  const isAnyRunning = useMemo(() => Array.from(runningById.values()).some(Boolean), [runningById]);
  // Per-panel empty/non-empty state. Drives seed-chip visibility: the broadcast
  // composer only shows chips when every open panel is in its empty initial
  // state. Panels default to empty until they report otherwise.
  const [emptyById, setEmptyById] = useState<Map<number, boolean>>(() => new Map());
  const allPanelsEmpty = models.every((m) => emptyById.get(m.id) ?? true);

  const handleRunningChange = useCallback((id: number, running: boolean) => {
    setRunningById((prev) => {
      if (prev.get(id) === running) return prev;
      const next = new Map(prev);
      next.set(id, running);
      return next;
    });
  }, []);

  const handleEmptyChange = useCallback((id: number, empty: boolean) => {
    setEmptyById((prev) => {
      if (prev.get(id) === empty) return prev;
      const next = new Map(prev);
      next.set(id, empty);
      return next;
    });
  }, []);

  const addModel = useCallback(() => {
    setModels((prev) => {
      if (prev.length >= MAX_MODELS) return prev;
      const id = nextIdRef.current++;
      return [...prev, makeDefaultEntry(id)];
    });
  }, []);

  const removeModel = useCallback((id: number) => {
    setModels((prev) => prev.filter((m) => m.id !== id));
    setRunningById((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Map(prev);
      next.delete(id);
      return next;
    });
    setEmptyById((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Map(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const setModelRef = useCallback((id: number, modelURN: string | null) => {
    setModels((prev) => prev.map((m) => (m.id === id ? { ...m, modelURN } : m)));
  }, []);

  const resetAll = useCallback(() => {
    setStopCount((n) => n + 1); // cancel in-flight completions before remount
    setBroadcast(null);
    setRunningById(new Map());
    setChatResetCount((n) => n + 1);
  }, []);

  // TODO: re-add Run Evaluation button once the RunEvaluationModal flow is ready

  const handleBroadcast = useCallback((text: string) => {
    setBroadcast((prev) => ({ seq: (prev?.seq ?? 0) + 1, text }));
  }, []);

  const handleStopAll = useCallback(() => {
    setStopCount((n) => n + 1);
  }, []);

  const atMaxModels = models.length >= MAX_MODELS;
  const readyPanelCount = models.filter((m) => !!m.modelURN).length;

  // Empty state when the workspace has zero models and we're not still loading.
  if (!isLoadingModels && modelGroups.length === 0) {
    return <ChatEmptyState hasModels={false} />;
  }

  const showChatPanels = activeView !== 'prompts';

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 px-6 pt-6 pb-4">
        <PageHeader className="p-0 pb-4" slotHeading="Playground" />
        <Tabs
          className="min-w-0 overflow-visible"
          value={activeView}
          onValueChange={(value) => setActiveView(value as CompareView)}
          items={[
            { value: 'compare', children: 'Compare' },
            { value: 'prompts', children: 'Run Prompts' },
          ]}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        <div className={`h-full ${showChatPanels ? '' : 'hidden'}`}>
          <ModelCompareChat
            workspace={workspace}
            modelGroups={modelGroups}
            isLoadingModels={isLoadingModels}
            models={models}
            onRemoveModel={removeModel}
            onSetModel={setModelRef}
            chatResetCount={chatResetCount}
            composerMode={perPanelInput ? ComposerMode.PER_PANEL : ComposerMode.BROADCAST_ALL}
            slotComposerEnd={
              perPanelInput ? (
                <Tooltip slotContent="Shared input">
                  <button
                    onClick={(e) => {
                      const panel = (e.currentTarget as HTMLElement).closest('[data-model-panel]');
                      const textarea = panel?.querySelector<HTMLTextAreaElement>(
                        'textarea[aria-label="Task prompt"]'
                      );
                      const draft = textarea?.value ?? '';
                      if (draft) {
                        setComposerSeed((prev) => ({
                          triggerCount: (prev?.triggerCount ?? 0) + 1,
                          text: draft,
                        }));
                      }
                      setPerPanelInput(false);
                    }}
                    className="flex cursor-pointer items-center justify-center rounded p-1.5 text-fg-subdued transition-colors hover:bg-surface-sunken hover:text-fg-base"
                    aria-label="Shared input"
                  >
                    <MessageSquareShare size={15} />
                  </button>
                </Tooltip>
              ) : undefined
            }
            composerSeed={panelSeed ?? undefined}
            broadcast={!perPanelInput ? (broadcast ?? undefined) : undefined}
            stopCount={stopCount}
            onRunningChange={handleRunningChange}
            onEmptyChange={handleEmptyChange}
            onAddModel={!atMaxModels ? addModel : undefined}
            seedQuestions={DEFAULT_SEED_QUESTIONS}
            slotComposer={
              !perPanelInput ? (
                <CompareComposer
                  isAnyRunning={isAnyRunning}
                  readyPanelCount={readyPanelCount}
                  totalPanelCount={models.length}
                  onSubmit={handleBroadcast}
                  onStop={handleStopAll}
                  onResetAll={resetAll}
                  seedQuestions={allPanelsEmpty ? DEFAULT_SEED_QUESTIONS : []}
                  draftRef={compareComposerDraftRef}
                  seed={composerSeed ?? undefined}
                  slotSeedEnd={
                    <Tooltip slotContent="Per-panel input">
                      <button
                        onClick={() => {
                          const draft = compareComposerDraftRef.current;
                          if (draft) {
                            setPanelSeed((prev) => ({
                              triggerCount: (prev?.triggerCount ?? 0) + 1,
                              text: draft,
                            }));
                          }
                          setComposerSeed(null);
                          setPerPanelInput(true);
                        }}
                        className="flex cursor-pointer items-center justify-center rounded border border-base bg-surface-raised p-1.5 text-fg-subdued transition-colors hover:bg-surface-sunken hover:text-fg-base"
                        aria-label="Per-panel input"
                      >
                        <MessagesSquare size={15} />
                      </button>
                    </Tooltip>
                  }
                />
              ) : undefined
            }
          />
        </div>
        <div className={`h-full overflow-hidden ${activeView !== 'prompts' ? 'hidden' : ''}`}>
          <ModelComparePrompts
            workspace={workspace}
            modelGroups={modelGroups}
            isLoadingModels={isLoadingModels}
            models={models}
            onRemoveModel={removeModel}
            onSetModel={setModelRef}
            onAddModel={!atMaxModels ? addModel : undefined}
          />
        </div>
      </div>
    </div>
  );
};
