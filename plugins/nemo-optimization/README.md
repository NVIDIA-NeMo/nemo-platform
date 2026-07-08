# nemo-optimization-plugin

Customizer **Tune** lane: routes numeric hyperparameter optimization through
`OptimizeRouter` to backend plugins (`optuna`, `ga`).

Trial execution is delegated to the Evaluator (`AgentEvaluator` +
`FabricAgentRuntime`); this plugin owns the study loop, artifacts, and Jobs
results registration.

See `customizer-optuna-optimizer-implementation-strategy.md` for the full plan.
