"""Contract checks for the k6 offline eval launcher."""

import argparse
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import k6_evals


def options(**overrides: object) -> argparse.Namespace:
    values = dict(
        name="baseline",
        bench_repo=Path("/bench"),
        model="claude-test",
        task=["promql-error-rate"],
        trials=3,
        suite_version="",
        port=8098,
        publish=False,
        dry_run=False,
        sync_suite=False,
        concurrency=1,
    )
    return argparse.Namespace(**(values | overrides))


class K6EvalsTests(unittest.TestCase):
    def test_trials_default_to_three_and_accept_environment_override(self) -> None:
        argv = ["k6_evals.py", "--name", "baseline"]
        with patch.dict(os.environ, {}, clear=True), patch("sys.argv", argv):
            self.assertEqual(k6_evals.arguments().trials, 3)
        with patch.dict(os.environ, {"EXPERIMENT_TRIALS": "5"}, clear=True), patch("sys.argv", argv):
            self.assertEqual(k6_evals.arguments().trials, 5)

    def test_publishing_is_opt_in(self) -> None:
        argv = ["k6_evals.py", "--name", "baseline"]
        with patch.dict(os.environ, {}, clear=True), patch("sys.argv", argv):
            self.assertFalse(k6_evals.arguments().publish)
        with patch.dict(os.environ, {}, clear=True), patch("sys.argv", [*argv, "--publish"]):
            self.assertTrue(k6_evals.arguments().publish)

    def test_runner_gets_a_provider_qualified_model_and_the_run_label(self) -> None:
        command = k6_evals.runner_command(options())
        self.assertEqual(command[command.index("--model") + 1], "anthropic/claude-test")
        self.assertEqual(command[command.index("--name") + 1], "baseline")
        self.assertEqual(command[command.index("--port") + 1], "8098")

    def test_runner_keeps_a_provider_that_the_model_already_names(self) -> None:
        command = k6_evals.runner_command(options(model="openai/gpt-test"))
        self.assertEqual(command[command.index("--model") + 1], "openai/gpt-test")

    def test_experiment_ids_carry_name_and_trial_count(self) -> None:
        self.assertRegex(k6_evals.experiment_id(options()), r"^k6-baseline-k3-\d{14}$")

    def test_local_environment_selects_tasks_without_publishing(self) -> None:
        env = {"ANTHROPIC_API_KEY": "key"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("k6_evals.experiments.agent_version", return_value="sha"),
        ):
            result = k6_evals.k6_environment(options(task=["a", "b"]))
        self.assertEqual(result["EXPERIMENT_PUBLISH"], "false")
        self.assertEqual(result["EXPERIMENT_TASKS"], "a b")
        self.assertEqual(result["O11Y_BENCH_SHA"], "sha")
        self.assertEqual(result["RUNNER_URL"], "http://127.0.0.1:8098")

    def test_local_environment_refuses_an_unresolved_grader_key(self) -> None:
        env = {"ANTHROPIC_API_KEY": "op://vault/item/field"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("k6_evals.experiments.agent_version", return_value="sha"),
            self.assertRaisesRegex(ValueError, "op run"),
        ):
            k6_evals.k6_environment(options())


if __name__ == "__main__":
    unittest.main()
