// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { featureFlags } from '@studio/constants/featureFlags';
import {
  applySuggestion,
  archivePreviousRun,
  CONTENT_SAFETY_MODEL_RE,
  checkContentSafety,
  createAgent,
  createDeployment,
  ensureEvalConfigFileset,
  ensureOptimizeConfigFileset,
  fetchAgentConfig,
  fetchAgents,
  fetchEvalAverageScores,
  fetchModels,
  fetchPiiSample,
  fetchProfilerStats,
  fetchTunedParams,
  isCanceledError,
  loadPreviousSuggestionsFromFileset,
  loadSnapshot,
  loadSuggestionsFromFileset,
  markSuggestionAppliedInFileset,
  persistEvalRunInFileset,
  SNAPSHOT_PATH,
  submitEvalJob,
  submitOptimizeJob,
  SUGGESTIONS_PATH,
  uploadToFileset,
  waitForDeployments,
  waitForEvalJob,
  waitForOptimizeJob,
} from '@studio/routes/agents/AgentSuggestionsRoute/api';
import {
  OPTIMIZE_CONFIG_PATH,
  SAMPLE_EVAL_CONFIG_PATH,
} from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import type {
  EvalJobStatus,
  EvalRunResult,
  EvalUiState,
  OptimizationSuggestion,
  PersistedEvalRun,
  RunState,
  SnapshotShape,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';
import {
  analyze,
  buildTunedSiblingConfig,
  evalFilesetForAgent,
  evalOutputFilesetFor,
  isOrchestratedApplyType,
  mergeWithApplied,
  optimizeOutputFilesetFor,
  randomSiblingSuffix,
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

/**
 * Pull the eval-config fields out of the suggestion's ``POST /jobs/evaluate``
 * step so a baseline eval of the *original* agent can be submitted with the
 * identical dataset / judge config (apples-to-apples "before" vs "after").
 */
const extractEvalStepSpec = (
  suggestion: OptimizationSuggestion
): { eval_config?: string; eval_config_fileset?: string } | undefined => {
  const apply = suggestion.apply;
  const steps = Array.isArray(apply) ? apply : apply ? [apply] : [];
  for (const step of steps) {
    if (step.method !== 'POST' || !/\/jobs\/evaluate/.test(step.path)) continue;
    const spec = (step.body as { spec?: Record<string, unknown> } | undefined)?.spec;
    if (!spec) continue;
    return {
      eval_config: typeof spec.eval_config === 'string' ? spec.eval_config : undefined,
      eval_config_fileset:
        typeof spec.eval_config_fileset === 'string' ? spec.eval_config_fileset : undefined,
    };
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
  // Suggestion identities whose persisted ``eval_run`` has already been picked
  // up by the hydration effect, so re-renders / state patches don't re-poll.
  const hydratedKeysRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    setRunState(INITIAL_RUN_STATE);
    setApplyingKeys(new Set());
    setApplyErrors(new Map());
    setEvalStates(new Map());
    hydratedKeysRef.current = new Set();
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

  // Polls a suggestion's eval job(s) to completion and patches its eval-state
  // row (scores + profiler) as each settles. Assumes the row is already seeded
  // in ``evalStates`` (the caller sets the initial "queued" state). Shared by
  // the apply pipelines and the reload-hydration effect so all three paths poll
  // identically. Baseline ("before") polling runs only when a baseline job was
  // submitted. Never throws — per-side failures patch that side to ``failed``.
  const pollEvalRunIntoState = useCallback(
    async (
      key: string,
      run: {
        jobName: string;
        siblingAgentName: string;
        baselineJobName?: string;
        baselineAgent?: string;
      },
      signal: AbortSignal
    ): Promise<void> => {
      const patchEval = (fn: (s: EvalUiState) => EvalUiState) =>
        setEvalStates((prev) => {
          const existing = prev.get(key);
          if (!existing) return prev;
          return new Map(prev).set(key, fn(existing));
        });
      const patchBaseline = (fn: (b: EvalRunResult) => EvalRunResult) =>
        patchEval((s) => (s.baseline ? { ...s, baseline: fn(s.baseline) } : s));
      const collectRun = async (
        jobName: string,
        outputFileset: string,
        onStatus: (status: EvalJobStatus) => void
      ) => {
        await waitForEvalJob(workspace, jobName, { signal, onStatus });
        const [scores, profiler] = await Promise.all([
          fetchEvalAverageScores(workspace, outputFileset, signal),
          fetchProfilerStats(workspace, outputFileset, signal),
        ]);
        return { scores, profiler };
      };
      const tunedTask = (async () => {
        try {
          const { scores, profiler } = await collectRun(
            run.jobName,
            evalOutputFilesetFor(run.siblingAgentName),
            (status) => patchEval((s) => ({ ...s, status }))
          );
          patchEval((s) => ({ ...s, status: 'completed', scores, profiler }));
        } catch (evalErr) {
          if (isCanceledError(evalErr)) return;
          patchEval((s) => ({ ...s, status: 'failed', error: toError(evalErr).message }));
        }
      })();
      const baselineTask =
        run.baselineJobName && run.baselineAgent
          ? (async () => {
              try {
                const { scores, profiler } = await collectRun(
                  run.baselineJobName as string,
                  evalOutputFilesetFor(run.baselineAgent as string),
                  (status) => patchBaseline((b) => ({ ...b, status }))
                );
                patchBaseline((b) => ({ ...b, status: 'completed', scores, profiler }));
              } catch (evalErr) {
                if (isCanceledError(evalErr)) return;
                patchBaseline((b) => ({ ...b, status: 'failed', error: toError(evalErr).message }));
              }
            })()
          : Promise.resolve();
      await Promise.all([tunedTask, baselineTask]);
    },
    [workspace]
  );

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
      opts?: {
        evalConfigOverride?: { fileset: string; configPath: string };
        /** When set, the optimization already succeeded and deployed this
         *  sibling — re-run only the eval (skip the sweep + redeploy). Only
         *  honored by the orchestrated (hyperparameter-tuning) path. */
        evalOnlyRetry?: { siblingAgentName: string };
      }
    ) => {
      if (!suggestion.apply && !isOrchestratedApplyType(suggestion.type)) return;
      const key = suggestionIdentity(suggestion);
      const override = opts?.evalConfigOverride ?? null;
      const evalOnlyRetry = opts?.evalOnlyRetry ?? null;

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
        // Hyperparameter tuning has no static apply array — the tuned params
        // aren't known until the sweep runs. Orchestrate the whole pipeline
        // here (all via trusted customFetch helpers, not the JSONL allowlist):
        // run the real optimize job → read tuned temperature/top_p → deploy a
        // tuned sibling → eval it + the baseline → render before/after. Eval
        // state is keyed by this suggestion's identity so the tile shows it.
        if (isOrchestratedApplyType(suggestion.type) && suggestion.agent) {
          const originalAgent = suggestion.agent;
          const evalFileset = evalFilesetForAgent(originalAgent);

          // Eval config: the user-chosen fileset + path when they picked one,
          // otherwise the bundled sample in the per-agent eval fileset.
          const evalConfigPath = override?.configPath ?? SAMPLE_EVAL_CONFIG_PATH;
          const evalConfigFileset = override?.fileset ?? evalFileset;

          const patchState = (fn: (s: EvalUiState) => EvalUiState) =>
            setEvalStates((prev) => {
              const existing = prev.get(key);
              if (!existing) return prev;
              return new Map(prev).set(key, fn(existing));
            });

          // ``siblingName`` is either the freshly-deployed tuned copy (normal
          // run) or the one deployed by a prior successful sweep (eval-only
          // retry). In retry mode the sweep + deploy + applied-state persist are
          // skipped entirely — only the evals re-run below.
          let siblingName: string;
          let deploymentName: string | undefined;

          if (evalOnlyRetry) {
            siblingName = evalOnlyRetry.siblingAgentName;
          } else {
            const optimizeOut = optimizeOutputFilesetFor(originalAgent);

            await ensureOptimizeConfigFileset(workspace, evalFileset, controller.signal);
            const optimizeJobName = await submitOptimizeJob(
              workspace,
              {
                agent: originalAgent,
                optimize_config: OPTIMIZE_CONFIG_PATH,
                optimize_config_fileset: evalFileset,
                output: optimizeOut,
              },
              controller.signal
            );

            // "Running" tile state while the sweep executes.
            setEvalStates((prev) =>
              new Map(prev).set(key, {
                jobName: optimizeJobName,
                siblingAgentName: '',
                status: 'running',
                scores: [],
                profiler: null,
                detailHref: getAgentEvaluationDetailRoute(workspace, optimizeJobName),
                baseline: null,
              })
            );
            await waitForOptimizeJob(workspace, optimizeJobName, {
              signal: controller.signal,
              onStatus: (status) => patchState((s) => ({ ...s, status })),
            });

            const tuned = await fetchTunedParams(workspace, optimizeOut, controller.signal);
            if (!tuned) {
              throw new Error(
                'Optimization finished but produced no tuned params (optimized_config.yml missing from the output fileset).'
              );
            }

            // Build + deploy a tuned sibling from the original agent's config.
            const originalConfig = await fetchAgentConfig(
              workspace,
              originalAgent,
              controller.signal
            );
            siblingName = `${originalAgent}-tuned-${randomSiblingSuffix()}`;
            await createAgent(
              workspace,
              siblingName,
              buildTunedSiblingConfig(originalConfig, tuned),
              controller.signal
            );
            deploymentName = await createDeployment(workspace, siblingName, controller.signal);

            // Resources exist — persist applied state before the (slower) evals.
            const persistTask = persistChainRef.current.then(async () => {
              await markSuggestionAppliedInFileset(workspace, suggestion, controller.signal);
              await queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY(workspace) });
            });
            persistChainRef.current = persistTask.catch(() => undefined);
            await persistTask;
          }

          // Score tuned + baseline against the same eval config for before/after.
          // Seed the bundled sample only when the user did NOT override — an
          // override fileset is assumed already populated (don't clobber it).
          if (!override) {
            await ensureEvalConfigFileset(workspace, evalFileset, controller.signal);
          }
          const wantComparison = featureFlags.optimizerComparisonEnabled;
          const tunedEvalJob = await submitEvalJob(
            workspace,
            {
              agent: siblingName,
              eval_config: evalConfigPath,
              eval_config_fileset: evalConfigFileset,
              output: evalOutputFilesetFor(siblingName),
            },
            controller.signal
          );
          let baselineJobName: string | undefined;
          if (wantComparison) {
            try {
              baselineJobName = await submitEvalJob(
                workspace,
                {
                  agent: originalAgent,
                  eval_config: evalConfigPath,
                  eval_config_fileset: evalConfigFileset,
                  output: evalOutputFilesetFor(originalAgent),
                },
                controller.signal
              );
            } catch (err) {
              if (isCanceledError(err)) return;
            }
          }

          setEvalStates((prev) =>
            new Map(prev).set(key, {
              jobName: tunedEvalJob,
              siblingAgentName: siblingName,
              status: 'queued',
              scores: [],
              profiler: null,
              detailHref: getAgentEvaluationDetailRoute(workspace, tunedEvalJob),
              baseline: wantComparison
                ? {
                    agentName: originalAgent,
                    jobName: baselineJobName ?? '',
                    status: baselineJobName ? 'queued' : 'failed',
                    scores: [],
                    profiler: null,
                    error: baselineJobName ? undefined : 'Baseline eval could not be submitted.',
                  }
                : null,
            })
          );

          // Persist the eval-job pointers so the row re-hydrates + re-polls
          // after a reload/navigation — the jobs outlive this in-memory loop.
          // Mark hydrated so the refetch triggered here doesn't double-poll.
          hydratedKeysRef.current.add(key);
          const evalRun: PersistedEvalRun = {
            jobName: tunedEvalJob,
            siblingAgentName: siblingName,
            baseline: baselineJobName
              ? { agentName: originalAgent, jobName: baselineJobName }
              : null,
          };
          const evalRunPersist = persistChainRef.current.then(async () => {
            await persistEvalRunInFileset(workspace, suggestion, evalRun, controller.signal);
            await queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY(workspace) });
          });
          persistChainRef.current = evalRunPersist.catch(() => undefined);
          await evalRunPersist;

          if (deploymentName) {
            try {
              await waitForDeployments(workspace, [deploymentName], { signal: controller.signal });
            } catch (waitErr) {
              if (isCanceledError(waitErr)) return;
              setApplyErrors((prev) =>
                new Map(prev).set(key, waitErr instanceof Error ? waitErr.message : String(waitErr))
              );
            }
          }

          await pollEvalRunIntoState(
            key,
            {
              jobName: tunedEvalJob,
              siblingAgentName: siblingName,
              baselineJobName,
              baselineAgent: baselineJobName ? originalAgent : undefined,
            },
            controller.signal
          );
          return;
        }

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

        // The sibling name comes from the apply array (the eval step's
        // body.spec.agent) — it's the agent the optimized eval runs against.
        const siblingAgentName = extractEvalAgentName(suggestion);

        // When the comparison flag is on, also re-score the *original* agent
        // (a "before" baseline) with the identical dataset/judge config, so the
        // tile can render before/after side-by-side. Gated on there being an
        // optimized run to compare against. Best-effort: a baseline failure
        // never blocks the optimized ("after") run.
        const wantComparison =
          featureFlags.optimizerComparisonEnabled &&
          suggestion.type === 'model_optimization' &&
          !!suggestion.agent &&
          !!evalJobNames[0] &&
          !!siblingAgentName;
        const baselineFileset =
          wantComparison && suggestion.agent ? evalOutputFilesetFor(suggestion.agent) : undefined;
        let baselineJobName: string | undefined;
        let baselineError: string | undefined;
        if (wantComparison && suggestion.agent) {
          const sibSpec = extractEvalStepSpec(targetSuggestion);
          if (sibSpec?.eval_config && sibSpec?.eval_config_fileset) {
            try {
              baselineJobName = await submitEvalJob(
                workspace,
                {
                  agent: suggestion.agent,
                  eval_config: sibSpec.eval_config,
                  eval_config_fileset: sibSpec.eval_config_fileset,
                  output: baselineFileset as string,
                },
                controller.signal
              );
            } catch (err) {
              if (isCanceledError(err)) return;
              baselineError = toError(err).message;
            }
          } else {
            baselineError = 'Original agent has no eval config to re-score against.';
          }
        }

        // Seed the eval-state row up front so the tile renders "Queued" the
        // moment apply succeeds, before deployment readiness or eval polling
        // resolves.
        if (evalJobNames[0] && siblingAgentName) {
          const seededBaseline: EvalRunResult | null =
            wantComparison && suggestion.agent
              ? {
                  agentName: suggestion.agent,
                  jobName: baselineJobName ?? '',
                  status: baselineJobName ? 'queued' : 'failed',
                  scores: [],
                  profiler: null,
                  error: baselineJobName ? undefined : baselineError,
                }
              : null;
          const seededState: EvalUiState = {
            jobName: evalJobNames[0],
            siblingAgentName,
            status: 'queued',
            scores: [],
            profiler: null,
            detailHref: getAgentEvaluationDetailRoute(workspace, evalJobNames[0]),
            baseline: seededBaseline,
          };
          setEvalStates((prev) => new Map(prev).set(key, seededState));

          // Persist eval-job pointers so the row re-hydrates + re-polls after a
          // reload. Mark hydrated so the refetch below doesn't double-poll.
          hydratedKeysRef.current.add(key);
          const evalRun: PersistedEvalRun = {
            jobName: evalJobNames[0],
            siblingAgentName,
            baseline:
              baselineJobName && suggestion.agent
                ? { agentName: suggestion.agent, jobName: baselineJobName }
                : null,
          };
          const evalRunPersist = persistChainRef.current.then(async () => {
            await persistEvalRunInFileset(workspace, suggestion, evalRun, controller.signal);
            await queryClient.invalidateQueries({ queryKey: SUGGESTIONS_QUERY_KEY(workspace) });
          });
          persistChainRef.current = evalRunPersist.catch(() => undefined);
          await evalRunPersist;
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
        // job is queued by the platform, not the frontend, so we don't gate it
        // on the deployment becoming ``running`` here. The job hits the
        // deployment via the agent gateway once the controller routes it.
        if (evalJobNames[0] && siblingAgentName) {
          await pollEvalRunIntoState(
            key,
            {
              jobName: evalJobNames[0],
              siblingAgentName,
              baselineJobName: baselineFileset ? baselineJobName : undefined,
              baselineAgent: baselineFileset ? suggestion.agent : undefined,
            },
            controller.signal
          );
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
    [workspace, queryClient, pollEvalRunIntoState]
  );

  // Re-hydrate eval rows from persisted ``eval_run`` pointers after a reload or
  // navigation (``evalStates`` is in-memory only). For each loaded suggestion
  // that carries an ``eval_run`` and isn't already tracked/being applied, seed
  // a "queued" row and re-poll the job(s) to completion. ``hydratedKeysRef``
  // makes this run once per identity; the controller is aborted on unmount /
  // workspace change via ``applyControllersRef``.
  useEffect(() => {
    const data = suggestionsQuery.data;
    if (!data) return;
    for (const suggestion of data) {
      const run = suggestion.eval_run;
      if (!run) continue;
      const key = suggestionIdentity(suggestion);
      if (hydratedKeysRef.current.has(key)) continue;
      if (applyingKeys.has(key) || evalStates.has(key)) continue;
      hydratedKeysRef.current.add(key);

      const controller = new AbortController();
      applyControllersRef.current.add(controller);
      const seededBaseline: EvalRunResult | null = run.baseline
        ? {
            agentName: run.baseline.agentName,
            jobName: run.baseline.jobName,
            status: 'queued',
            scores: [],
            profiler: null,
          }
        : null;
      setEvalStates((prev) =>
        prev.has(key)
          ? prev
          : new Map(prev).set(key, {
              jobName: run.jobName,
              siblingAgentName: run.siblingAgentName,
              status: 'queued',
              scores: [],
              profiler: null,
              detailHref: getAgentEvaluationDetailRoute(workspace, run.jobName),
              baseline: seededBaseline,
            })
      );
      void pollEvalRunIntoState(
        key,
        {
          jobName: run.jobName,
          siblingAgentName: run.siblingAgentName,
          baselineJobName: run.baseline?.jobName,
          baselineAgent: run.baseline?.agentName,
        },
        controller.signal
      ).finally(() => {
        applyControllersRef.current.delete(controller);
      });
    }
  }, [suggestionsQuery.data, applyingKeys, evalStates, workspace, pollEvalRunIntoState]);

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
