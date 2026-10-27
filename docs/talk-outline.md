# Talk Outline

## Thesis

AI observability agents need evals that check what they did, not just what they
said. Dashboards are a good stress test because a query can be valid, plausible,
and still wrong.

## Demo Beats

The demo builds in two acts. Act 1 uses only the benchmark and its own HTML
report. Act 2 sends the same benchmark trials to a Grafana Cloud stack as Agent
Observability experiments, which shows what changes when results live somewhere
shared.

### Act 1: The benchmark on its own

1. Run `make demo`.
2. Point at the mean-latency query that looks valid but fails the p95 task.
3. Show the corrected `histogram_quantile` query and linked logs/traces.
4. Show the dashboard patch dry-run.
5. Run `make score` and compare Pass^3 with Pass@3.
6. Show a real o11y-bench run for one task with three trials, published nowhere.
   Print the commands with
   `make experiment-plan EXPERIMENT_NAME=local EXPERIMENT_TASKS=promql-error-rate`.
   It prints a task sync and a job command. Run both from the o11y-bench
   checkout, dropping `--agento11y-publish` from the job command. The job writes
   Harbor artifacts and an HTML report under `jobs/experiments/<job-name>/`.
7. Open that job's `run_report.html`, the benchmark's output dashboard: each
   trial's reward, grader details, and transcript.
8. Name the limits: the report is a local file for one job. Comparing a
   candidate means generating another report or running
   `reporting.compare_report` against two job directories. Nothing records which
   task definitions, agent commit, or model a result came from, beyond the
   directory name.

### Act 2: The same trials as Agent Observability experiments

9. Publish the task definitions once as a Cloud test suite:
   `op run --env-file=.env -- make experiment-suite`. Point out the version it
   prints, for example `v2`.
10. Run the same task as a named baseline, pinned to that suite version:
    `op run --env-file=.env -- make experiment EXPERIMENT_NAME=baseline EXPERIMENT_TASKS=promql-error-rate EXPERIMENT_SUITE_VERSION=v2`.
    It's the Act 1 job command plus `--agento11y-publish`: each graded trial is
    sent to the stack as soon as it finishes. The run prints the Cloud
    experiment URL.
11. Open **Agent Observability → Experiments** in the stack. Show the
    experiment `baseline (k=3)`, its three trials, the pass/fail result per
    trial, and the quality scores published separately.
12. Run a candidate under a new name, such as a different model with
    `EXPERIMENT_MODEL`, pinned to the same suite version. Select both runs and
    compare **Pass@3** (at least one passing trial per task) with **Pass^3**
    (all three passing). This is beat 5's comparison, now on real trials and
    shared with the team.
13. Show why the comparison can be trusted:
    - Every run records its model, tasks, o11y-bench commit, and suite version.
    - Resuming a name with different settings is refused, and the error names
      what changed.
    - Runs from an o11y-bench checkout with uncommitted changes are refused.
    - `latest_published` is resolved to a concrete suite version at the start
      and recorded.

## Running It Live

- **Before the talk:** run both Act 2 experiments ahead of time and open their
  experiment pages in tabs. One task with three trials takes several minutes, and
  the full suite (63 tasks, 189 trials at the default of three) is far too long
  for a talk.
- **During the talk:** keep the live step to `make experiment-plan` and one short
  run, or show a run's live progress instead of waiting for it to finish.
- **Setup:** Docker, `uv`, a sibling `../o11y-bench` checkout, and `.env` with
  the Agent Observability ingestion credentials and a Grafana service-account
  token. See `bench/o11y-bench/README.md`.
- **ARM laptops:** prefix commands with `OPENSSL_armcap=0` if the runner exits
  with code 132.

## Audience Takeaway

The benchmark is not a leaderboard stunt. It is a reproducible way to separate
one-off lucky answers from agents that consistently use the right observability
evidence. Its HTML report answers "how did this run do?". Agent Observability
experiments answer "is this candidate better than the last one, on the same
tasks, every time?", with the results kept in your stack where the team can see
them.
