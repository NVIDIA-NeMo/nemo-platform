# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

UV ?= uv
CI_PROJECT_DIR ?= $(shell dirname $(shell dirname $(shell dirname $(shell pwd))))

.PHONY: help
help:
	@echo "Makefile commands:"
	@grep -E '^[0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: quickstart-up
up: quickstart-up

quickstart-up: ## Start the NeMo Platform with core services for local development
	cd $(CI_PROJECT_DIR) && \
	NMP_CONFIG_FILE_PATH=$(CI_PROJECT_DIR)/packages/nmp_platform/config/local.yaml \
	EXTRA_LOG_CONFIG='{loggers: {nmp.core.models.controllers.backends.docker: {level: DEBUG}}}' \
	DATABASE_DIALECT=sqlite \
	DATABASE_PATH=/tmp/nmp-platform.db \
	UVICORN_RELOAD=true \
	$(UV) run nemo services run \
	--services models,entities,jobs,secrets,files,auth,safe-synthesizer,inference-gateway \
	--controllers jobs,models \
	--host=0.0.0.0 \
	--port=8080

quickstart-clean: ## Clean the NeMo Platform DB
	rm -rf /tmp/nmp-platform.db

up-image: ## Start the NeMo Platform with core services for local development
	cd $(CI_PROJECT_DIR) && make docker/nmp-api && \
	uv run nemo quickstart up --image my-registry/nmp-api:local && \
	uv run nemo quickstart logs -f

create-hf-secret: ## Create the HF secret in the NeMo Platform
	cd $(CI_PROJECT_DIR) && \
	nemo secrets create --name "hf-token-secret" --data "env=HF_TOKEN"
