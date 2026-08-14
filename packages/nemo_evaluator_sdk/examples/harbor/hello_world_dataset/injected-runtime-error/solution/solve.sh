#!/bin/bash
# Intentional failure fixture: sleep past agent.timeout_sec (1s) so Harbor
# records an agent-timeout exception_info. Opt in via --inject-error-task.
echo "Intentional Harbor oracle solve.sh hang for exception propagation testing." >&2
sleep 10
