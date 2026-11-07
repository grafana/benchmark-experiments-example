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
`ANTHROPIC_API_KEY` is required for the existing benchmark's Anthropic grader,
including when the candidate model uses another provider such as OpenAI.
`AGENTO11Y_GRAFANA_URL` selects the Cloud stack; if omitted, the launcher
derives it from the configured stack-in-path `MCP_URL`. The experiment agent
uses each task's Docker stack, independently of that Cloud MCP setting.

Preview commands without credentials, model calls, or Cloud writes:

```sh
make experiment-plan EXPERIMENT_NAME=baseline \
  EXPERIMENT_TASKS='promql-error-rate find-slow-traces'
```

Set `EXPERIMENT_TRIALS` in `.env` to a positive integer. It defaults to **3 for
demonstration purposes**, including when the value is blank. To override `.env`
for one run, pass it to `make` (for example `EXPERIMENT_TRIALS=5`), not as a
shell variable before `op run`. Publish the task definitions once, then run the
configured number of independent attempts for each selected task:

```sh
op run --env-file=.env -- make experiment-suite

op run --env-file=.env -- make experiment EXPERIMENT_NAME=baseline \
  EXPERIMENT_TASKS='promql-error-rate find-slow-traces'
```

Omit `EXPERIMENT_TASKS` to run every existing task. Before a run starts,
task IDs are checked against `scripts.sync_tasks --list-ids` from the checkout,
the same IDs Harbor receives. `experiment-plan` only checks their format. Set
`O11Y_BENCH_REPO` for a different checkout and `EXPERIMENT_MODEL` for a
different model; it defaults to `ANTHROPIC_MODEL` from `.env`. Start with a
selected task before running the full suite.

`experiment-suite` needs only the stack URL and the Grafana service-account
token; it doesn't check the Anthropic key or ingestion credentials. Like
`experiment`, it refuses to run while the checkout has uncommitted changes, so
published task definitions always match a commit.
It synchronizes the task specs to the dedicated
`watcherbench-o11y-bench` Cloud test suite. `experiment` publishes graded trials
as they finish, reusing the published suite. `AGENTO11Y_SUITE_ID` overrides that suite;
synchronization updates its
cases to match the source dataset, including removing cases absent from source.
No production evaluation rules are created.

Use a new `EXPERIMENT_NAME` for each candidate you want to compare, for example
`baseline` and `candidate`. Reusing a name resumes the same job and experiment.
The runner refuses to resume if the model, selected tasks, agent code (Git SHA)
or suite version changed, and names what differs. It also refuses to run while
the o11y-bench checkout has uncommitted changes, which the SHA can't capture.

The run's settings are written to `jobs/experiment-inputs/` just before Harbor
starts the job, so they survive even if the run is killed. Existing records
remain binding even if the local job directory is removed: the Cloud experiment
may still contain results. A task-sync failure before settings are recorded
doesn't lock a fresh name. Once recorded, use a new name for a different
configuration. A job directory with no recorded settings is refused; choose a
new name, or delete that directory to restart under the same name. New trials
then join the existing Cloud experiment with that ID. Runs that recorded their settings inside the job directory
(`inputs.json`) are still checked. Keep the task dataset and grader configuration fixed
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

## k6 offline evals

`make k6-evals` runs the same o11y-bench tasks as `make experiment`, but k6 OSS
drives the experiment, following Grafana's
[`agento11y-evals` jslib](https://github.com/grafana/jslib.k6.io/blob/main/lib/agento11y-evals/0.1.0/index.js)
and the
[reliability-inbox example](https://github.com/grafana/k6-experiments/blob/main/internal/experiments/reliabilityinbox/suggestions/evals/rank_agento11y.test.js).
It is the CI-friendly path: one `k6 run`, no Python publisher.

k6 can't start Docker or Harbor, so `k6_evals.py` serves a small runner
(`k6/runner.py`) around the script, like the reference serves its agent. For each
trial k6 asks the runner for one fresh o11y-bench job: the agent, its isolated
Docker stack and the benchmark's own verifier. A trial passes when the reward is
`1.0`, the same full-pass criterion as `make experiment`. Trials run one at a
time.

| File | Role |
|---|---|
| `k6_evals.py` | launcher: validates inputs, starts the runner, runs k6 |
| `k6/o11y_bench_evals.test.js` | the k6 script: trials, scores, Pass@k / Pass^k |
| `k6/runner.py` | serves `/tasks`, `/run` and `/summary` over local HTTP |
| `k6/trial_result.py` | reads a graded Harbor trial into the JSON k6 records |

Requirements are the same as `make experiment` (`uv`, Docker, a clean
`../o11y-bench` checkout), plus [`k6`](https://grafana.com/docs/k6/latest/set-up/install-k6/).

```sh
# Preview the commands; no credentials, model calls or Cloud writes.
make k6-evals-plan EXPERIMENT_NAME=baseline EXPERIMENT_TASKS=promql-error-rate

# Baseline: every o11y-bench task, locally. EXPERIMENT_TASKS empty means all.
op run --env-file=.env -- make k6-evals EXPERIMENT_NAME=baseline

# One task, or several separated by spaces, locally.
op run --env-file=.env -- make k6-evals EXPERIMENT_NAME=smoke \
  EXPERIMENT_TASKS=promql-error-rate

# Send the experiment to the Grafana Cloud stack defined in .env.
# Run make experiment-suite first, once: it publishes the tasks as the test suite
# that k6-evals pulls. Without it the run fails with "test suite ... not found".
op run --env-file=.env -- make experiment-suite
op run --env-file=.env -- make k6-evals EXPERIMENT_NAME=smoke EXPERIMENT_TASKS=promql-error-rate EXPERIMENT_PUBLISH=true
```

Publishing requires `make experiment-suite` to have run at least once; local runs don't.
Local runs need only `ANTHROPIC_API_KEY` (the verifier's grader) and the model
key. They print each trial and, at the end, `Pass@k` and `Pass^k` for the tasks
run. With `EXPERIMENT_PUBLISH=true` the run also needs the `AGENTO11Y_*` and
service-account settings from `.env.example`, pulls the published suite version
(`EXPERIMENT_SUITE_VERSION` pins it, otherwise `latest_published`), records each
trial's conversation, usage and `o11y_bench_reward` score, and prints the
experiment URL under **Agent Observability → Experiments**.

Each run creates a new experiment (`k6-<name>-k<trials>-<timestamp>`); unlike
`make experiment`, a name is not resumed. A task whose Harbor job fails counts
as a failed trial.
