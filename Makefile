.PHONY: build demo experiment experiment-plan experiment-suite lint score test typecheck

EXPERIMENT_NAME ?= baseline
# Empty EXPERIMENT_MODEL / EXPERIMENT_SUITE_VERSION fall back to ANTHROPIC_MODEL /
# AGENTO11Y_SUITE_VERSION from the environment. As command-line flags they also
# override values that op run --env-file injects from .env.
EXPERIMENT_MODEL ?=
EXPERIMENT_SUITE_VERSION ?=
EXPERIMENT_TASKS ?=
# Blank EXPERIMENT_TRIALS falls back to the script default of 3. Pass it on the
# make command line to override .env under op run --env-file.
EXPERIMENT_TRIALS ?=
O11Y_BENCH_REPO ?= ../o11y-bench
EXPERIMENT_ARGS = --name "$(EXPERIMENT_NAME)" --bench-repo "$(O11Y_BENCH_REPO)" \
	$(if $(strip $(EXPERIMENT_TRIALS)),--trials "$(strip $(EXPERIMENT_TRIALS))") \
	$(if $(EXPERIMENT_MODEL),--model "$(EXPERIMENT_MODEL)") \
	$(if $(EXPERIMENT_SUITE_VERSION),--suite-version "$(EXPERIMENT_SUITE_VERSION)") \
	$(foreach task,$(EXPERIMENT_TASKS),--task "$(task)")

experiment:
	python3 bench/o11y-bench/experiments.py $(EXPERIMENT_ARGS)

experiment-plan:
	python3 bench/o11y-bench/experiments.py $(EXPERIMENT_ARGS) --dry-run

experiment-suite:
	python3 bench/o11y-bench/experiments.py $(EXPERIMENT_ARGS) --sync-suite

build:
	mkdir -p bin
	go build -o bin/watcherbench ./cmd/watcherbench

demo:
	go run ./cmd/watcherbench demo

score:
	go run ./cmd/watcherbench score --file bench/sample-results.json

test:
	go test ./...
	python3 -m unittest discover -s bench/o11y-bench -p 'test_*.py'

lint:
	go vet ./...

typecheck:
	go test ./...
