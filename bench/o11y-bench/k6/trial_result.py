"""Read one graded Harbor trial into the JSON the k6 script records."""

import json
import sys
from pathlib import Path
from typing import Any


def use_bench_repo(bench_repo: Path) -> None:
    """Makes o11y-bench's own grading and reporting modules importable."""
    if str(bench_repo) not in sys.path:
        sys.path.insert(0, str(bench_repo))


def trial_dir(job_dir: Path) -> Path:
    """The single trial directory a one-task, one-attempt Harbor job writes."""
    found = sorted(path.parent for path in job_dir.glob("*__*/result.json"))
    if len(found) != 1:
        raise ValueError(f"expected one graded trial under {job_dir}, found {len(found)}")
    return found[0]


def explanation(details: dict[str, Any]) -> str:
    """The verifier's per-criterion explanations, one per line."""
    lines = [
        str(value)
        for key, value in details.items()
        if str(key).startswith("explanation:") and value
    ]
    return "\n".join(lines)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def model_ref(result: dict[str, Any], fallback: str) -> dict[str, str]:
    info = (result.get("agent_info") or {}).get("model_info") or {}
    name = str(info.get("name") or fallback)
    provider = str(info.get("provider") or "")
    if "/" in name:
        embedded, name = name.split("/", 1)
        provider = provider or embedded
    return {"provider": provider or "unknown", "name": name}


def final_output(agent_dir: Path) -> str:
    from grading.transcript_parser import parse_transcript

    for message in reversed(parse_transcript(agent_dir).messages):
        if message.role == "assistant" and message.content:
            return message.content
    return ""


def read_trial(job_dir: Path, model: str) -> dict[str, Any]:
    """Grade outcome and usage of the job's trial, using o11y-bench's own definitions."""
    from reporting.report_data import agent_result_metrics, agent_seconds, reward_counts_as_pass

    directory = trial_dir(job_dir)
    result = read_json(directory / "result.json")
    reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    if reward is None:
        raise ValueError(f"{directory.name} has no verifier reward; see {directory}")
    cost, input_tokens, cache_tokens, output_tokens = agent_result_metrics(result)
    details = read_json(directory / "verifier" / "grading_details.json")
    return {
        "reward": float(reward),
        "passed": reward_counts_as_pass(result),
        "explanation": explanation(details),
        "final_output": final_output(directory / "agent"),
        "model": model_ref(result, model),
        "cost": cost if cost > 0 else None,
        "input_tokens": input_tokens + cache_tokens,
        "output_tokens": output_tokens,
        "duration_ms": int(agent_seconds(result) * 1000),
        "harbor_trial": directory.name,
    }
