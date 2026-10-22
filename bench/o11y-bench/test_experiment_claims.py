"""Resume checks: a name stays bound to one configuration once Harbor starts."""

import contextlib
import json
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import experiments
from test_experiments import RUN_ENV, options

JOB = Path("jobs/experiments/watcherbench-baseline-k3")


class ClaimTests(unittest.TestCase):
    @contextlib.contextmanager
    def root(self) -> Iterator[Path]:
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

    def test_removing_local_job_artifacts_does_not_release_the_cloud_run_name(self) -> None:
        inputs = experiments.run_inputs(options(), RUN_ENV)
        with self.root() as root:
            experiments.record_claim(options(), inputs)
            (root / JOB).mkdir(parents=True)
            (root / JOB).rmdir()
            experiments.check_claim(options(), inputs)
            for changed in (inputs | {"model": "other"}, inputs | {"tasks": []}):
                with (
                    self.subTest(changed=changed),
                    self.assertRaisesRegex(ValueError, "new --name"),
                ):
                    experiments.check_claim(options(), changed)

    def test_fresh_name_without_claim_or_job_is_allowed(self) -> None:
        with self.root():
            experiments.check_claim(options(), experiments.run_inputs(options(), RUN_ENV))

    def test_malformed_claim_is_refused(self) -> None:
        with self.root():
            path = experiments.claim_path(options())
            path.parent.mkdir(parents=True)
            path.write_text("[]")
            with self.assertRaisesRegex(ValueError, "invalid recorded run inputs"):
                experiments.check_claim(options(), experiments.run_inputs(options(), RUN_ENV))

    def test_job_dir_without_record_is_refused(self) -> None:
        with self.root() as root:
            (root / JOB).mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "delete that directory.*existing Cloud"):
                experiments.check_claim(options(), experiments.run_inputs(options(), RUN_ENV))

    def test_legacy_record_inside_job_dir_still_guards_resume(self) -> None:
        inputs = experiments.run_inputs(options(), RUN_ENV)
        with self.root() as root:
            (root / JOB).mkdir(parents=True)
            (root / JOB / "inputs.json").write_text(json.dumps(inputs))
            experiments.check_claim(options(), inputs)
            with self.assertRaisesRegex(ValueError, "model"):
                experiments.check_claim(options(), inputs | {"model": "other"})

    def test_corrupt_record_names_the_file(self) -> None:
        with self.root():
            path = experiments.claim_path(options())
            path.parent.mkdir(parents=True)
            path.write_text('{"model": ')
            with self.assertRaisesRegex(ValueError, f"invalid recorded run inputs in {path}"):
                experiments.check_claim(options(), experiments.run_inputs(options(), RUN_ENV))

    def test_record_is_replaced_atomically(self) -> None:
        inputs = experiments.run_inputs(options(), RUN_ENV)
        with self.root():
            experiments.record_claim(options(), inputs)
            path = experiments.claim_path(options())
            self.assertEqual(json.loads(path.read_text()), inputs)
            self.assertEqual([p.name for p in path.parent.iterdir()], [path.name])

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
    def run_experiment_in(self) -> Iterator[MagicMock]:
        env = RUN_ENV | {"AGENTO11Y_SUITE_VERSION": "latest_published"}
        with (
            self.root(),
            patch.object(experiments, "check_tasks"),
            patch.object(experiments, "environment", return_value=dict(env)),
            patch.object(experiments, "resolve_suite_version", return_value="v2"),
            patch("experiments.subprocess.run") as run,
        ):
            yield run


if __name__ == "__main__":
    unittest.main()
