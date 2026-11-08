"""Contract checks for the k6 task runner's job naming and pass history."""

import argparse
import unittest
from pathlib import Path
from unittest.mock import patch

import runner


def make_runner(run_id: str = "r1") -> runner.Runner:
    args = argparse.Namespace(
        bench_repo=Path("/bench"), name="smoke", model="m", tasks_dir=Path("/t"),
        jobs_dir=Path("/j"), agent_env=[], run_id=run_id,
    )  # fmt: skip
    with patch.object(runner.Runner, "load_specs", return_value=[{"id": "a"}, {"id": "b"}]):
        return runner.Runner(args)


class RunnerTests(unittest.TestCase):
    def test_job_names_are_unique_per_invocation(self) -> None:
        with patch("runner.subprocess.run") as run, patch("runner.read_trial") as read:
            read.return_value = {"passed": True}
            run.return_value.returncode = 0
            first = make_runner()
            second = make_runner("r2")
            first.run("a", 1)
            second.run("a", 1)
        names = [call.args[0][call.args[0].index("--job-name") + 1] for call in run.call_args_list]
        self.assertEqual(len(set(names)), 2)
        self.assertIn("r1", names[0])

    def test_failed_jobs_count_as_failed_trials(self) -> None:
        instance = make_runner()
        with patch("runner.subprocess.run") as run:
            run.return_value.returncode = 1
            with self.assertRaises(RuntimeError):
                instance.run("a", 1)
        self.assertEqual(instance.history, {"a": [False]})

    def test_unreadable_results_count_as_failed_trials(self) -> None:
        instance = make_runner()
        with (
            patch("runner.subprocess.run") as run,
            patch("runner.read_trial", side_effect=ValueError("no reward")),
        ):
            run.return_value.returncode = 0
            with self.assertRaises(ValueError):
                instance.run("a", 1)
        self.assertEqual(instance.history, {"a": [False]})

    def test_unknown_tasks_are_not_recorded(self) -> None:
        instance = make_runner()
        with self.assertRaises(ValueError):
            instance.run("nope", 1)
        self.assertEqual(instance.history, {})


if __name__ == "__main__":
    unittest.main()
