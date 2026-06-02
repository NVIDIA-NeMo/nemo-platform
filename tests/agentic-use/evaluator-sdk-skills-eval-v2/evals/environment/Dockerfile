FROM nmp-agentic-base:latest

# Cleanup /app to prevent agent from cheating when evaluating with no skills available.
RUN rm -rf /app/tests/agentic-use/evaluator-sdk-skills-eval* && \
    rm -rf /app/tests/agentic-use/evaluator-plugin-skills-eval* && \
    rm -rf /app/skills/nemo-evaluator-plugin* && \
    rm -fr /app/plugins/nemo-evaluator/src/nemo_evaluator/skills && \
    rm -rf /app/packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-evaluator && \
    rm -rf /app/.agents/skills/nemo-evaluator*/SKILL.md
