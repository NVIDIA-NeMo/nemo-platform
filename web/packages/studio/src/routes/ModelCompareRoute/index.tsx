// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AssistantMessageCompletion } from '@nemo/common/src/components/AssistantChat/types';
import { getPartsFromReference, getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import {
  Button,
  Flex,
  PageHeader,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { AgentPicker } from '@studio/components/chat/AgentPicker';
import { computeWinners } from '@studio/components/chat/BestPerformingSummary';
import {
  PerformanceSummaryPanel,
  type PanelAverage,
} from '@studio/components/chat/PerformanceSummaryPanel';
import { ChatEmptyState } from '@studio/components/chat/ChatEmptyState';
import { CompareComposer } from '@studio/components/chat/CompareComposer';
import { DEFAULT_SEED_QUESTIONS } from '@studio/components/chat/defaultSeedQuestions';
import { DEFAULT_INFERENCE_PARAMS, type InferenceParams } from '@studio/components/chat/params';
import { RunEvaluationModal } from '@studio/components/chat/RunEvaluationModal';
import { useWorkspaceModels } from '@studio/components/chat/useWorkspaceModels';
import { ModelCompareChat } from '@studio/components/ModelCompareChat';
import { ModelComparePrompts } from '@studio/components/ModelComparePrompts';
import { ROUTES } from '@studio/constants/routes';
import { useSyncedHorizontalScroll } from '@studio/hooks/useSyncedHorizontalScroll';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import type { SharedModelEntry } from '@studio/routes/ModelCompareRoute/types';
import { useAgentContext } from '@studio/routes/ModelCompareRoute/useAgentContext';
import { type FC, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { generatePath, useNavigate, useSearchParams } from 'react-router-dom';

type CompareView = 'compare' | 'prompts';

const MAX_MODELS = 4;
const DEFAULT_SYSTEM_PROMPT = 'You are a helpful assistant.';

/**
 * Maps an agent's configured model onto a URN that exists in the workspace
 * picker. The agent config stores a bare `model_name` under an arbitrary
 * workspace, which won't always equal the platform model entity's
 * `workspace/name` URN the dropdown matches on. We try an exact URN match
 * first, then fall back to the (adapter-stripped) model name so the Baseline
 * panel reliably shows the agent's model as selected instead of an empty
 * placeholder. Falls back to the original URN when no entity matches.
 */
const resolveAgentModelUrn = (currentModelUrn: string, availableModels: ModelEntity[]): string => {
  const exact = availableModels.find((m) => getURNFromNamedEntityRef(m) === currentModelUrn);
  if (exact) return currentModelUrn;
  const { name: targetName } = getPartsFromReference(currentModelUrn);
  const targetBase = targetName.split('@')[0];
  const byName = availableModels.find((m) => {
    const name = m.name ?? '';
    return name === targetName || name.split('@')[0] === targetBase;
  });
  return (byName && getURNFromNamedEntityRef(byName)) || currentModelUrn;
};

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

  const [activeView, setActiveView] = useState<CompareView>('compare');

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
    // Defer seeding until the workspace models resolve so we can map the
    // agent's configured model onto the picker's actual `workspace/name` URN.
    // Seeding too early would set a URN the dropdown can't match, leaving the
    // locked Baseline panel stuck on the empty "Select a model…" placeholder.
    if (isLoadingModels) return;
    seededAgentRef.current = agentContext.name;
    const seedPrompt = agentContext.systemPrompt || DEFAULT_SYSTEM_PROMPT;
    const baselineUrn = resolveAgentModelUrn(agentContext.currentModelUrn, availableModels);
    setModels((prev) =>
      prev.map((m, i) => {
        if (i === 0) {
          return {
            ...m,
            modelURN: baselineUrn,
            systemPrompt: seedPrompt,
            locked: true,
          };
        }
        return { ...m, systemPrompt: seedPrompt };
      })
    );
  }, [agentContext, isLoadingModels, availableModels]);

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

  // Completed-turn timing history per panel, used for the "Best Performing +
  // Averages" panel. Accumulates across every turn in the session (not reset on
  // broadcast) so the panel reflects the multi-turn averages; cleared only on
  // reset, model removal, or a model swap.
  const [metricsById, setMetricsById] = useState<Map<number, AssistantMessageCompletion[]>>(
    () => new Map()
  );
  const [summaryExpanded, setSummaryExpanded] = useState(true);
  // Keep the chat-panel row and the performance-summary row scrolling together.
  const [chatScrollRef, summaryScrollRef] = useSyncedHorizontalScroll(2);

  const handleMetrics = useCallback((id: number, info: AssistantMessageCompletion) => {
    setMetricsById((prev) => {
      const next = new Map(prev);
      next.set(id, [...(prev.get(id) ?? []), info]);
      return next;
    });
  }, []);

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
    setMetricsById((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Map(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const setModelRef = useCallback((id: number, modelURN: string | null) => {
    setModels((prev) => prev.map((m) => (m.id === id ? { ...m, modelURN } : m)));
    // A model swap invalidates this panel's prior timing.
    setMetricsById((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Map(prev);
      next.delete(id);
      return next;
    });
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
    setMetricsById(new Map());
  }, []);

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

  // "Create Agent" isn't wired up yet (the agents API has no model-swap endpoint
  // today). The menu item's tooltip already says it's coming in a future release,
  // so the click is intentionally a no-op — previously this surfaced an info toast
  // that was redundant with the tooltip.
  const addToAgent = useCallback(() => {}, []);

  const handleBroadcast = useCallback((text: string) => {
    setBroadcast((prev) => ({ nonce: (prev?.nonce ?? 0) + 1, text }));
    // Metrics accumulate across turns — don't clear here. The averages panel
    // aggregates every completed turn in the session.
  }, []);

  const handleStopAll = useCallback(() => {
    setCancelNonce((n) => n + 1);
  }, []);

  const atMaxModels = models.length >= MAX_MODELS;
  const anyModelSelected = models.some((m) => !!m.modelURN);
  const readyPanelCount = models.filter((m) => !!m.modelURN).length;

  // Per-panel averages across all completed turns. `tokensPerSec` is weighted
  // (sum tokens / sum seconds) rather than a mean-of-means so short turns don't
  // over-influence the rate. Null for panels with zero completed turns so the
  // panel can render an em-dash.
  const averagesById = useMemo(() => {
    const result: Record<number, PanelAverage> = {};
    models.forEach((m) => {
      const turns = metricsById.get(m.id) ?? [];
      if (turns.length === 0) {
        result[m.id] = null;
        return;
      }
      let totalMs = 0;
      let totalTokens = 0;
      turns.forEach((t) => {
        totalMs += t.totalMs;
        totalTokens += t.completionTokens;
      });
      const count = turns.length;
      result[m.id] = {
        totalMs: totalMs / count,
        completionTokens: totalTokens / count,
        tokensPerSec: totalMs > 0 ? totalTokens / (totalMs / 1000) : 0,
        count,
      };
    });
    return result;
  }, [models, metricsById]);

  const anyAverages = Object.values(averagesById).some((a) => a !== null);

  // Overall "Best Performing" winners across the session's averages. Null until
  // at least two panels have results, since a winner needs a comparison.
  const winners = useMemo(
    () =>
      computeWinners(
        models
          .map((m) => ({ id: m.id, avg: averagesById[m.id] }))
          .filter((e): e is { id: number; avg: NonNullable<PanelAverage> } => e.avg !== null)
          .map((e) => ({
            id: e.id,
            stats: {
              totalMs: e.avg.totalMs,
              tokensPerSec: e.avg.tokensPerSec,
              completionTokens: e.avg.completionTokens,
            },
          }))
      ),
    [models, averagesById]
  );

  const modelLabelById = useCallback(
    (id: number): string => {
      const m = models.find((mm) => mm.id === id);
      return m?.modelURN ? getPartsFromReference(m.modelURN).name : 'Model';
    },
    [models]
  );

  // Empty state when the workspace has zero models and we're not still loading.
  if (!isLoadingModels && availableModels.length === 0) {
    return <ChatEmptyState hasModels={false} />;
  }

  const showChatPanels = activeView === 'compare';

  return (
    <div className="flex h-full flex-col">
      {/* Row 1 — page title (left) + page actions (right). Uses the shared KUI
       *  PageHeader so the heading typography and placement match every other
       *  page. Actions live on this row so the tab underline below can span the
       *  full width. */}
      <div className="shrink-0 px-6 pt-6 pb-5">
        <PageHeader
          className="p-0"
          slotHeading="Playground"
          slotActions={
            <Flex align="center" gap="density-md" className="shrink-0">
              <AgentPicker workspace={workspace} value={agentNameFromUrl} onChange={setAgentName} />
              {anyModelSelected && (
                <Button kind="secondary" size="medium" onClick={openEvalForAll}>
                  Run Evaluation
                </Button>
              )}
            </Flex>
          }
        />
      </div>
      {/* Row 2 — sub-nav tabs. */}
      <Flex align="center" className="shrink-0 px-6 pb-2">
        <TabsRoot value={activeView} onValueChange={(value) => setActiveView(value as CompareView)}>
          <TabsList>
            <TabsTrigger value="compare">Compare</TabsTrigger>
            <TabsTrigger value="prompts">Run Prompts</TabsTrigger>
          </TabsList>
        </TabsRoot>
      </Flex>
      {/* Row 3 — loading/error state when the URL points at a missing agent.
       *  The agent picker lives in the page header actions (top-right); the
       *  resolved-agent context is now surfaced as a tooltip on the locked
       *  baseline model selector instead of a page banner. */}
      {agentNameFromUrl && !agentContext && (agentLoading || agentError) && (
        <div className="min-w-0 shrink-0 px-6 pb-3">
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
        </div>
      )}

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
          onAddToAgent={addToAgent}
          canAddToAgent={!!agentContext}
          agentName={agentContext?.name ?? null}
          onAddModel={addModel}
          canAddModel={!atMaxModels}
          hideComposer
          broadcast={broadcast ?? undefined}
          cancelNonce={cancelNonce}
          onRunningChange={handleRunningChange}
          onMetrics={handleMetrics}
          scrollRef={chatScrollRef}
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
          onSetParams={setParams}
          onAddModel={addModel}
          canAddModel={!atMaxModels}
          agentName={agentContext?.name ?? null}
        />
      </div>

      {activeView === 'compare' && anyAverages && (
        <div className="shrink-0 px-6 pt-3">
          <PerformanceSummaryPanel
            models={models}
            averagesById={averagesById}
            winners={winners}
            modelLabelById={modelLabelById}
            expanded={summaryExpanded}
            onToggleExpanded={() => setSummaryExpanded((v) => !v)}
            reserveTrailingSlot={!atMaxModels}
            scrollRef={summaryScrollRef}
          />
        </div>
      )}

      {activeView === 'compare' && (
        <div className="shrink-0 px-6 pt-6 pb-3">
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
