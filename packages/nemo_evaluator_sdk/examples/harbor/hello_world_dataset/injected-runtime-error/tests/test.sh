#!/bin/bash
# Unreachable when the environment Dockerfile fails to build; kept so the task
# shape matches hello-world for Harbor discovery.
mkdir -p /logs/verifier

if [ -f /app/hello.txt ] && [ "$(tr -d '\n' < /app/hello.txt)" = "Hello, world!" ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
