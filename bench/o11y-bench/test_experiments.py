"""Contract checks for the configurable experiment publishing workflow."""

import argparse
import io
import os
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
        sync_suite=False,
    )
    return argparse.Namespace(**(values | overrides))


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
        env = {
            "AGENTO11Y_AGENT_VERSION": "sha",
            "AGENTO11Y_SUITE_ID": "suite",
            "AGENTO11Y_SUITE_VERSION": "v1",
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(experiments, "ROOT", Path(directory)),
        ):
            experiments.claim_run(options(), env)
            experiments.claim_run(options(), env)
            experiments.claim_run(options(trials=5), env)
            self.assertTrue(
                (Path(directory) / "jobs/experiments/watcherbench-baseline-k5/inputs.json").exists()
            )
            with self.assertRaisesRegex(ValueError, "new --name"):
                experiments.claim_run(options(task=[]), env)

    def test_stack_url_comes_from_configured_hosted_mcp(self) -> None:
        self.assertEqual(
            experiments.cloud_url({"MCP_URL": "https://mcp.grafana.com/mcp/test.grafana.net"}),
            "https://test.grafana.net",
        )
        with self.assertRaises(ValueError):
            experiments.cloud_url({"MCP_URL": "http://private/mcp"})
        with self.assertRaises(ValueError):
            experiments.cloud_url({"AGENTO11Y_GRAFANA_URL": "http://example"})

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
            self.assertNotIn("AGENTO11Y_EXPERIMENT_ID", os.environ)


if __name__ == "__main__":
    unittest.main()
