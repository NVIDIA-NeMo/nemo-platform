#!/bin/bash
# Intentional failure fixture: sleep past agent.timeout_sec (1s) so Harbor
# records an agent-timeout exception_info
echo "Intentional Harbor oracle solve.sh hang for exception propagation testing." >&2
sleep 10
