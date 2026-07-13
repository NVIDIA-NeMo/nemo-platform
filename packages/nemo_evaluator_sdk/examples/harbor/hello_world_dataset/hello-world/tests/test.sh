#!/bin/bash
# Self-contained verifier (no network/pip): pass iff /app/hello.txt says
# "Hello, world!". Harbor reads the reward from /logs/verifier/reward.txt.
mkdir -p /logs/verifier

if [ -f /app/hello.txt ] && [ "$(tr -d '\n' < /app/hello.txt)" = "Hello, world!" ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
