"""Contract checks for reading a graded Harbor trial for k6."""

import json
import tempfile
import unittest
from pathlib import Path

import trial_result


class TrialResultTests(unittest.TestCase):
    def test_explanation_joins_only_nonblank_criterion_explanations(self) -> None:
        details = {"score": 1.0, "explanation:a": "first", "explanation:b": "", "explanation:c": "third"}
        self.assertEqual(trial_result.explanation(details), "first\nthird")

    def test_model_ref_splits_an_embedded_provider(self) -> None:
        result = {"agent_info": {"model_info": {"name": "anthropic/claude-test"}}}
        self.assertEqual(
            trial_result.model_ref(result, "fallback"),
            {"provider": "anthropic", "name": "claude-test"},
        )

    def test_model_ref_falls_back_to_the_requested_model(self) -> None:
        self.assertEqual(
            trial_result.model_ref({}, "claude-test"),
            {"provider": "unknown", "name": "claude-test"},
        )

    def test_trial_dir_requires_exactly_one_graded_trial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp)
            with self.assertRaises(ValueError):
                trial_result.trial_dir(job)
            (job / "task__abc").mkdir()
            (job / "task__abc" / "result.json").write_text("{}")
            self.assertEqual(trial_result.trial_dir(job), job / "task__abc")
            (job / "task__def").mkdir()
            (job / "task__def" / "result.json").write_text("{}")
            with self.assertRaises(ValueError):
                trial_result.trial_dir(job)

    def test_read_json_ignores_missing_and_malformed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("not json")
            self.assertEqual(trial_result.read_json(bad), {})
            self.assertEqual(trial_result.read_json(Path(tmp) / "missing.json"), {})
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps({"a": 1}))
            self.assertEqual(trial_result.read_json(good), {"a": 1})


if __name__ == "__main__":
    unittest.main()
