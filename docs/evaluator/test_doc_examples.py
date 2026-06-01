#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test script for evaluator documentation examples.

Run with: uv run python docs/evaluator/test_doc_examples.py

FINDINGS:
=========

1. Job Evaluation (async) - WORKS
   - Use system metric URNs: "system/trajectory-evaluation"
   - Configure judge in metric_params for metrics that require it
   - Metric names use HYPHENS (not underscores): trajectory-evaluation

2. Live Evaluation (sync) - BUG IN SERVICE
   - The evaluate endpoint has a validation bug in the current service build
   - Returns "Unable to extract tag using discriminator 'type'" for all requests
   - Both inline metrics and MetricRef strings fail
   - This needs to be fixed in the service code

3. RAGAS Metrics - Use for tool_call_accuracy, topic_adherence, etc.
   - These are available as RAGAS metric types (not system metrics)
   - Support both live and job evaluation

WORKING JOB PATTERNS:
=====================

Trajectory Evaluation (system metric, judge required):
  spec:
    metric: "system/trajectory-evaluation"
    dataset:
      rows:
        - question: "..."
          generated_answer: "..."
          answer: "..."
          intermediate_steps: [NAT format]
    metric_params:
      judge:
        model:
          url: "https://nim.int.aire.nvidia.com/v1/chat/completions"
          name: "meta/llama-3.2-3b-instruct"
      trajectory_used_tools: "tool1,tool2"

RAGAS Tool Call Accuracy (no judge required):
  metric:
    type: "tool_call_accuracy"
  dataset:
    rows:
      - user_input: [multi-turn conversation with tool_calls]
        reference_tool_calls: [expected tool calls]
"""

import time

import httpx

BASE_URL = "http://localhost:8080"
WORKSPACE = "doc-test-workspace"


def setup_workspace():
    """Create workspace if it doesn't exist."""
    with httpx.Client() as client:
        try:
            response = client.post(f"{BASE_URL}/v2/workspaces", json={"name": WORKSPACE})
            if response.status_code in (200, 201):
                print(f"✓ Created workspace: {WORKSPACE}")
            elif response.status_code == 409:
                print(f"✓ Workspace exists: {WORKSPACE}")
        except Exception as e:
            print(f"✗ Error: {e}")


def test_trajectory_evaluation_job():
    """Test Trajectory Evaluation - Job (judge required)"""
    print("\n[TEST] Trajectory Evaluation - Job (system/trajectory-evaluation)")

    payload = {
        "spec": {
            "dataset": {
                "rows": [{
                    "question": "What is the weather?",
                    "generated_answer": "The weather is sunny.",
                    "answer": "The weather is sunny.",
                    "intermediate_steps": [
                        {
                            "payload": {
                                "event_type": "LLM_END",
                                "name": "test-model",
                                "data": {
                                    "input": "What is the weather?",
                                    "output": "Action: weather_tool\nAction Input: {}"
                                }
                            }
                        },
                        {
                            "payload": {
                                "event_type": "TOOL_END",
                                "name": "weather_tool",
                                "data": {
                                    "input": "{}",
                                    "output": "sunny"
                                }
                            }
                        }
                    ]
                }]
            },
            "metric": "system/trajectory-evaluation",
            "params": {"limit_samples": 1},
            "metric_params": {
                "judge": {
                    "model": {
                        "url": "https://nim.int.aire.nvidia.com/v1/chat/completions",
                        "name": "meta/llama-3.2-3b-instruct"
                    }
                },
                "trajectory_used_tools": "weather_tool"
            }
        }
    }

    with httpx.Client(timeout=300.0) as client:
        response = client.post(f"{BASE_URL}/v2/workspaces/{WORKSPACE}/evaluation/metrics/jobs", json=payload)
        if response.status_code not in (200, 201):
            print(f"  ✗ Create failed: {response.text[:200]}")
            return False

        job_name = response.json()["name"]
        print(f"  Job: {job_name}")

        for _ in range(30):
            status = client.get(f"{BASE_URL}/v2/workspaces/{WORKSPACE}/evaluation/metrics/jobs/{job_name}").json().get("status")
            print(f"  Status: {status}")
            if status in ("completed", "error", "cancelled"):
                break
            time.sleep(4)

        return status == "completed"


def main():
    print("=" * 60)
    print("Evaluator Documentation Test")
    print("=" * 60)

    setup_workspace()

    passed = 0
    failed = 0

    if test_trajectory_evaluation_job():
        print("  ✓ PASSED")
        passed += 1
    else:
        print("  ✗ FAILED")
        failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
