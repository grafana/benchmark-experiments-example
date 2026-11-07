#!/usr/bin/env python3
"""Serve o11y-bench tasks over HTTP so a k6 script can run them as experiment trials.

k6 can't start Docker or Harbor, so this process does it on k6's behalf, the way
the reference k6 eval serves its agent around the script. It runs inside the
o11y-bench environment (`uv run --project <o11y-bench>`).

  GET  /tasks    every task: id, category, statement
  POST /run      {"task_id", "attempt"} -> graded result of one fresh Harbor job
  GET  /summary  {"task_id": [passed, ...]} for the trials run so far

Requests are served one at a time: each trial owns a Docker stack, so this
matches `--n-concurrent 1`.
"""

import argparse
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from trial_result import read_trial, use_bench_repo


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.history: dict[str, list[bool]] = {}
        self.tasks_dir = args.tasks_dir
        self.specs = self.load_specs()

    def load_specs(self) -> list[dict[str, str]]:
        import yaml

        specs = []
        for path in sorted((self.args.bench_repo / "tasks-spec").rglob("*.yaml")):
            spec = yaml.safe_load(path.read_text())
            specs.append(
                {
                    "id": str(spec["id"]),
                    "category": str(spec.get("category") or ""),
                    "statement": str(spec["statement"]).strip(),
                }
            )
        return specs

    def sync_tasks(self) -> None:
        """Materializes Harbor tasks from the specs, once, before the first trial."""
        subprocess.run(
            [sys.executable, "-m", "scripts.sync_tasks", "--output-dir", str(self.tasks_dir)],
            cwd=self.args.bench_repo,
            check=True,
        )

    def job_command(self, task_id: str, job_name: str) -> list[str]:
        command = [
            sys.executable, "-m", "o11y_bench", "job",
            "--model", self.args.model,
            "--job-name", job_name,
            "--path", str(self.tasks_dir),
            "--jobs-dir", str(self.args.jobs_dir),
            "--n-attempts", "1",
            "--n-concurrent", "1",
            "--task-name", task_id,
            "--quiet",
        ]  # fmt: skip
        for setting in self.args.agent_env:
            command.extend(["--ae", setting])
        return command

    def run(self, task_id: str, attempt: int) -> dict[str, Any]:
        if task_id not in {spec["id"] for spec in self.specs}:
            raise ValueError(f"unknown task {task_id!r}")
        job_name = f"k6-{self.args.name}-{task_id}-a{attempt}"
        done = subprocess.run(self.job_command(task_id, job_name), cwd=self.args.bench_repo)
        if done.returncode != 0:
            raise RuntimeError(f"o11y_bench job exited {done.returncode} for {job_name}")
        result = read_trial(self.args.jobs_dir / job_name, self.args.model)
        self.history.setdefault(task_id, []).append(result["passed"])
        return result


def make_handler(runner: Runner) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status: int, body: Any) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            routes = {"/tasks": runner.specs, "/summary": runner.history}
            if self.path in routes:
                self.reply(200, routes[self.path])
            else:
                self.reply(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/run":
                return self.reply(404, {"error": "not found"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(size))
                self.reply(200, runner.run(str(request["task_id"]), int(request["attempt"])))
            except (ValueError, KeyError, RuntimeError, OSError) as exc:
                self.reply(500, {"error": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:
            print(f"runner: {format % args}", flush=True)

    return Handler


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bench-repo", type=Path, required=True)
    parser.add_argument("--model", required=True, help="provider/model, as o11y_bench job takes")
    parser.add_argument("--name", required=True, help="run label; scopes the Harbor job names")
    parser.add_argument("--tasks-dir", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--agent-env", action="append", default=[], help="KEY=VALUE for the agent")
    return parser.parse_args()


def main() -> None:
    args = arguments()
    use_bench_repo(args.bench_repo)
    runner = Runner(args)
    runner.sync_tasks()
    server = HTTPServer(("127.0.0.1", args.port), make_handler(runner))
    print(f"runner: {len(runner.specs)} tasks on http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
