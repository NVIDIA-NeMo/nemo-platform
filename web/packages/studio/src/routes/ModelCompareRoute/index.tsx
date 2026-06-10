// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useModelsFromDefaultAndWorkspace } from '@nemo/common/src/api/models/useModelsFromDefaultAndWorkspace';
import { ComposerMode } from '@nemo/common/src/components/AssistantChat';
import type { BroadcastSignal } from '@nemo/common/src/components/AssistantChat/types';
import {
  Button,
  Flex,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Tooltip,
} from '@nvidia/foundations-react-core';
import { ChatEmptyState } from '@studio/components/chat/ChatEmptyState';
import { CompareComposer } from '@studio/components/chat/CompareComposer';
import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import { ModelCompareChat } from '@studio/components/ModelCompareChat';
import { ModelComparePrompts } from '@studio/components/ModelComparePrompts';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import type { ComposerSeed, SharedModelEntry } from '@studio/routes/ModelCompareRoute/types';
import { MoveDown, MoveUp, Plus, RotateCcw } from 'lucide-react';
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
  const { groups: modelGroups, isFetching: isLoadingModels } = useModelsFromDefaultAndWorkspace({
    workspace,
  });
  const [searchParams] = useSearchParams();
  const [activeView, setActiveView] = useState<CompareView>('compare');
  const [perPanelInput, setPerPanelInput] = useState(false);
  const [promptsReady, setPromptsReady] = useState(false);

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

  const handleRunningChange = useCallback((id: number, running: boolean) => {
    setRunningById((prev) => {
      if (prev.get(id) === running) return prev;
      const next = new Map(prev);
      next.set(id, running);
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
  const addModelDisabled = atMaxModels || (activeView === 'prompts' && !promptsReady);
  const readyPanelCount = models.filter((m) => !!m.modelURN).length;

  // Empty state when the workspace has zero models and we're not still loading.
  if (!isLoadingModels && modelGroups.length === 0) {
    return <ChatEmptyState hasModels={false} />;
  }

  const showChatPanels = activeView !== 'prompts';

  return (
    <div className="flex h-full flex-col">
      {/* Row 1 — page title */}
      <div className="shrink-0 px-6 pt-4 pb-2">
        <h1 className="text-2xl font-semibold">Chat</h1>
      </div>
      {/* Row 2 — sub-nav tabs (left) + page actions (right). No row-level
       *  underline: each tab carries its own indicator only when active, so
       *  the header stays quiet until the user selects a tab. */}
      <div className="flex shrink-0 items-center justify-between overflow-hidden px-6 pb-2">
        <TabsRoot value={activeView} onValueChange={(value) => setActiveView(value as CompareView)}>
          {/* -ml-3 cancels the first TabsTrigger's internal 12px left padding
           *  so its label aligns precisely with the page title above. */}
          <TabsList className="-ml-3 !shadow-none [&_[data-state=active]]:border-b-[var(--color-brand)]">
            <TabsTrigger value="compare">Compare</TabsTrigger>
            <TabsTrigger value="prompts">Run Prompts</TabsTrigger>
          </TabsList>
        </TabsRoot>
        <Flex align="center" gap="density-md" className="shrink-0">
          <Button kind="secondary" size="small" onClick={addModel} disabled={addModelDisabled}>
            <Plus size={14} />
            Add Model
          </Button>
          <Button kind="tertiary" size="small" onClick={resetAll}>
            <RotateCcw size={14} />
            Reset
          </Button>
        </Flex>
      </div>
      <div className={`min-h-0 flex-1 overflow-hidden ${showChatPanels ? '' : 'hidden'}`}>
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
                  <MoveDown size={15} />
                </button>
              </Tooltip>
            ) : undefined
          }
          composerSeed={panelSeed ?? undefined}
          broadcast={!perPanelInput ? (broadcast ?? undefined) : undefined}
          stopCount={stopCount}
          onRunningChange={handleRunningChange}
        />
      </div>
      <div className={`min-h-0 flex-1 overflow-hidden ${activeView !== 'prompts' ? 'hidden' : ''}`}>
        <ModelComparePrompts
          workspace={workspace}
          modelGroups={modelGroups}
          isLoadingModels={isLoadingModels}
          models={models}
          onRemoveModel={removeModel}
          onSetModel={setModelRef}
          onReadyChange={setPromptsReady}
        />
      </div>

      {activeView === 'compare' && !perPanelInput && (
        <div className="shrink-0 px-6 pb-3">
          <CompareComposer
            isAnyRunning={isAnyRunning}
            readyPanelCount={readyPanelCount}
            totalPanelCount={models.length}
            onSubmit={handleBroadcast}
            onStop={handleStopAll}
            onResetAll={resetAll}
            seedQuestions={DEFAULT_SEED_QUESTIONS}
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
                  className="flex cursor-pointer items-center justify-center rounded p-1.5 text-fg-subdued transition-colors hover:bg-surface-sunken hover:text-fg-base"
                  aria-label="Per-panel input"
                >
                  <MoveUp size={15} />
                </button>
              </Tooltip>
            }
          />
        </div>
      )}
    </div>
  );
};
