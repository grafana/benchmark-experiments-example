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

# Resolves aliases such as latest_published to the concrete suite version, so
# a resumed run cannot silently move to a newly published version.
RESOLVE_SUITE_VERSION = (
    "import sys\n"
    "from agento11y.experiments import TestSuitesClient\n"
    "client = TestSuitesClient()\n"
    "print(client.resolve_version(client.get_suite(sys.argv[1]), sys.argv[2]))\n"
)


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
    parser.add_argument(
        "--suite-version",
        default=os.getenv("AGENTO11Y_SUITE_VERSION", ""),
        help="published suite version to pin (for example v1); default latest_published",
    )
    parser.add_argument("--sync-suite", action="store_true", help="publish task definitions only")
    parser.add_argument(
        "--dry-run", action="store_true", help="print commands without running them"
    )
    return parser.parse_args()


def validate(args: argparse.Namespace) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}", args.name):
        raise ValueError("--name must be 1-80 letters, digits, dots, underscores or hyphens")
    model_invalid = not args.model.strip() or any(char.isspace() for char in args.model)
    if not args.sync_suite and model_invalid:
        raise ValueError("--model or ANTHROPIC_MODEL is required, without whitespace")
    if args.concurrency < 1:
        raise ValueError("--concurrency must be positive")
    if args.suite_version.strip() and not re.fullmatch(r"[a-zA-Z0-9_.-]+", args.suite_version):
        raise ValueError("--suite-version must be letters, digits, dots, underscores or hyphens")
    for path in ("pyproject.toml", "o11y_bench/agento11y_publish.py", "tasks-spec"):
        if not (args.bench_repo / path).exists():
            raise ValueError(
                f"--bench-repo needs the Agent Observability integration: missing {path}"
            )
    unknown = sorted(set(args.task) - known_task_ids(args.bench_repo))
    if unknown:
        raise ValueError(f"unknown --task {', '.join(unknown)}; task IDs come from tasks-spec/")


def known_task_ids(bench_repo: Path) -> set[str]:
    # sync_tasks names each task after its spec's id, which matches the file name.
    return {spec.stem for spec in (bench_repo / "tasks-spec").rglob("*.yaml")}


def job_name(args: argparse.Namespace) -> str:
    return f"watcherbench-{args.name}-k{args.trials}"


def uv(args: argparse.Namespace) -> list[str]:
    return ["uv", "run", "--project", str(args.bench_repo), "--extra", "agento11y", "--frozen"]


def commands(args: argparse.Namespace) -> list[list[str]]:
    if args.sync_suite:
        return [[*uv(args), "python", "-m", "o11y_bench.agento11y_suite"]]
    tasks = ROOT / "tasks" / "o11y-bench"
    model = args.model if "/" in args.model else f"anthropic/{args.model}"
    job = [
        *uv(args),
        "python",
        "-m",
        "o11y_bench",
        "job",
        "--model",
        model,
        "--job-name",
        job_name(args),
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
        [*uv(args), "python", "-m", "scripts.sync_tasks", "--output-dir", str(tasks)],
        job,
    ]


