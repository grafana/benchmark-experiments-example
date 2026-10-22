"""Contract checks for the configurable experiment publishing workflow."""

import argparse
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import experiments
from stack_env import suite_environment


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
        for value in ("0", "-1", "1.5", "abc"):
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
            result = suite_environment()
        git.assert_not_called()
        self.assertEqual(result["AGENTO11Y_SERVICE_ACCOUNT_TOKEN"], "test-only")
        self.assertEqual(result["AGENTO11Y_SUITE_ID"], "watcherbench-o11y-bench")

    def test_unknown_tasks_are_rejected_using_sync_tasks_ids(self) -> None:
        listed = "promql-error-rate\nfind-slow-traces\n"
        with patch("experiments.subprocess.check_output", return_value=listed) as sync:
            experiments.check_tasks(options())
            with self.assertRaisesRegex(ValueError, "promql-eror-rate"):
                experiments.check_tasks(options(task=["promql-eror-rate"]))
        self.assertIn("--list-ids", sync.call_args.args[0])
        with patch("experiments.subprocess.check_output") as sync:
            experiments.check_tasks(options(task=[]))
        sync.assert_not_called()

    def test_validate_checks_task_syntax_without_running_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bench = Path(directory)
            (bench / "o11y_bench").mkdir()
            (bench / "pyproject.toml").touch()
            (bench / "o11y_bench" / "agento11y_publish.py").touch()
            (bench / "tasks-spec").mkdir()
            with patch("experiments.subprocess.check_output") as tools:
                experiments.validate(options(bench_repo=bench))
                experiments.validate(options(bench_repo=bench, task=[], model="", sync_suite=True))
                with self.assertRaisesRegex(ValueError, "not a valid task ID"):
                    experiments.validate(options(bench_repo=bench, task=["../x"]))
            tools.assert_not_called()

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
            patch("experiments.subprocess.check_output", side_effect=["", "abc123\n"]),
        ):
            result = experiments.environment(options(trials=5))
            self.assertEqual(result["AGENTO11Y_SERVICE_ACCOUNT_TOKEN"], "test-only")
            self.assertEqual(result["AGENTO11Y_AGENT_VERSION"], "abc123")
            self.assertEqual(result["AGENTO11Y_EXPERIMENT_ID"], "watcherbench-baseline-k5")
            self.assertEqual(result["AGENTO11Y_EXPERIMENT_NAME"], "baseline (k=5)")
            self.assertEqual(result["AGENTO11Y_SUITE_VERSION"], "latest_published")
            self.assertNotIn("AGENTO11Y_EXPERIMENT_ID", os.environ)

    def test_uncommitted_bench_changes_are_refused(self) -> None:
        with (
            patch("experiments.subprocess.check_output", return_value=" M grading/x.py\n"),
            self.assertRaisesRegex(ValueError, "uncommitted changes"),
        ):
            experiments.agent_version(Path("/bench"))

    def test_anthropic_grader_key_is_required_for_every_candidate_provider(self) -> None:
        env = {
            "AGENTO11Y_GRAFANA_URL": "https://test.grafana.net",
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": "test-only",
            "AGENTO11Y_ENDPOINT": "https://ingest.example",
            "AGENTO11Y_AUTH_TENANT_ID": "test",
            "AGENTO11Y_AUTH_TOKEN": "test-only",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(experiments, "agent_version", return_value="sha"),
        ):
            for model in ("claude-test", "anthropic/claude-test", "openai/gpt-test"):
                with self.subTest(model=model), self.assertRaisesRegex(ValueError, "ANTHROPIC"):
                    experiments.environment(options(model=model))
                os.environ["ANTHROPIC_API_KEY"] = "test-only"
                experiments.environment(options(model=model))
                del os.environ["ANTHROPIC_API_KEY"]

    def test_blank_trial_count_falls_back_to_three(self) -> None:
        argv = ["experiments.py", "--name", "baseline"]
        with patch.dict(os.environ, {"EXPERIMENT_TRIALS": " "}), patch("sys.argv", argv):
            self.assertEqual(experiments.arguments().trials, 3)

    def test_missing_command_reports_what_to_install(self) -> None:
        with (
            patch("sys.argv", ["experiments.py", "--name", "baseline", "--model", "m"]),
            patch.object(experiments, "validate", side_effect=FileNotFoundError(2, "x", "uv")),
            self.assertRaisesRegex(SystemExit, "command not found: uv"),
        ):
            experiments.main()

    def test_other_missing_files_are_not_reported_as_missing_tools(self) -> None:
        missing = FileNotFoundError(2, "No such file or directory", "/bench/tasks-spec/x.yaml")
        with (
            patch("sys.argv", ["experiments.py", "--name", "baseline", "--model", "m"]),
            patch.object(experiments, "validate", side_effect=missing),
            self.assertRaises(SystemExit) as error,
        ):
            experiments.main()
        self.assertNotIn("install uv", str(error.exception))
        self.assertIn("tasks-spec/x.yaml", str(error.exception))

    def test_suite_sync_refuses_uncommitted_bench_changes(self) -> None:
        argv = ["experiments.py", "--name", "baseline", "--sync-suite"]
        with (
            patch("sys.argv", argv),
            patch.object(experiments, "validate"),
            patch("experiments.subprocess.check_output", return_value=" M tasks-spec/x.yaml\n"),
            patch("experiments.subprocess.run") as run,
            self.assertRaisesRegex(SystemExit, "uncommitted changes"),
        ):
            experiments.main()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
