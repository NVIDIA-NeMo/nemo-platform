# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

NMP_ROOT_PATH := $(shell git rev-parse --show-toplevel)

.PHONY: benchmark
benchmark:
	cd $(NMP_ROOT_PATH) && uv run python packages/nemo_platform_ext/scripts/benchmark.py run

.PHONY: benchmark-list
benchmark-list:
	cd $(NMP_ROOT_PATH) && uv run python packages/nemo_platform_ext/scripts/benchmark.py list

.PHONY: benchmark-compare
benchmark-compare:
	cd $(NMP_ROOT_PATH) && uv run python packages/nemo_platform_ext/scripts/benchmark.py compare-baseline

.PHONY: test-unit
test-unit:
	uv run --frozen pytest tests/ -m unit

.PHONY: test-integration
test-integration:
	uv run --frozen pytest tests/ -m integration

.PHONY: vendor-only
vendor-only:
	@echo "📦 Vendoring nemo-platform-ext to nemo-platform SDK..."
	cd ${NMP_ROOT_PATH} && uv run --no-sync nemo-platform-sdk-tools vendor from-config nemo_platform_ext

.PHONY: vendor
vendor: vendor-only
	cd ${NMP_ROOT_PATH} && uv run --no-sync nemo-platform-sdk-tools post-generation update-license-headers
