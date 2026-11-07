#!/usr/bin/env python3
"""Run o11y-bench tasks as k6 offline evals, optionally publishing to Agent Observability."""

import argparse
import os
import platform
import shlex
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import experiments
from stack_env import require_resolved

ROOT = experiments.ROOT
K6_DIR = Path(__file__).resolve().parent / "k6"
SCRIPT = K6_DIR / "o11y_bench_evals.test.js"
RUNNER_START_TIMEOUT = 300


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="run label; scopes job and experiment ids")
    parser.add_argument("--bench-repo", type=Path, default=ROOT.parent / "o11y-bench")
    parser.add_argument("--model", default=os.getenv("ANTHROPIC_MODEL", ""))
    parser.add_argument("--task", action="append", default=[], help="task ID; omit for all tasks")
    parser.add_argument(
        "--trials",
        type=experiments.positive_trials,
        default=os.getenv("EXPERIMENT_TRIALS", "").strip() or "3",
        help="trials per task; EXPERIMENT_TRIALS defaults to 3 for demonstration",
    )
    parser.add_argument("--suite-version", default=os.getenv("AGENTO11Y_SUITE_VERSION", ""))
    parser.add_argument("--port", type=int, default=8098, help="local port for the task runner")
    parser.add_argument("--publish", action="store_true", help="send the experiment to Grafana Cloud")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running them")
    args = parser.parse_args()
    # The fields experiments.validate() and its helpers read.
    args.sync_suite, args.concurrency = False, 1
    return args


def new_run_id() -> str:
    """One per invocation: a timestamp for ordering plus random bits, so runs started in
    the same second still get distinct experiment and job ids."""
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def experiment_id(args: argparse.Namespace, run_id: str) -> str:
    return f"k6-{args.name}-k{args.trials}-{run_id}"


def runner_command(args: argparse.Namespace, run_id: str) -> list[str]:
    tasks = ROOT / "tasks" / "o11y-bench"
    command = [
        "uv", "run", "--project", str(args.bench_repo), "--frozen",
        "python", str(K6_DIR / "runner.py"),
        "--bench-repo", str(args.bench_repo),
        "--model", args.model if "/" in args.model else f"anthropic/{args.model}",
        "--name", args.name,
        "--run-id", run_id,
        "--tasks-dir", str(tasks),
        "--jobs-dir", str(ROOT / "jobs" / "k6-evals"),
        "--port", str(args.port),
    ]  # fmt: skip
    if armcap := openssl_armcap():
        command.extend(["--agent-env", f"OPENSSL_armcap={armcap}"])
    return command


def openssl_armcap() -> str:
    """Exit code 132 (SIGILL) in `cryptography` on ARM hosts is fixed by OPENSSL_armcap=0."""
    return os.getenv("OPENSSL_armcap") or ("0" if platform.machine() in ("arm64", "aarch64") else "")


def k6_command() -> list[str]:
    return ["k6", "run", str(SCRIPT)]


def k6_environment(args: argparse.Namespace, run_id: str) -> dict[str, str]:
    """Process environment for the runner and k6, with what the script reads."""
    if args.publish:
        # Also checks the ingest credentials, the Cloud stack and the service account.
        env = experiments.environment(args)
        env["AGENTO11Y_SUITE_VERSION"] = experiments.resolve_suite_version(args, env)
    else:
        env = dict(os.environ)
        env["O11Y_BENCH_SHA"] = experiments.agent_version(args.bench_repo)
        require_resolved(env, ("ANTHROPIC_API_KEY",))
    env.update(
        EXPERIMENT_ID=experiment_id(args, run_id),
        EXPERIMENT_NAME=args.name,
        EXPERIMENT_MODEL=args.model.removeprefix("anthropic/"),
        EXPERIMENT_TRIALS=str(args.trials),
        EXPERIMENT_TASKS=" ".join(args.task),
        EXPERIMENT_PUBLISH="true" if args.publish else "false",
        RUNNER_URL=f"http://127.0.0.1:{args.port}",
    )
    if args.publish:
        env["O11Y_BENCH_SHA"] = env["AGENTO11Y_AGENT_VERSION"]
    return env


def wait_for_runner(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + RUNNER_START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"runner exited with code {process.returncode}")
        try:
            urllib.request.urlopen(f"{url}/tasks", timeout=2).close()
            return
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    raise RuntimeError(f"runner not ready after {RUNNER_START_TIMEOUT}s")


def run_evals(args: argparse.Namespace) -> int:
    experiments.check_tasks(args)
    run_id = new_run_id()
    env = k6_environment(args, run_id)
    runner = subprocess.Popen(runner_command(args, run_id), env=env, cwd=args.bench_repo)
    try:
        wait_for_runner(env["RUNNER_URL"], runner)
        return subprocess.run(k6_command(), env=env).returncode
    finally:
        runner.terminate()
        runner.wait()


def main() -> None:
    args = arguments()
    args.bench_repo = args.bench_repo.resolve()
    try:
        experiments.validate(args)
        if args.dry_run:
            print(shlex.join(runner_command(args, new_run_id())))
            print(shlex.join(k6_command()))
            return
        raise SystemExit(run_evals(args))
    except FileNotFoundError as exc:
        if exc.filename in ("uv", "git", "k6"):
            raise SystemExit(f"command not found: {exc.filename}; install it first") from exc
        raise SystemExit(str(exc)) from exc
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
