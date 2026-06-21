IMAGE   := birdnet-species
VERSION := 0.1.1
TAG     := $(IMAGE):$(VERSION)

.PHONY: help build test test-docker test-native audio clean

help: ## Show this help
	@grep -E '^[a-z][a-z_-]+:.*## ' $(MAKEFILE_LIST) | \
	  awk -F ':.*## ' '{printf "%-16s %s\n", $$1, $$2}'

build: ## Build Docker image
	docker build -t $(TAG) .

audio: ## Download test audio files (no-op, files are in git)
	@echo "Test audio files are committed to git — nothing to download."

test: build test-docker ## Build and run tests in Docker (default)

test-docker: ## Run test suite in Docker container
	bash tests/run-tests.sh --docker

test-native: ## Run test suite natively (requires venv)
	bash tests/run-tests.sh

manifest: ## Regenerate test audio manifest
	python3 tests/generate_manifest.py

clean: ## Remove Docker image and temp files
	docker rmi $(TAG) 2>/dev/null || true
	rm -f tests/audio/*.csv
