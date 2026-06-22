// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  applySuggestion,
  archivePreviousRun,
  CONTENT_SAFETY_MODEL_RE,
  checkContentSafety,
  ensureEvalConfigFileset,
  fetchAgents,
  fetchEvalAverageScores,
  fetchModels,
  fetchPiiSample,
  isCanceledError,
  loadPreviousSuggestionsFromFileset,
  loadSnapshot,
  loadSuggestionsFromFileset,
  markSuggestionAppliedInFileset,
  SNAPSHOT_PATH,
  SUGGESTIONS_PATH,
  uploadToFileset,
  waitForDeployments,
  waitForEvalJob,
} from '@studio/routes/agents/AgentSuggestionsRoute/api';
import type {
  EvalUiState,
  OptimizationSuggestion,
  RunState,
  SnapshotShape,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';
import {
  analyze,
  evalFilesetForAgent,
  evalOutputFilesetFor,
  mergeWithApplied,
  serializeSuggestions,
  suggestionIdentity,
} from '@studio/routes/agents/AgentSuggestionsRoute/utils';
import { getAgentEvaluationDetailRoute } from '@studio/routes/utils';
import { toError } from '@studio/util/logger';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

const EMPTY_SUGGESTIONS: readonly OptimizationSuggestion[] = [];

/**
 * Patch the suggestion's ``apply`` array so the ``POST /jobs/evaluate`` step
 * uses the user-chosen fileset + config path instead of the per-agent
 * default. Returns a shallow-cloned suggestion with a rebuilt apply array
 * so the original (stored in JSONL state) is untouched.
 */
const withEvalConfigOverride = (
  suggestion: OptimizationSuggestion,
  override: { fileset: string; configPath: string }
): OptimizationSuggestion => {
  const apply = suggestion.apply;
  const steps = Array.isArray(apply) ? apply : apply ? [apply] : [];
  const patched = steps.map((step) => {
    if (step.method !== 'POST' || !/\/jobs\/evaluate/.test(step.path)) return step;
    const body = (step.body ?? {}) as { spec?: Record<string, unknown> };
    const spec = body.spec ?? {};
    return {
      ...step,
      body: {
        ...body,
        spec: {
          ...spec,
          eval_config: override.configPath,
          eval_config_fileset: override.fileset,
        },
      },
    };
  });
  return { ...suggestion, apply: patched };
};

/**
 * Pull the sibling agent name out of the suggestion's ``apply`` array by
 * walking it for the ``POST /jobs/evaluate`` step and reading
 * ``body.spec.agent``. Returns ``undefined`` when no eval step is present —
 * suggestions that don't kick off an evaluation simply have no eval-state
 * row. Workspace-prefixed refs (``workspace/name``) are stripped to the bare
 * name since the eval output fileset is named after the bare agent.
 */
const extractEvalAgentName = (suggestion: OptimizationSuggestion): string | undefined => {
  const apply = suggestion.apply;
  const steps = Array.isArray(apply) ? apply : apply ? [apply] : [];
  for (const step of steps) {
    if (step.method !== 'POST' || !/\/jobs\/evaluate/.test(step.path)) continue;
    const spec = (step.body as { spec?: { agent?: unknown } } | undefined)?.spec;
    const agent = spec?.agent;
    if (typeof agent !== 'string' || !agent) continue;
    return agent.includes('/') ? agent.split('/').pop() : agent;
  }
  return undefined;
};

const SUGGESTIONS_QUERY_KEY = (workspace: string) =>
  ['agent-optimizer', 'suggestions', workspace] as const;

const PREVIOUS_SUGGESTIONS_QUERY_KEY = (workspace: string) =>
  ['agent-optimizer', 'previous-suggestions', workspace] as const;

const INITIAL_RUN_STATE: RunState = { phase: 'idle', step: '', error: null };

export const useOptimizerSuggestions = (workspace: string) => {
  const queryClient = useQueryClient();
  const [runState, setRunState] = useState<RunState>(INITIAL_RUN_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const [applyingKeys, setApplyingKeys] = useState<Set<string>>(() => new Set());
  const [applyErrors, setApplyErrors] = useState<Map<string, string>>(() => new Map());
  const [evalStates, setEvalStates] = useState<Map<string, EvalUiState>>(() => new Map());
  // Serializes JSONL read-modify-write across run() and concurrent applies.
  const persistChainRef = useRef<Promise<void>>(Promise.resolve());
  // Aborted on workspace change / unmount so waitForDeployments doesn't
  // outlive the route.
  const applyControllersRef = useRef<Set<AbortController>>(new Set());

  useEffect(() => {
    setRunState(INITIAL_RUN_STATE);
    setApplyingKeys(new Set());
    setApplyErrors(new Map());
    setEvalStates(new Map());
    const controllers = applyControllersRef.current;
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
      for (const c of controllers) c.abort();
      controllers.clear();
    };
  }, [workspace]);

  const suggestionsQuery = useQuery({
    queryKey: SUGGESTIONS_QUERY_KEY(workspace),
    queryFn: ({ signal }) => loadSuggestionsFromFileset(workspace, signal),
    enabled: !!workspace,
    retry: false,
  });

  const previousSuggestionsQuery = useQuery({
    queryKey: PREVIOUS_SUGGESTIONS_QUERY_KEY(workspace),
    queryFn: ({ signal }) => loadPreviousSuggestionsFromFileset(workspace, signal),
    enabled: !!workspace,
    retry: false,
  });

  const run = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;
    const isCurrentRun = () => abortRef.current === controller && !signal.aborted;
    const setStepIfCurrent = (step: string) => {
      if (isCurrentRun()) setRunState((s) => ({ ...s, phase: 'running', step }));
    };

    setRunState({
      phase: 'running',
      step: 'Fetching agents, models, and telemetry sample…',
      error: null,
    });

    try {
      // prevSuggestions is reloaded inside the persist continuation so the
      // merge sees any apply that landed mid-run.
      const [agents, models, piiSampleText, prevSnapshot] = await Promise.all([
        fetchAgents(workspace, signal),
        fetchModels(workspace, signal),
        fetchPiiSample(workspace, signal),
        loadSnapshot(workspace, signal),
      ]);
      if (!isCurrentRun()) return;
      setStepIfCurrent(
        `Found ${agents.length} agent${agents.length === 1 ? '' : 's'}, ${models.length} models — checking content safety…`
      );

      const contentSafetyModel = models.find((m) => CONTENT_SAFETY_MODEL_RE.test(m.name));
      const contentSafetyRisk = contentSafetyModel
        ? await checkContentSafety(workspace, contentSafetyModel.name, piiSampleText, signal)
        : false;

      if (!isCurrentRun()) return;
      setStepIfCurrent('Analyzing…');
      const fresh = analyze({
        agents,
        models,
        piiSampleText,
        contentSafetyRisk,
        prevSnapshot,
        workspace,
      });
      if (!isCurrentRun()) return;
      setStepIfCurrent('Saving results…');

      const allModelNames = models.map((m) => m.name);
      const updatedAt = new Date().toISOString();
      const snapshot: SnapshotShape = {
        agents: Object.fromEntries(
          agents.map((agent) => [
            agent.name,
            { modelNames: allModelNames, agentNames: [agent.name], updatedAt },
          ])
        ),
      };

      const persistTask = persistChainRef.current.then(async () => {
        const prevSuggestions = await loadSuggestionsFromFileset(workspace, signal);
        const merged = mergeWithApplied(prevSuggestions, fresh);
        // Stash the current run as "previous" before overwriting so the UI
        // can render the previous-run stat card. 404 → no prior run, skip.
        await archivePreviousRun(workspace, signal);
        await Promise.all([
          uploadToFileset(workspace, SUGGESTIONS_PATH, serializeSuggestions(merged), signal),
          uploadToFileset(workspace, SNAPSHOT_PATH, JSON.stringify(snapshot), signal),
        ]);
        return { merged, prevSuggestions };
      });
      persistChainRef.current = persistTask.then(
        () => undefined,
        () => undefined
      );
      const { merged, prevSuggestions } = await persistTask;

      if (!isCurrentRun()) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY(workspace) }),
        queryClient.invalidateQueries({ queryKey: PREVIOUS_SUGGESTIONS_QUERY_KEY(workspace) }),
        queryClient.invalidateQueries({ queryKey: ['agent-optimizer', 'snapshot', workspace] }),
      ]);
      if (!isCurrentRun()) return;

      // "New" = identity wasn't on disk before this run. Old math
      // (merged - applied) counted every non-applied row whether or not the
      // prior run had already produced it.
      const prevIdentities = new Set(prevSuggestions.map(suggestionIdentity));
      const newCount = merged.filter((s) => !prevIdentities.has(suggestionIdentity(s))).length;
      setRunState({
        phase: 'done',
        step: `Done — ${merged.length} suggestion${merged.length === 1 ? '' : 's'} (${newCount} new)`,
        error: null,
      });
    } catch (err) {
      if (isCanceledError(err) || !isCurrentRun()) return;
      setRunState({
        phase: 'failed',
        step: '',
        error: toError(err),
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [workspace, queryClient]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunState(INITIAL_RUN_STATE);
  }, []);

  const apply = useCallback(
    async (
      suggestion: OptimizationSuggestion,
      opts?: { evalConfigOverride?: { fileset: string; configPath: string } }
    ) => {
      if (!suggestion.apply) return;
      const key = suggestionIdentity(suggestion);
      const override = opts?.evalConfigOverride ?? null;

      setApplyingKeys((prev) => {
        const next = new Set(prev);
        next.add(key);
        return next;
      });
      setApplyErrors((prev) => {
        if (!prev.has(key)) return prev;
        const next = new Map(prev);
        next.delete(key);
        return next;
      });

      const controller = new AbortController();
      applyControllersRef.current.add(controller);
      try {
        // Seed the eval fileset before running the apply array so the
        // ``POST /jobs/evaluate`` step in ``apply`` finds eval_config_fileset
        // / eval_config already populated. Skipped when:
        // - The suggestion has no agent (e.g. workspace-wide types).
        // - The user picked an existing fileset via the override — that
        //   fileset is assumed already populated; seeding the bundled
        //   default into it would clobber a user-curated config.
        if (!override && suggestion.type === 'model_optimization' && suggestion.agent) {
          await ensureEvalConfigFileset(
            workspace,
            evalFilesetForAgent(suggestion.agent),
            controller.signal
          );
        }

        // When the user picks a fileset, patch the eval step's spec so
        // the validated apply array points at their fileset + config
        // instead of the per-agent default.
        const targetSuggestion = override
          ? withEvalConfigOverride(suggestion, override)
          : suggestion;

        const { deploymentNames, evalJobNames } = await applySuggestion(
          targetSuggestion,
          workspace,
          controller.signal
        );

        // Persist applied state immediately — resources are created;
        // deployment readiness and eval results are separate signals tracked
        // independently below.
        const persistTask = persistChainRef.current.then(async () => {
          await markSuggestionAppliedInFileset(workspace, suggestion, controller.signal);
          await queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY(workspace) });
        });
        persistChainRef.current = persistTask.catch(() => undefined);
        await persistTask;

        // Seed the eval-state row up front so the tile renders "Queued" the
        // moment apply succeeds, before deployment readiness or eval polling
        // resolves. The sibling name comes from the apply array (the eval
        // step's body.spec.agent) — it's the agent the eval will run against.
        const siblingAgentName = extractEvalAgentName(suggestion);
        if (evalJobNames[0] && siblingAgentName) {
          const seededState: EvalUiState = {
            jobName: evalJobNames[0],
            siblingAgentName,
            status: 'queued',
            scores: [],
            detailHref: getAgentEvaluationDetailRoute(workspace, evalJobNames[0]),
          };
          setEvalStates((prev) => new Map(prev).set(key, seededState));
        }

        if (deploymentNames.length > 0) {
          try {
            await waitForDeployments(workspace, deploymentNames, { signal: controller.signal });
          } catch (waitErr) {
            if (isCanceledError(waitErr)) return;
            // Surface readiness failure but keep applied:true so the user
            // isn't prompted to retry the create.
            const message = waitErr instanceof Error ? waitErr.message : String(waitErr);
            setApplyErrors((prev) => new Map(prev).set(key, message));
          }
        }

        // Eval polling runs in parallel with deployment readiness — the eval
        // job is queued by the platform, not the frontend, so we don't gate
        // it on the deployment becoming ``running`` here. The job itself
        // hits the deployment via the agent gateway, which the platform
        // controller routes once the deployment is ready.
        if (evalJobNames[0] && siblingAgentName) {
          const jobName = evalJobNames[0];
          const outputFileset = evalOutputFilesetFor(siblingAgentName);
          try {
            await waitForEvalJob(workspace, jobName, {
              signal: controller.signal,
              onStatus: (status) => {
                setEvalStates((prev) => {
                  const existing = prev.get(key);
                  if (!existing) return prev;
                  return new Map(prev).set(key, { ...existing, status });
                });
              },
            });
            const scores = await fetchEvalAverageScores(
              workspace,
              outputFileset,
              controller.signal
            );
            setEvalStates((prev) => {
              const existing = prev.get(key);
              if (!existing) return prev;
              return new Map(prev).set(key, { ...existing, status: 'completed', scores });
            });
          } catch (evalErr) {
            if (isCanceledError(evalErr)) return;
            const message = evalErr instanceof Error ? evalErr.message : String(evalErr);
            setEvalStates((prev) => {
              const existing = prev.get(key);
              if (!existing) return prev;
              return new Map(prev).set(key, { ...existing, status: 'failed', error: message });
            });
          }
        }
      } catch (err) {
        if (isCanceledError(err)) return;
        const message = toError(err).message;
        setApplyErrors((prev) => new Map(prev).set(key, message));
      } finally {
        applyControllersRef.current.delete(controller);
        setApplyingKeys((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [workspace, queryClient]
  );

  const getApplyState = useCallback(
    (suggestion: OptimizationSuggestion) => {
      const key = suggestionIdentity(suggestion);
      return {
        isApplying: applyingKeys.has(key),
        isApplied: suggestion.applied === true,
        error: applyErrors.get(key) ?? null,
      };
    },
    [applyingKeys, applyErrors]
  );

  const getEvalState = useCallback(
    (suggestion: OptimizationSuggestion): EvalUiState | null => {
      return evalStates.get(suggestionIdentity(suggestion)) ?? null;
    },
    [evalStates]
  );

  return {
    suggestions: suggestionsQuery.data ?? EMPTY_SUGGESTIONS,
    previousSuggestions: previousSuggestionsQuery.data ?? EMPTY_SUGGESTIONS,
    isSuggestionsLoading: suggestionsQuery.isLoading,
    suggestionsLoadError: suggestionsQuery.error,
    refetchSuggestions: suggestionsQuery.refetch,
    ...runState,
    run,
    reset,
    apply,
    getApplyState,
    getEvalState,
  };
};
