# o11y-bench Integration

This folder is the bridge from the Go `watcherbench` agent to
`grafana/o11y-bench`.

## Smoke Run

From this repository:

```sh
GOOS=linux GOARCH=arm64 go build -o dist/watcherbench-linux-arm64 ./cmd/watcherbench
```

Then from a local clone of `grafana/o11y-bench`:

```sh
export WATCHERBENCH_BINARY=/absolute/path/to/dist/watcherbench-linux-arm64
export ANTHROPIC_API_KEY=...
export PYTHONPATH=/absolute/path/to/this/repo/bench/o11y-bench
mise run bench:job -- \
  --model anthropic/claude-sonnet-4-6 \
  --task-name query-cpu-metrics \
  --n-concurrent 1 \
  --agent-import-path agents.ai_sdk_bridge_agent:AiSdkBridgeAgent
```

Use `GOARCH=amd64` instead when Docker is running x86_64 Linux containers.

## Demo Point

The adapter intentionally does very little. o11y-bench still owns task
materialization, the Grafana/Prometheus/Loki/Tempo stack, grading, and HTML
reports. The Go binary owns the agent loop through `grafana/ai-sdk`.
