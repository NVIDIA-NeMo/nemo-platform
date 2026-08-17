# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

.PHONY: test

NMP_ROOT_PATH := $(shell dirname $(shell dirname $(shell pwd)))

# TODO: Uncomment this when we have a way to vendor the package into the sdk
# vendor: # Vendor the package into the sdk
# rm -r sdk/python/nemo-platform/src/nemo_platform/beta/evaluator/ || true
# cd ${NMP_ROOT_PATH} && uv run --frozen nemo-platform-sdk-tools vendor from-config nemo_evaluator_sdk
# cd ${NMP_ROOT_PATH} && uv run --frozen nemo-platform-sdk-tools post-generation update-license-headers

test: # Run nemo_evaluator_sdk tests
	uv run --frozen pytest tests

.PHONY: vendor

NMP_ROOT_PATH := $(shell dirname $(shell dirname $(shell pwd)))

vendor: # Vendor the package into the sdk
	rm -r sdk/python/nemo-platform/src/nemo_platform/beta/evaluator/ || true
	cd ${NMP_ROOT_PATH} && uv run --frozen nemo-platform-sdk-tools vendor from-config nemo_evaluator_sdk
	cd ${NMP_ROOT_PATH} && uv run --frozen nemo-platform-sdk-tools post-generation update-license-headers

