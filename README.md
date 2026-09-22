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

## Project Layout

```
.
├── cmd/watcherbench/          CLI entrypoint
│   └── main.go                 wires flags/env into agent.RunConfig; subcommands: demo, score, ask, bench-agent
├── internal/
│   ├── agent/                  the agent itself
│   │   ├── config.go            RunConfig + validation (API key, model, prompt, MCP URL)
│   │   ├── model.go             model name normalization
│   │   ├── prompts.go           system prompt
│   │   ├── run.go               Run(): calls aisdk.GenerateText, wrapped in Agent Observability
│   │   │                        instrumentation (one generation per call, OTel traces/metrics)
│   │   └── tools.go             typed tool definitions (query_prometheus, query_loki, find_trace,
│   │                            patch_dashboard) bound to an o11y.Backend
│   ├── o11y/                   the observability domain model + tool implementations
│   │   ├── backend.go            Backend interface (QueryMetrics/QueryLogs/FindTrace/PatchDashboard)
│   │   ├── types.go              request/response types for each tool
│   │   ├── validate.go           PromQL/LogQL/dashboard-patch input validation
│   │   └── fixture.go            FixtureBackend: canned data for the demo (mean-vs-p95 failure case)
│   ├── bench/                   Pass^3 vs. Pass@3 scoring for trial result files
│   │   ├── score.go              scoring logic
│   │   └── format.go             table output for `make score`
│   ├── demo/                    deterministic terminal demo script (`make demo`)
│   │   └── script.go
│   └── telemetry/               process-wide OpenTelemetry setup
│       └── otel.go               builds the TracerProvider/MeterProvider from OTEL_EXPORTER_OTLP_*
│                                  env vars; the agento11y SDK's spans/metrics export through these
├── bench/
│   ├── sample-results.json      sample trial data for `make score`
│   └── o11y-bench/               Harbor-based benchmark harness for grading the agent against a
│       ├── README.md              real Grafana stack (separate from the Go fixture demo above)
│       ├── agents/                bridge agent that drives the Go binary from Python/Harbor
│       └── jobs/                  benchmark job definitions (e.g. watcherbench-smoke.yaml)
├── docs/
│   └── talk-outline.md          outline for the OSA Con 2026 talk this project supports
├── .env.example                 documents required env vars (Anthropic, MCP, Agent Observability, OTel)
├── Makefile                     build/demo/score/test/lint/typecheck targets
└── go.mod / go.sum              Go module definition
```

### Folder intentions

- **`cmd/watcherbench`** — the only binary in this repo. Thin: parses flags/env and delegates to
  `internal/agent`, `internal/bench`, or `internal/demo`. Keep business logic out of this package.
- **`internal/agent`** — the agent's control flow and its Anthropic-facing configuration. This is
  also where Agent Observability instrumentation lives (`run.go`), since it wraps the same call site
  that talks to the model.
- **`internal/o11y`** — the tool surface the agent calls into. `Backend` is the seam between "what
  the agent can ask for" and "where the answer actually comes from"; `FixtureBackend` is the only
  implementation today; a real Grafana-backed implementation would live here.
- **`internal/bench`** — pure scoring logic for benchmark trial results, decoupled from how those
  trials were produced.
- **`internal/demo`** — the deterministic, non-LLM terminal walkthrough used for the talk itself.
- **`internal/telemetry`** — the *how do our own metrics/traces get out of this process* concern.
  Deliberately separate from `internal/o11y`, which is the agent's tools for querying *someone else's*
  telemetry.
- **`bench/o11y-bench`** — a separate benchmarking harness (Python/Harbor) that exercises the built
  Go binary against a live Grafana stack; distinct from the in-repo `internal/bench` scorer.
- **`docs`** — talk material, not code documentation.

