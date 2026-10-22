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

## Hosted Grafana MCP Server

The adapter uploads only the binary and the instruction file, so containers
have no saved OAuth login. To have the agent use Grafana's hosted MCP server,
run `login` once on the host. Then export a short-lived access token before
starting the job; the adapter forwards `MCP_ACCESS_TOKEN` into each trial
container:

```sh
# From this repository, once (re-run after 30 days):
go run ./cmd/watcherbench login --mcp-url "$MCP_URL"

# Before each job:
export MCP_ACCESS_TOKEN=$(go run ./cmd/watcherbench mcp-token --mcp-url "$MCP_URL" --min-valid=55m)
```

The hosted server issues tokens that last about an hour, so keep jobs under
that or re-mint the token between jobs. Only the access token reaches the
container; the refresh token stays on the host. The adapter forwards the token
only when the MCP URL it selects for a trial equals the host's `MCP_URL`, so
the token never goes to a task-provided MCP server. Without a forwarded token,
the agent connects to the MCP server without a token, which works for
servers that don't require OAuth.

## Demo Point

The adapter intentionally does very little. o11y-bench still owns task
materialization, the Grafana/Prometheus/Loki/Tempo stack, grading, and HTML
reports. The Go binary owns the agent loop through `grafana/ai-sdk`.
