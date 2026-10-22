#!/usr/bin/env python3
"""Run the existing o11y-bench tasks and publish configurable attempts per task."""

import argparse
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]


def positive_trials(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("trial count must be a positive integer") from exc
    if count < 1:
        raise argparse.ArgumentTypeError("trial count must be a positive integer")
    return count


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="unique candidate/run label; reuse to resume")
    parser.add_argument("--bench-repo", type=Path, default=ROOT.parent / "o11y-bench")
    parser.add_argument("--model", default=os.getenv("ANTHROPIC_MODEL", ""))
    parser.add_argument("--task", action="append", default=[], help="task ID; omit for all tasks")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument(
        "--trials",
        type=positive_trials,
        default=os.getenv("EXPERIMENT_TRIALS", "3"),
        help="trials per task; EXPERIMENT_TRIALS defaults to 3 for demonstration",
    )
    parser.add_argument("--sync-suite", action="store_true", help="publish task definitions only")
    parser.add_argument(
        "--dry-run", action="store_true", help="print commands without running them"
    )
    return parser.parse_args()


def validate(args: argparse.Namespace) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}", args.name):
        raise ValueError("--name must be 1-80 letters, digits, dots, underscores or hyphens")
    if not args.model.strip() or any(char.isspace() for char in args.model):
        raise ValueError("--model or ANTHROPIC_MODEL is required, without whitespace")
    if args.concurrency < 1:
        raise ValueError("--concurrency must be positive")
    for task in args.task:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", task):
            raise ValueError("--task must be an existing task ID")
    for path in ("pyproject.toml", "o11y_bench/agento11y_publish.py", "tasks-spec"):
        if not (args.bench_repo / path).exists():
            raise ValueError(
                f"--bench-repo needs the Agent Observability integration: missing {path}"
            )


def commands(args: argparse.Namespace) -> list[list[str]]:
    uv = ["uv", "run", "--project", str(args.bench_repo), "--extra", "agento11y", "--frozen"]
    if args.sync_suite:
        return [[*uv, "python", "-m", "o11y_bench.agento11y_suite"]]
    tasks = ROOT / "tasks" / "o11y-bench"
    model = args.model if "/" in args.model else f"anthropic/{args.model}"
    job = [
        *uv,
        "python",
        "-m",
        "o11y_bench",
        "job",
        "--model",
        model,
        "--job-name",
        f"watcherbench-{args.name}-k{args.trials}",
        "--path",
        str(tasks),
        "--jobs-dir",
        str(ROOT / "jobs" / "experiments"),
        "--n-attempts",
        str(args.trials),
        "--n-concurrent",
        str(args.concurrency),
        "--agento11y-publish",
    ]
    for task in args.task:
        job.extend(["--task-name", task])
    if armcap := os.getenv("OPENSSL_armcap"):
        job.extend(["--ae", f"OPENSSL_armcap={armcap}"])
    return [
        [*uv, "python", "-m", "scripts.sync_tasks", "--output-dir", str(tasks)],
        job,
    ]


def cloud_url(env: dict[str, str]) -> str:
    configured = env.get("AGENTO11Y_GRAFANA_URL", "").strip()
    if configured:
        parsed = urlparse(configured)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("AGENTO11Y_GRAFANA_URL must be an absolute HTTPS stack URL")
        return configured.rstrip("/")
    mcp = urlparse(env.get("MCP_URL", ""))
    stack = mcp.path.removeprefix("/mcp/")
    if mcp.hostname == "mcp.grafana.com" and re.fullmatch(r"[a-zA-Z0-9-]+\.grafana\.net", stack):
        return f"https://{stack}"
    raise ValueError("set AGENTO11Y_GRAFANA_URL to the Grafana Cloud stack URL")


def environment(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    env["AGENTO11Y_GRAFANA_URL"] = cloud_url(env)
    env.setdefault(
        "AGENTO11Y_CONTROL_ENDPOINT", env["AGENTO11Y_GRAFANA_URL"] + "/a/grafana-agento11y-app"
    )
    env.setdefault("AGENTO11Y_SERVICE_ACCOUNT_TOKEN", env.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", ""))
    env.setdefault("AGENTO11Y_SUITE_ID", "watcherbench-o11y-bench")
    env.setdefault("AGENTO11Y_INGEST_ACTOR", "ingest:watcherbench/o11y-bench")
    env.setdefault("AGENTO11Y_SUITE_VERSION", "latest_published")
    env["AGENTO11Y_EXPERIMENT_ID"] = f"watcherbench-{args.name}-k{args.trials}"
    env["AGENTO11Y_EXPERIMENT_NAME"] = args.name
    env["AGENTO11Y_AGENT_NAME"] = "o11y-bench"
    env["AGENTO11Y_AGENT_VERSION"] = subprocess.check_output(
        ["git", "-C", str(args.bench_repo), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    for key in (
        "AGENTO11Y_ENDPOINT",
        "AGENTO11Y_AUTH_TENANT_ID",
        "AGENTO11Y_AUTH_TOKEN",
        "AGENTO11Y_SERVICE_ACCOUNT_TOKEN",
        "ANTHROPIC_API_KEY",
    ):
        value = env.get(key, "").strip()
        if not value or value.startswith("op://"):
            raise ValueError(f"{key} must be resolved; use op run --env-file=.env")
    return env


def claim_run(args: argparse.Namespace, env: dict[str, str]) -> None:
    path = (
        ROOT / "jobs" / "experiments" / f"watcherbench-{args.name}-k{args.trials}" / "inputs.json"
    )
    inputs = {
        "model": args.model.removeprefix("anthropic/"),
        "tasks": sorted(set(args.task)),
        "agent_version": env["AGENTO11Y_AGENT_VERSION"],
        "suite_id": env["AGENTO11Y_SUITE_ID"],
        "suite_version": env["AGENTO11Y_SUITE_VERSION"],
    }
    if path.exists() and json.loads(path.read_text()) != inputs:
        raise ValueError("run configuration changed; choose a new --name for comparison")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inputs, indent=2) + "\n")


def main() -> None:
    args = arguments()
    args.bench_repo = args.bench_repo.resolve()
    try:
        validate(args)
        plan = commands(args)
        if args.dry_run:
            for command in plan:
                print(shlex.join(command))
            return
        env = environment(args)
        if not args.sync_suite:
            claim_run(args, env)
        for command in plan:
            subprocess.run(command, cwd=args.bench_repo, env=env, check=True)
    except (ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
