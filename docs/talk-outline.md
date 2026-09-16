# Talk Outline

## Thesis

AI observability agents need evals that check what they did, not just what they
said. Dashboards are a good stress test because a query can be valid, plausible,
and still wrong.

## Demo Beats

1. Run `make demo`.
2. Point at the mean-latency query that looks valid but fails the p95 task.
3. Show the corrected `histogram_quantile` query and linked logs/traces.
4. Show the dashboard patch dry-run.
5. Run `make score` and compare Pass^3 with Pass@3.
6. Switch to `bench/o11y-bench/README.md` for the live benchmark path.

## Audience Takeaway

The benchmark is not a leaderboard stunt. It is a reproducible way to separate
one-off lucky answers from agents that consistently use the right observability
evidence.

