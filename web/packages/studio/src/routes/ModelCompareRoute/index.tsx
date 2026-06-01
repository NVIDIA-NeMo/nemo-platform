// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  Button,
  Flex,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { AgentContextBanner } from '@studio/components/chat/AgentContextBanner';
import { AgentPicker } from '@studio/components/chat/AgentPicker';
import { ChatEmptyState } from '@studio/components/chat/ChatEmptyState';
import { CompareComposer } from '@studio/components/chat/CompareComposer';
import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import { DEFAULT_INFERENCE_PARAMS, type InferenceParams } from '@studio/components/chat/params';
import { RunEvaluationModal } from '@studio/components/chat/RunEvaluationModal';
import { useWorkspaceModels } from '@studio/components/chat/useWorkspaceModels';
import { ModelCompareChat } from '@studio/components/ModelCompareChat';
import { ModelComparePrompts } from '@studio/components/ModelComparePrompts';
import { ROUTES } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import type { SharedModelEntry } from '@studio/routes/ModelCompareRoute/types';
import { useAgentContext } from '@studio/routes/ModelCompareRoute/useAgentContext';
import { Check, Plus, RotateCcw, Target } from 'lucide-react';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { generatePath, useNavigate, useSearchParams } from 'react-router-dom';

type CompareView = 'chat' | 'compare' | 'prompts';

const MAX_MODELS = 4;
const DEFAULT_SYSTEM_PROMPT = 'You are a helpful assistant.';

const makeDefaultEntry = (
  id: number,
  systemPrompt: string = DEFAULT_SYSTEM_PROMPT,
  modelURN: string | null = null,
  locked = false
): SharedModelEntry => ({
  id,
  modelURN,
  systemPrompt,
  params: { ...DEFAULT_INFERENCE_PARAMS },
  paramsTouched: false,
  locked,
});

