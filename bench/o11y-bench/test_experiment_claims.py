"""Resume checks: a name stays bound to one configuration once Harbor starts."""

import contextlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import experiments
from test_experiments import RUN_ENV, options

JOB = Path("jobs/experiments/watcherbench-baseline-k3")


class ClaimTests(unittest.TestCase):
    @contextlib.contextmanager
    def root(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(experiments, "ROOT", Path(directory)),
        ):
            yield Path(directory)

    def test_resume_rejects_changed_settings_and_names_them(self) -> None:
        inputs = experiments.run_inputs(options(), RUN_ENV)
        with self.root() as root:
            experiments.record_claim(options(), inputs)
            (root / JOB).mkdir(parents=True)
            experiments.check_claim(options(), inputs)
            changed = experiments.run_inputs(options(task=[]), RUN_ENV)
            with self.assertRaisesRegex(ValueError, "tasks: .*new --name"):
                experiments.check_claim(options(), changed)

    def test_record_without_job_dir_means_no_trial_ran(self) -> None:
        inputs = experiments.run_inputs(options(), RUN_ENV)
        with self.root():
            experiments.record_claim(options(), inputs)
            experiments.check_claim(options(), experiments.run_inputs(options(task=[]), RUN_ENV))

    def test_job_dir_without_record_is_refused(self) -> None:
        with self.root() as root:
            (root / JOB).mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "without recorded run inputs"):
                experiments.check_claim(options(), experiments.run_inputs(options(), RUN_ENV))

    def test_legacy_record_inside_job_dir_still_guards_resume(self) -> None:
        inputs = experiments.run_inputs(options(), RUN_ENV)
        with self.root() as root:
            (root / JOB).mkdir(parents=True)
            (root / JOB / "inputs.json").write_text(json.dumps(inputs))
            experiments.check_claim(options(), inputs)
            with self.assertRaisesRegex(ValueError, "model"):
                experiments.check_claim(options(), inputs | {"model": "other"})

    def test_claim_lives_outside_harbor_job_directory(self) -> None:
        with self.root() as root:
            parents = experiments.claim_path(options()).parents
            self.assertNotIn(root / "jobs" / "experiments", parents)

    def test_record_is_written_before_harbor_starts(self) -> None:
        with self.run_experiment_in() as run:
            seen = []

            def harbor(command: list[str], **_: object) -> None:
                if command == ["job"]:
                    seen.append(json.loads(experiments.claim_path(options()).read_text()))

            run.side_effect = harbor
            experiments.run_experiment(options(), [["sync"], ["job"]])
            self.assertEqual(seen[0]["suite_version"], "v2")

    def test_sync_failure_writes_no_record(self) -> None:
        with self.run_experiment_in() as run:
            run.side_effect = subprocess.CalledProcessError(1, "sync_tasks")
            with self.assertRaises(subprocess.CalledProcessError):
                experiments.run_experiment(options(), [["sync"], ["job"]])
            self.assertFalse(experiments.claim_path(options()).exists())

    @contextlib.contextmanager
    def run_experiment_in(self):
        env = RUN_ENV | {"AGENTO11Y_SUITE_VERSION": "latest_published"}
        with (
            self.root(),
            patch.object(experiments, "environment", return_value=dict(env)),
            patch.object(experiments, "resolve_suite_version", return_value="v2"),
            patch("experiments.subprocess.run") as run,
        ):
            yield run


if __name__ == "__main__":
    unittest.main()
