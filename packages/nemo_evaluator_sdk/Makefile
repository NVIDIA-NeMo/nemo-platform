.PHONY: test

NMP_ROOT_PATH := $(shell dirname $(shell dirname $(shell pwd)))

test: # Run nemo_evaluator_sdk tests
	uv run --frozen pytest tests