export const ModelCompareRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { models: availableModels, isLoading: isLoadingModels } = useWorkspaceModels(workspace);
  const toast = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const agentNameFromUrl = searchParams.get('agent');
  const {
    context: agentContext,
    isLoading: agentLoading,
    error: agentError,
  } = useAgentContext(workspace, agentNameFromUrl);

  const [activeView, setActiveView] = useState<CompareView>('chat');
  const [promptsReady, setPromptsReady] = useState(false);

  // Start with two empty, unlocked panels — even when `?agent=` is set. The
  // seeding effect below applies the lock + baseline once the agent fetch
  // resolves. Deferring the lock avoids a stuck "locked with no model" panel
  // if the fetch 404s or the agent config doesn't expose a recognizable LLM.
  const [models, setModels] = useState<SharedModelEntry[]>(() => [
    makeDefaultEntry(0),
    makeDefaultEntry(1),
  ]);
  const nextIdRef = useRef(2);

  // Track which agent (if any) we've already applied to the panels so the
  // seeding effect re-runs only when the URL agent actually changes — not on
  // every render or every refetch.
  const seededAgentRef = useRef<string | null>(null);

  useEffect(() => {
    // Agent cleared from URL → unlock panel 0 if we previously locked it for
    // an agent, and reset its model.
    if (!agentContext) {
      if (seededAgentRef.current !== null) {
        seededAgentRef.current = null;
        setModels((prev) =>
          prev.map((m, i) => (i === 0 && m.locked ? { ...m, modelURN: null, locked: false } : m))
        );
      }
      return;
    }
    if (seededAgentRef.current === agentContext.name) return;
    seededAgentRef.current = agentContext.name;
    const seedPrompt = agentContext.systemPrompt || DEFAULT_SYSTEM_PROMPT;
    setModels((prev) =>
      prev.map((m, i) => {
        if (i === 0) {
          return {
            ...m,
            modelURN: agentContext.currentModelUrn,
            systemPrompt: seedPrompt,
            locked: true,
          };
        }
        return { ...m, systemPrompt: seedPrompt };
      })
    );
  }, [agentContext]);

  const setAgentName = useCallback(
    (next: string | null) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          if (next) params.set('agent', next);
          else params.delete('agent');
          return params;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const [evalOpen, setEvalOpen] = useState(false);
  const [evalSeedModels, setEvalSeedModels] = useState<string[]>([]);

  // Compare-mode plumbing: broadcast carries the prompt to every panel via
  // nonce-keyed effect; cancelNonce flips to stop them all.
  const [broadcast, setBroadcast] = useState<{ nonce: number; text: string } | null>(null);
  const [cancelNonce, setCancelNonce] = useState(0);
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
      return [...prev, makeDefaultEntry(id, prev[0]?.systemPrompt ?? DEFAULT_SYSTEM_PROMPT)];
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

  const setSystemPrompt = useCallback((id: number, value: string) => {
    setModels((prev) => prev.map((m) => (m.id === id ? { ...m, systemPrompt: value } : m)));
  }, []);

  const setParams = useCallback((id: number, params: InferenceParams) => {
    setModels((prev) => prev.map((m) => (m.id === id ? { ...m, params, paramsTouched: true } : m)));
  }, []);

  const resetAll = useCallback(() => {
    setModels((prev) =>
      prev.map((m) => makeDefaultEntry(m.id, DEFAULT_SYSTEM_PROMPT, null, !!m.locked))
    );
    setBroadcast(null);
    setRunningById(new Map());
  }, []);

  // Auto-fall-back: leaving Compare mode when there's no longer enough panels
  // to compare. Keeps the SegmentedControl from showing a selected-but-hidden
  // item.
  useEffect(() => {
    if (activeView === 'compare' && models.length < 2) setActiveView('chat');
  }, [activeView, models.length]);

  const openEvalForAll = useCallback(() => {
    const urns = Array.from(new Set(models.map((m) => m.modelURN).filter((u): u is string => !!u)));
    setEvalSeedModels(urns);
    setEvalOpen(true);
  }, [models]);

  const openEvalForOne = useCallback(
    (id: number) => {
      const panel = models.find((m) => m.id === id);
      if (!panel?.modelURN) return;
      setEvalSeedModels([panel.modelURN]);
      setEvalOpen(true);
    },
    [models]
  );

  const openFineTune = useCallback(
    (id: number) => {
      const panel = models.find((m) => m.id === id);
      if (!panel?.modelURN) return;
      const target = generatePath(ROUTES.workspace.newCustomizationJob, { workspace });
      toast.success(`Opening Customizer — would preselect ${panel.modelURN} as the base model.`);
      navigate(target);
    },
    [models, navigate, toast, workspace]
  );

  const applyToAgent = useCallback(() => {
    if (!agentContext) return;
    const comparison = models[1];
    const candidate = comparison?.modelURN;
    if (!candidate) {
      toast.error('Select a model in Comparison 1 first');
      return;
    }
    // Honest UX: the agents API has no PATCH/PUT today, so we can't actually
    // swap the model. Surface the gap clearly instead of faking a success
    // toast — see Follow-up B in the staged-seahorse plan.
    toast.info(
      `Coming next — agent model swap is queued for the next release. (Planned diff: ${agentContext.currentModelUrn} → ${candidate})`
    );
  }, [agentContext, models, toast]);

  const handleBroadcast = useCallback((text: string) => {
    setBroadcast((prev) => ({ nonce: (prev?.nonce ?? 0) + 1, text }));
  }, []);

  const handleStopAll = useCallback(() => {
    setCancelNonce((n) => n + 1);
  }, []);

  const atMaxModels = models.length >= MAX_MODELS;
  const addModelDisabled = atMaxModels || (activeView === 'prompts' && !promptsReady);
  const showCompareItem = models.length >= 2;
  const inCompareMode = models.length >= 2;
  const anyModelSelected = models.some((m) => !!m.modelURN);
  const readyPanelCount = models.filter((m) => !!m.modelURN).length;

  // Empty state when the workspace has zero models and we're not still loading.
  if (!isLoadingModels && availableModels.length === 0) {
    return <ChatEmptyState hasModels={false} />;
  }

  const showChatPanels = activeView === 'chat' || activeView === 'compare';

  return (
    <div className="flex h-full flex-col">
      {/* Row 1 — page title */}
      <div className="shrink-0 px-6 pt-4 pb-2">
        <h1 className="text-2xl font-semibold">Chat</h1>
      </div>
      {/* Row 2 — sub-nav tabs (left) + page actions (right). No row-level
       *  underline: each tab carries its own indicator only when active, so
       *  the header stays quiet until the user selects a tab. */}
      <Flex align="center" justify="between" className="shrink-0 px-6 pb-2">
        <TabsRoot value={activeView} onValueChange={(value) => setActiveView(value as CompareView)}>
          {/* -ml-3 cancels the first TabsTrigger's internal 12px left padding
           *  so its label aligns precisely with the page title above. */}
          <TabsList className="-ml-3 !shadow-none [&_[data-state=active]]:border-b-[var(--color-brand)]">
            <TabsTrigger value="chat">Chat</TabsTrigger>
            {showCompareItem && <TabsTrigger value="compare">Compare</TabsTrigger>}
            <TabsTrigger value="prompts">Run Prompts</TabsTrigger>
          </TabsList>
        </TabsRoot>
        <Flex align="center" gap="density-md">
          {inCompareMode && (
            <Button
              kind="primary"
              color="brand"
              size="small"
              onClick={openEvalForAll}
              disabled={!anyModelSelected}
            >
              <Target size={14} />
              Run Evaluation
            </Button>
          )}
          {agentContext && (
            <Button kind="secondary" size="small" onClick={applyToAgent}>
              <Check size={14} />
              Apply to Agent
            </Button>
          )}
          <Button kind="secondary" size="small" onClick={addModel} disabled={addModelDisabled}>
            <Plus size={14} />
            Add Model
          </Button>
          <Button kind="tertiary" size="small" onClick={resetAll}>
            <RotateCcw size={14} />
            Reset
          </Button>
        </Flex>
      </Flex>
      {/* Row 3 — agent picker (left) + context banner (right, fills remaining
       *  width). Banner is the info chrome when an agent is selected, or a
       *  loading/error state when the URL points at a missing agent. */}
      <Flex align="center" gap="density-md" className="shrink-0 px-6 pb-3">
        <AgentPicker workspace={workspace} value={agentNameFromUrl} onChange={setAgentName} />
        <div className="min-w-0 flex-1">
          {agentContext && (
            <AgentContextBanner
              agentName={agentContext.name}
              baselineModelUrn={models[0]?.modelURN ?? null}
            />
          )}
          {agentNameFromUrl && !agentContext && (agentLoading || agentError) && (
            <div className="rounded-lg border border-base bg-surface-sunken px-3 py-2 text-sm">
              {agentLoading ? (
                <Text kind="body/regular/sm" color="secondary">
                  Loading agent &quot;{agentNameFromUrl}&quot;…
                </Text>
              ) : (
                <Text kind="body/regular/sm" className="text-fg-error">
                  Agent &quot;{agentNameFromUrl}&quot; not found in workspace &quot;{workspace}
                  &quot;. Falling back to plain Chat.
                </Text>
              )}
            </div>
          )}
        </div>
      </Flex>

      <div className={`min-h-0 flex-1 overflow-hidden ${showChatPanels ? '' : 'hidden'}`}>
        <ModelCompareChat
          workspace={workspace}
          availableModels={availableModels}
          isLoadingModels={isLoadingModels}
          models={models}
          onRemoveModel={removeModel}
          onSetModel={setModelRef}
          onSetSystemPrompt={setSystemPrompt}
          onSetParams={setParams}
          onEvaluate={openEvalForOne}
          onFineTune={openFineTune}
          hideComposer={activeView === 'compare'}
          broadcast={broadcast ?? undefined}
          cancelNonce={cancelNonce}
          onRunningChange={handleRunningChange}
        />
      </div>
      <div className={`min-h-0 flex-1 overflow-hidden ${activeView !== 'prompts' ? 'hidden' : ''}`}>
        <ModelComparePrompts
          workspace={workspace}
          availableModels={availableModels}
          isLoadingModels={isLoadingModels}
          models={models}
          onRemoveModel={removeModel}
          onSetModel={setModelRef}
          onReadyChange={setPromptsReady}
          agentName={agentContext?.name ?? null}
        />
      </div>

      {activeView === 'compare' && (
        <div className="shrink-0 px-6 py-3">
          <CompareComposer
            isAnyRunning={isAnyRunning}
            readyPanelCount={readyPanelCount}
            totalPanelCount={models.length}
            onSubmit={handleBroadcast}
            onStop={handleStopAll}
            onResetAll={resetAll}
            seedQuestions={DEFAULT_SEED_QUESTIONS}
          />
        </div>
      )}

      <RunEvaluationModal
        open={evalOpen}
        onClose={() => setEvalOpen(false)}
        workspace={workspace}
        modelUrns={evalSeedModels}
      />
    </div>
  );
};
