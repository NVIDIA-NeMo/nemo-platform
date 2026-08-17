#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


set -e

# Export environment variables
if [ -f "config/env.local" ]; then
	set -o allexport
	source config/env.local
	set +o allexport
fi
export DEBUG=true
env | grep NEMO || true

# Trap Ctrl-C and kill all background processes
trap 'echo "Stopping all processes..."; kill $(jobs -p); wait; exit' INT TERM

# Start the API server in the background
echo "Starting Inference Gateway API server..."
uv run --frozen python -m inference_gateway.entrypoint api &
API_PID=$!

# Wait for API to be healthy
echo "Waiting for API to be available on localhost:8080..."
wait_for_health() {
	local max_attempts=30
	local attempt=1

	while [ $attempt -le $max_attempts ]; do
		if curl -s -f http://localhost:8080 >/dev/null 2>&1; then
			echo "✅ API is healthy and ready!"
			return 0
		fi

		echo "Attempt $attempt/$max_attempts: API not ready yet, waiting 2 seconds..."
		sleep 2
		attempt=$((attempt + 1))
	done

	echo "❌ API failed to become healthy after $max_attempts attempts"
	echo "Killing API process..."
	kill $API_PID 2>/dev/null || true
	exit 1
}

wait_for_health

echo "Inference Gateway API service is running. Press Ctrl-C to stop."
echo "API Server PID: $API_PID"

# Wait for all background processes
wait
