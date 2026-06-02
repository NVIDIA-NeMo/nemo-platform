FROM nmp-agentic-base:latest

ENV NVIDIA_API_KEY=${NVIDIA_API_KEY}

# Cleanup /app to prevent agent from cheating when evaluating with no skills available.
RUN rm -rf /app/tests/agentic-use/evaluator-sdk-skills-eval && \
    rm -rf /app/tests/agentic-use/evaluator-plugin-skills-eval && \
    rm -rf /app/packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-evaluator && \
    rm -rf /app/tests/agentic-use/evaluator-sdk-skills-eval-out-of-box
    
