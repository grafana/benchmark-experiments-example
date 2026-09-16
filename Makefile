.PHONY: build demo lint score test typecheck

build:
	mkdir -p bin
	go build -o bin/watcherbench ./cmd/watcherbench

demo:
	go run ./cmd/watcherbench demo

score:
	go run ./cmd/watcherbench score --file bench/sample-results.json

test:
	go test ./...

lint:
	go vet ./...

typecheck:
	go test ./...
