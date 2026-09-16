# WatcherBench

Demo project for the proposed OSA Con 2026 talk:

> Who Watches the Watcher: Benchmarking AI Agents That Debug Your Dashboards

The project shows three concrete pieces:

- a Go observability agent built on `github.com/grafana/ai-sdk`
- typed tools for Prometheus, Loki, Tempo, and dashboard patch dry-runs
- an `o11y-bench` adapter so the same agent can be graded against a live Grafana stack

## Quick Start

Run the deterministic terminal demo:

```sh
make demo
```

Show the Pass^3 vs. Pass@3 difference:

```sh
make score
```

Run tests and linter:

```sh
make test
make lint
make typecheck
```

## Live Agent Mode

The live path uses Anthropic through Grafana's Go AI SDK:

```sh
ANTHROPIC_API_KEY=... go run ./cmd/watcherbench ask \
  --prompt "Investigate checkout latency and propose a dashboard fix." \
  --fixture-tools=true
```

For o11y-bench, build a Linux binary and use the Harbor adapter in
`bench/o11y-bench/agents/ai_sdk_bridge_agent.py`.

## Demo Narrative

The useful failure case is deliberate: the agent first sees a syntactically
valid mean-latency PromQL query. The fixture marks it as wrong evidence for a
p95 task, then the corrected `histogram_quantile` query returns the supporting
ground truth. That sets up the benchmark claim: fluent incident text is not
enough; the agent needs verifiable actions.

## Sources This Project Tracks

- `grafana/ai-sdk` for Go model calls, streaming, typed tools, and agent loops
- `grafana/o11y-bench` for real Grafana-stack benchmark tasks and reports
- Grafana's o11y-bench launch post for the Pass^3 vs. Pass@3 framing

