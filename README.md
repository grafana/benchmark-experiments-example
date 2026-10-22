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
  --fixture-tools=true --mcp-url=""
```

### Configuring secrets in `.env`

Copy `.env.example` to `.env` and fill it in. watcherbench reads only process
environment variables and does not load `.env` itself.

If your `.env` uses 1Password secret references (`op://<vault>/<item>/<field>`)
instead of literal values, run every command through
[`op run`](https://developer.1password.com/docs/cli/reference/commands/run/).
`op run` resolves the references and passes the real values to the process
only:

```sh
op run --env-file=.env -- go run ./cmd/watcherbench ask \
  --prompt "Investigate checkout latency and propose a dashboard fix." \
  --fixture-tools=true --mcp-url=""
```

Without `op run`, the process receives the literal `op://...` strings, and
authentication fails, for example with a 401 from Anthropic or Agent
Observability. This applies to every subcommand that reads `.env`, including
`login`, which needs `MCP_URL`. If `.env` holds plain values instead, export
them into your shell with `set -a; source .env; set +a`.

To give the agent Grafana's hosted MCP server, set `MCP_URL` to
`https://mcp.grafana.com/mcp/<your-stack>.grafana.net` and log in once. The
server only accepts user OAuth tokens (not service account tokens):

```sh
go run ./cmd/watcherbench login   # opens the browser consent page
```

`login` stores the token in your user config dir (`watcherbench/mcp-oauth.json`,
mode 0600); `ask` and `bench-agent` refresh it automatically. Re-run `login`
after 30 days or when switching stacks. Pass `--mcp-url=""` to run without MCP.

### Fixture tools vs. MCP tools

`--fixture-tools` picks where the agent's data comes from:

| | `--fixture-tools=true` (default for `ask`) | `--fixture-tools=false` (default for `bench-agent`) |
|---|---|---|
| Tools | Local `fixture_query_prometheus`, `fixture_query_loki`, `fixture_find_trace`, `fixture_patch_dashboard` | Whatever the MCP server at `MCP_URL` exposes |
| Data | Canned `FixtureBackend` data (the mean-vs-p95 demo scenario) | Your real Grafana stack |
| Runs | Your process, one SDK step per tool round trip | Anthropic's servers, inside a single streamed response |
| Speed | Seconds; same canned data every run | Minutes on an open-ended prompt (often 20+ MCP calls) |
| Limited by | `--max-steps` | The system prompt's tool budget and `--timeout` (default 10m) |
| Run with | `--mcp-url=""` | `watcherbench login` first |

```sh
# Deterministic demo, no Grafana stack needed
go run ./cmd/watcherbench ask --prompt "..." --fixture-tools=true --mcp-url=""

# Real investigation against your stack via the hosted MCP server
go run ./cmd/watcherbench ask --prompt "..." --fixture-tools=false --timeout=15m
```

Passing `--fixture-tools=true` with an `MCP_URL` gives the agent both tool
sets, and it can mix canned and real data in one answer. The fixture tools carry
a `fixture_` prefix because the AI SDK matches tools by name. If a local tool
shared a name with an MCP tool (the hosted server has `query_prometheus`), the
SDK would check the MCP calls against the local tool's schema. The API would
then reject the run with "`tool_use` ids were found without `tool_result`
blocks". Keep any new local tool names distinct from the MCP server's tools.

### Running `bench-agent`

`bench-agent` runs the same agent as `ask`, but fixture tools are off by
default. With `MCP_URL` set, it uses only the real MCP server. Log in once
first; the saved login only works for the exact `MCP_URL` it was created with.
Pass the task with `--prompt` or `--instruction <file>`.

With 1Password secret references in `.env`:

```sh
op run --env-file=.env -- go run ./cmd/watcherbench login

op run --env-file=.env -- go run ./cmd/watcherbench bench-agent \
  --prompt "Investigate checkout latency and propose a dashboard fix." \
  --timeout=15m
```

With plain values in `.env`:

```sh
set -a; source .env; set +a

go run ./cmd/watcherbench login

go run ./cmd/watcherbench bench-agent \
  --prompt "Investigate checkout latency and propose a dashboard fix." \
  --timeout=15m
```

Every call goes to the MCP server and runs on Anthropic's side, so
`--max-steps` has little effect here. The tool budget in the system prompt and
`--timeout` are what limit the run.

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
│   └── main.go                 wires flags/env into agent.RunConfig; subcommands: demo, score, ask, bench-agent, login
├── internal/
│   ├── agent/                  the agent itself
│   │   ├── config.go            RunConfig + validation (API key, model, prompt, MCP URL)
│   │   ├── model.go             model name normalization
│   │   ├── prompts.go           system prompt
│   │   ├── run.go               Run(): calls aisdk.GenerateText, wrapped in Agent Observability
│   │   │                        instrumentation (one generation per call, OTel traces/metrics)
│   │   └── tools.go             typed tool definitions (fixture_query_prometheus, fixture_query_loki,
│   │                            fixture_find_trace, fixture_patch_dashboard) bound to an o11y.Backend
│   ├── mcpauth/                OAuth 2.1 login for the hosted Grafana MCP server
│   │   ├── discover.go           RFC 9728/8414 metadata discovery from MCP_URL
│   │   ├── register.go           dynamic client registration (public client)
│   │   ├── login.go              browser + loopback redirect + PKCE code exchange
│   │   ├── store.go              credentials file (0600) in the user config dir
│   │   └── token.go              AccessToken(): load + refresh before each run
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

