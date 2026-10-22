"""Contract checks for the configurable experiment publishing workflow."""

import argparse
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import experiments


def options(**overrides: object) -> argparse.Namespace:
    values = dict(
        name="baseline",
        bench_repo=Path("/bench"),
        model="claude-test",
        task=["promql-error-rate", "find-slow-traces"],
        concurrency=1,
        trials=3,
        suite_version="",
        sync_suite=False,
    )
    return argparse.Namespace(**(values | overrides))


RUN_ENV = {
    "AGENTO11Y_AGENT_VERSION": "sha",
    "AGENTO11Y_SUITE_ID": "suite",
    "AGENTO11Y_SUITE_VERSION": "v1",
}


class ExperimentTests(unittest.TestCase):
    def test_trial_count_defaults_to_three_and_accepts_environment_override(self) -> None:
        argv = ["experiments.py", "--name", "baseline"]
        with patch.dict(os.environ, {}, clear=True), patch("sys.argv", argv):
            self.assertEqual(experiments.arguments().trials, 3)
        with patch.dict(os.environ, {"EXPERIMENT_TRIALS": "5"}), patch("sys.argv", argv):
            self.assertEqual(experiments.arguments().trials, 5)
        with (
            patch.dict(os.environ, {"EXPERIMENT_TRIALS": "5"}),
            patch("sys.argv", argv + ["--trials", "2"]),
        ):
            self.assertEqual(experiments.arguments().trials, 2)

    def test_invalid_environment_trial_counts_are_rejected(self) -> None:
        for value in ("0", "-1", "1.5", "abc", ""):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"EXPERIMENT_TRIALS": value}),
                patch("sys.argv", ["experiments.py", "--name", "baseline"]),
                patch("sys.stderr", new_callable=io.StringIO) as stderr,
                self.assertRaises(SystemExit) as error,
            ):
                experiments.arguments()
            self.assertEqual(error.exception.code, 2)
            self.assertIn("positive integer", stderr.getvalue())

    def test_task_identity_and_configured_attempts_reach_native_publisher(self) -> None:
        plan = experiments.commands(options(trials=5))
        job = plan[-1]
        self.assertEqual(job[job.index("--n-attempts") + 1], "5")
        self.assertEqual(job[job.index("--job-name") + 1], "watcherbench-baseline-k5")
        self.assertIn("--agento11y-publish", job)
        self.assertEqual(job[job.index("--model") + 1], "anthropic/claude-test")
        self.assertEqual(job.count("--task-name"), 2)
        self.assertIn("promql-error-rate", job)
        self.assertIn("find-slow-traces", job)
        self.assertNotIn("--agent-import-path", job)

    def test_no_task_filter_runs_whole_existing_suite(self) -> None:
        self.assertNotIn("--task-name", experiments.commands(options(task=[]))[-1])

    def test_cpu_override_reaches_container_without_forwarding_other_environment(self) -> None:
        with patch.dict(os.environ, {"OPENSSL_armcap": "0", "UNRELATED": "private"}):
            job = experiments.commands(options())[-1]
        self.assertEqual(job[job.index("--ae") + 1], "OPENSSL_armcap=0")
        self.assertNotIn("private", " ".join(job))

    def test_jobs_reuse_published_suite_without_creating_a_new_version(self) -> None:
        plan = experiments.commands(options())
        self.assertFalse(any("o11y_bench.agento11y_suite" in command for command in plan))
        sync = experiments.commands(options(sync_suite=True))
        self.assertEqual(len(sync), 1)
        self.assertIn("o11y_bench.agento11y_suite", sync[0])

    def test_run_labels_keep_comparisons_separate(self) -> None:
        baseline = experiments.commands(options())[-1]
        candidate = experiments.commands(options(name="candidate"))[-1]
        self.assertNotEqual(
            baseline[baseline.index("--job-name") + 1], candidate[candidate.index("--job-name") + 1]
        )

    def test_resume_rejects_different_tasks_under_the_same_name(self) -> None:
        inputs = experiments.run_inputs(options(), RUN_ENV)
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(experiments, "ROOT", Path(directory)),
        ):
            experiments.check_claim(options(), inputs)
            experiments.record_claim(options(), inputs)
            experiments.check_claim(options(), inputs)
            experiments.check_claim(options(trials=5), inputs)
            changed = experiments.run_inputs(options(task=[]), RUN_ENV)
            with self.assertRaisesRegex(ValueError, "tasks: .*new --name"):
                experiments.check_claim(options(), changed)

    def test_claim_lives_outside_harbor_job_directory(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(experiments, "ROOT", Path(directory)),
        ):
            path = experiments.claim_path(options())
            self.assertNotIn(Path(directory) / "jobs" / "experiments", path.parents)

    def test_failure_before_harbor_starts_does_not_lock_the_name(self) -> None:
        with self.run_experiment_in() as (root, run):
            run.side_effect = subprocess.CalledProcessError(1, "sync_tasks")
            with self.assertRaises(subprocess.CalledProcessError):
                experiments.run_experiment(options(), [["sync"], ["job"]])
            self.assertFalse(experiments.claim_path(options()).exists())

    def test_started_job_records_resolved_suite_version(self) -> None:
        with self.run_experiment_in() as (root, run):

            def harbor(command: list[str], **_: object) -> None:
                if command == ["job"]:
                    (root / "jobs" / "experiments" / "watcherbench-baseline-k3").mkdir(parents=True)
                    raise subprocess.CalledProcessError(1, "job")

            run.side_effect = harbor
            with self.assertRaises(subprocess.CalledProcessError):
                experiments.run_experiment(options(), [["sync"], ["job"]])
            saved = json.loads(experiments.claim_path(options()).read_text())
            self.assertEqual(saved["suite_version"], "v2")

    @contextlib.contextmanager
    def run_experiment_in(self):
        env = RUN_ENV | {"AGENTO11Y_SUITE_VERSION": "latest_published"}
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(experiments, "ROOT", Path(directory)) as root,
            patch.object(experiments, "environment", return_value=dict(env)),
            patch.object(experiments, "resolve_suite_version", return_value="v2"),
            patch("experiments.subprocess.run") as run,
        ):
            yield root, run

    def test_suite_sync_needs_only_stack_and_service_account(self) -> None:
        env = {
            "AGENTO11Y_GRAFANA_URL": "https://test.grafana.net",
            "AGENTO11Y_SERVICE_ACCOUNT_TOKEN": "",
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": "test-only",
            "AGENTO11Y_SUITE_ID": " ",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch("experiments.subprocess.check_output") as git,
        ):
            result = experiments.suite_environment()
        git.assert_not_called()
        self.assertEqual(result["AGENTO11Y_SERVICE_ACCOUNT_TOKEN"], "test-only")
        self.assertEqual(result["AGENTO11Y_SUITE_ID"], "watcherbench-o11y-bench")

    def test_unknown_tasks_are_rejected_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bench = Path(directory)
            (bench / "o11y_bench").mkdir()
            (bench / "pyproject.toml").touch()
            (bench / "o11y_bench" / "agento11y_publish.py").touch()
            (bench / "tasks-spec" / "prometheus_query").mkdir(parents=True)
            (bench / "tasks-spec" / "prometheus_query" / "promql-error-rate.yaml").touch()
            experiments.validate(options(bench_repo=bench, task=["promql-error-rate"]))
            with self.assertRaisesRegex(ValueError, "promql-eror-rate"):
                experiments.validate(options(bench_repo=bench, task=["promql-eror-rate"]))
            experiments.validate(options(bench_repo=bench, task=[], model="", sync_suite=True))

    def test_stack_url_comes_from_configured_hosted_mcp(self) -> None:
        self.assertEqual(
            experiments.cloud_url({"MCP_URL": "https://mcp.grafana.com/mcp/test.grafana.net"}),
            "https://test.grafana.net",
        )
        with self.assertRaises(ValueError):
            experiments.cloud_url({"MCP_URL": "http://private/mcp"})
        with self.assertRaises(ValueError):
            experiments.cloud_url({"AGENTO11Y_GRAFANA_URL": "http://example"})
        with self.assertRaises(ValueError):
            experiments.cloud_url({"AGENTO11Y_GRAFANA_URL": "https://<your-stack>.grafana.net"})
        self.assertEqual(
            experiments.cloud_url(
                {
                    "AGENTO11Y_GRAFANA_URL": "",
                    "MCP_URL": "https://mcp.grafana.com/mcp/test.grafana.net",
                }
            ),
            "https://test.grafana.net",
        )

    def test_existing_process_environment_is_not_modified(self) -> None:
        env = {
            "AGENTO11Y_GRAFANA_URL": "https://test.grafana.net",
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": "test-only",
            "AGENTO11Y_ENDPOINT": "https://ingest.example",
            "AGENTO11Y_AUTH_TENANT_ID": "test",
            "AGENTO11Y_AUTH_TOKEN": "test-only",
            "ANTHROPIC_API_KEY": "test-only",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch("experiments.subprocess.check_output", return_value="abc123\n"),
        ):
            result = experiments.environment(options(trials=5))
            self.assertEqual(result["AGENTO11Y_SERVICE_ACCOUNT_TOKEN"], "test-only")
            self.assertEqual(result["AGENTO11Y_AGENT_VERSION"], "abc123")
            self.assertEqual(result["AGENTO11Y_EXPERIMENT_ID"], "watcherbench-baseline-k5")
            self.assertEqual(result["AGENTO11Y_EXPERIMENT_NAME"], "baseline (k=5)")
            self.assertEqual(result["AGENTO11Y_SUITE_VERSION"], "latest_published")
            self.assertNotIn("AGENTO11Y_EXPERIMENT_ID", os.environ)


if __name__ == "__main__":
    unittest.main()
