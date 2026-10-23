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

## Agent Observability experiments

The experiment workflow uses the existing o11y-bench agent and its isolated
Docker stacks. Its original tasks and graders remain the source of truth.
The WatcherBench adapter above is a separate runner: its Anthropic-hosted MCP
execution cannot reach a task's private Docker MCP endpoint.

Install `uv`, keep a sibling `../o11y-bench` checkout with its Agent Observability
integration, and start Docker. The launcher installs that checkout's locked
dependencies, materializes its tasks under this project's ignored `tasks/`
directory, and writes Harbor results and HTML reports under `jobs/experiments/`.

Use the existing `.env` ingestion credentials and Grafana service-account token.
The service account needs access to the Agent Observability test-suite APIs.
`AGENTO11Y_GRAFANA_URL` selects the Cloud stack; if omitted, the launcher
derives it from the configured stack-in-path `MCP_URL`. The experiment agent
uses each task's Docker stack, independently of that Cloud MCP setting.

Preview commands without credentials, model calls, or Cloud writes:

```sh
make experiment-plan EXPERIMENT_NAME=baseline \
  EXPERIMENT_TASKS='promql-error-rate find-slow-traces'
```

Set `EXPERIMENT_TRIALS` in `.env` to a positive integer. It defaults to **3 for
demonstration purposes**. Publish the task definitions once, then run the
configured number of independent attempts for each selected task:

```sh
op run --env-file=.env -- make experiment-suite

op run --env-file=.env -- make experiment EXPERIMENT_NAME=baseline \
  EXPERIMENT_TASKS='promql-error-rate find-slow-traces'
```

Omit `EXPERIMENT_TASKS` to run every existing task. Task IDs are checked
against the checkout's `tasks-spec/` files before anything runs. Set
`O11Y_BENCH_REPO` for a different checkout and `EXPERIMENT_MODEL` for a
different model; it defaults to `ANTHROPIC_MODEL` from `.env`. Start with a
selected task before running the full suite.

`experiment-suite` needs only the stack URL and the Grafana service-account
token; it doesn't check the Anthropic key or ingestion credentials.
It synchronizes the task specs to the dedicated
`watcherbench-o11y-bench` Cloud test suite. `experiment` publishes graded trials
as they finish, reusing the published suite. `AGENTO11Y_SUITE_ID` overrides that suite;
synchronization updates its
cases to match the source dataset, including removing cases absent from source.
No production evaluation rules are created.

Use a new `EXPERIMENT_NAME` for each candidate you want to compare, for example
`baseline` and `candidate`. Reusing a name resumes the same job and experiment.
The runner refuses to resume if the model, selected tasks, agent code (Git SHA)
or suite version changed, and names what differs. The name is recorded only
once Harbor has started the job (under `jobs/experiment-inputs/`), so a run
that fails earlier, for example while syncing tasks, can be fixed and rerun
under the same name. Keep the task dataset and grader configuration fixed
between candidates for comparable results.

Pin both candidates to the published version printed by `experiment-suite`
by passing it to `make`, for example `EXPERIMENT_SUITE_VERSION=v1`. A shell
variable set before `op run` doesn't work: `op run --env-file` gives `.env`
values precedence. Without a pin, each run resolves `latest_published` to a
concrete version when it starts and records it, so a resume can't silently
switch to a newer suite version.

The runner prints a direct experiment URL. In your Cloud stack, open **Agent
Observability → Experiments**, select the runs to compare, and inspect their
repeated-trial results. A trial passes using the existing grader's full-pass
criterion (`reward == 1.0`, excluding timeouts). Numeric quality scores are
published separately from pass/fail.

For `k` completed attempts per task, **Pass@k** is the fraction of tasks with
at least one passing attempt; **Pass^k** is the fraction with all `k` attempts
passing. With the demonstration default of three, one pass out of three
contributes 100% to that task's Pass@3 and 0% to its Pass^3. Wait for all
configured trials before interpreting these metrics. Job and experiment IDs
include the count (`-k3`, `-k5`, etc.), and Cloud shows the experiment as, for
example, `baseline (k=3)`, keeping different trial counts separate.
The local `make demo` and `make score` tables use the same definitions over
their sample trials: quality scores don't affect either metric.

On ARM Docker hosts, if the existing runner exits with code 132 while importing
`cryptography`, set `OPENSSL_armcap=0` before `op run`. The launcher forwards
this OpenSSL CPU-capability override into the agent container; it disables the
hardware path that crashes on affected hosts.
