.PHONY: build demo experiment experiment-plan experiment-suite lint score test typecheck

EXPERIMENT_NAME ?= baseline
EXPERIMENT_MODEL ?= claude-sonnet-5
EXPERIMENT_TASKS ?=
EXPERIMENT_TRIALS ?= 3
O11Y_BENCH_REPO ?= ../o11y-bench
EXPERIMENT_ARGS = --name "$(EXPERIMENT_NAME)" --model "$(EXPERIMENT_MODEL)" --trials "$(EXPERIMENT_TRIALS)" --bench-repo "$(O11Y_BENCH_REPO)" $(foreach task,$(EXPERIMENT_TASKS),--task "$(task)")

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
