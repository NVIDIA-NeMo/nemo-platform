-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

BEGIN;

ALTER TABLE evaluations
    DROP CONSTRAINT IF EXISTS evaluations_last_failure_category_check,
    DROP CONSTRAINT IF EXISTS evaluations_last_failure_category_ck;

UPDATE evaluations
SET last_failure_category = CASE
    WHEN last_failure_category = 'retryable_task' THEN 'infrastructure'
    WHEN last_failure_code IN (
        'runner_disappeared',
        'object_store_unavailable',
        'poll_timeout',
        'ConnectionError',
        'TimeoutError',
        'OSError',
        'KubernetesJobError',
        'SandboxExecutionError'
    ) THEN 'infrastructure'
    WHEN last_failure_code IN (
        'provider_unavailable',
        'provider_rate_limited',
        'provider_timeout',
        'RateLimitError',
        'APITimeoutError',
        'APIConnectionError',
        'ServiceUnavailableError'
    ) THEN 'provider'
    WHEN last_failure_code IN (
        'NonZeroAgentExitCodeError',
        'task_object_missing',
        'evaluation_already_terminal',
        'InvalidReference',
        'ValidationError',
        'ValueError'
    ) THEN 'task'
    ELSE 'unknown'
END
WHERE last_failure_category IN ('retryable_task', 'non_retryable');

ALTER TABLE evaluations
    ADD CONSTRAINT evaluations_last_failure_category_ck CHECK (
        last_failure_category IS NULL
        OR last_failure_category IN (
            'infrastructure',
            'provider',
            'task',
            'unknown',
            'retryable_task',
            'non_retryable'
        )
    );

-- Old application pods may keep writing the legacy values until the rolling
-- deployment completes. A later migration can convert those late writes and
-- narrow this transitional constraint after every writer uses the new values.
COMMIT;