def cloud_url(env: dict[str, str]) -> str:
    configured = env.get("AGENTO11Y_GRAFANA_URL", "").strip()
    if configured:
        parsed = urlparse(configured)
        if (
            parsed.scheme != "https"
            or not re.fullmatch(r"[a-zA-Z0-9.-]+", parsed.hostname or "")
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


def nonblank(env: dict[str, str], key: str, default: str) -> str:
    """Like setdefault, but a key that .env defines as blank also gets the default."""
    return env.get(key, "").strip() or default


def require_resolved(env: dict[str, str], keys: tuple[str, ...]) -> None:
    for key in keys:
        value = env.get(key, "").strip()
        if not value or value.startswith("op://"):
            raise ValueError(f"{key} must be resolved; use op run --env-file=.env")


def suite_environment() -> dict[str, str]:
    """Only what publishing the suite needs: the stack and its service account."""
    env = dict(os.environ)
    url = cloud_url(env)
    env["AGENTO11Y_GRAFANA_URL"] = url
    env["AGENTO11Y_CONTROL_ENDPOINT"] = nonblank(
        env, "AGENTO11Y_CONTROL_ENDPOINT", url + "/a/grafana-agento11y-app"
    )
    env["AGENTO11Y_SERVICE_ACCOUNT_TOKEN"] = nonblank(
        env,
        "AGENTO11Y_SERVICE_ACCOUNT_TOKEN",
        env.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", "").strip(),
    )
    env["AGENTO11Y_SUITE_ID"] = nonblank(env, "AGENTO11Y_SUITE_ID", "watcherbench-o11y-bench")
    require_resolved(env, ("AGENTO11Y_SERVICE_ACCOUNT_TOKEN",))
    return env


def environment(args: argparse.Namespace) -> dict[str, str]:
    env = suite_environment()
    env["AGENTO11Y_INGEST_ACTOR"] = nonblank(
        env, "AGENTO11Y_INGEST_ACTOR", "ingest:watcherbench/o11y-bench"
    )
    env["AGENTO11Y_SUITE_VERSION"] = args.suite_version.strip() or "latest_published"
    env["AGENTO11Y_EXPERIMENT_ID"] = job_name(args)
    # Include the trial count so k3 and k5 runs of one name stay distinguishable.
    env["AGENTO11Y_EXPERIMENT_NAME"] = f"{args.name} (k={args.trials})"
    env["AGENTO11Y_AGENT_NAME"] = "o11y-bench"
    env["AGENTO11Y_AGENT_VERSION"] = subprocess.check_output(
        ["git", "-C", str(args.bench_repo), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    require_resolved(
        env,
        (
            "AGENTO11Y_ENDPOINT",
            "AGENTO11Y_AUTH_TENANT_ID",
            "AGENTO11Y_AUTH_TOKEN",
            "ANTHROPIC_API_KEY",
        ),
    )
    return env


def resolve_suite_version(args: argparse.Namespace, env: dict[str, str]) -> str:
    command = [*uv(args), "python", "-c", RESOLVE_SUITE_VERSION]
    resolved = subprocess.check_output(
        [*command, env["AGENTO11Y_SUITE_ID"], env["AGENTO11Y_SUITE_VERSION"]],
        cwd=args.bench_repo,
        env=env,
        text=True,
    ).strip()
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", resolved):
        raise ValueError(f"could not resolve suite version {env['AGENTO11Y_SUITE_VERSION']!r}")
    return resolved


def claim_path(args: argparse.Namespace) -> Path:
    # Kept outside Harbor's job directory so Harbor still starts fresh jobs in an empty dir.
    return ROOT / "jobs" / "experiment-inputs" / f"{job_name(args)}.json"


def run_inputs(args: argparse.Namespace, env: dict[str, str]) -> dict[str, object]:
    return {
        "model": args.model.removeprefix("anthropic/"),
        "tasks": sorted(set(args.task)),
        "agent_version": env["AGENTO11Y_AGENT_VERSION"],
        "suite_id": env["AGENTO11Y_SUITE_ID"],
        "suite_version": env["AGENTO11Y_SUITE_VERSION"],
    }


def check_claim(args: argparse.Namespace, inputs: dict[str, object]) -> None:
    path = claim_path(args)
    if not path.exists():
        return
    saved = json.loads(path.read_text())
    changed = [
        f"{key}: {saved.get(key)!r} -> {value!r}"
        for key, value in inputs.items()
        if saved.get(key) != value
    ]
    if changed:
        raise ValueError(
            "run configuration changed (" + "; ".join(changed) + "); "
            "choose a new --name, or restore the original settings to resume"
        )


def record_claim(args: argparse.Namespace, inputs: dict[str, object]) -> None:
    path = claim_path(args)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inputs, indent=2) + "\n")


def run_experiment(args: argparse.Namespace, plan: list[list[str]]) -> None:
    env = environment(args)
    env["AGENTO11Y_SUITE_VERSION"] = resolve_suite_version(args, env)
    inputs = run_inputs(args, env)
    check_claim(args, inputs)
    sync, job = plan
    subprocess.run(sync, cwd=args.bench_repo, env=env, check=True)
    try:
        subprocess.run(job, cwd=args.bench_repo, env=env, check=True)
    finally:
        # Lock the name only once Harbor has created the job, so a run that
        # failed before any trial started can be fixed and rerun as-is.
        if (ROOT / "jobs" / "experiments" / job_name(args)).exists():
            record_claim(args, inputs)


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
        if args.sync_suite:
            subprocess.run(plan[0], cwd=args.bench_repo, env=suite_environment(), check=True)
            return
        run_experiment(args, plan)
    except (ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
