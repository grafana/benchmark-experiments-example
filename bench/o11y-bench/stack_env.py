"""Grafana Cloud stack and credential settings shared by the experiment commands."""

import os
import re
from urllib.parse import urlparse


def cloud_url(env: dict[str, str]) -> str:
    configured = env.get("AGENTO11Y_GRAFANA_URL", "").strip()
    if configured:
        parsed = urlparse(configured)
        if (
            parsed.scheme != "https"
            or not re.fullmatch(r"[a-zA-Z0-9.-]+", parsed.hostname or "")
            or "@" in parsed.netloc
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("AGENTO11Y_GRAFANA_URL must be an absolute HTTPS stack URL")
        return configured.rstrip("/")
    mcp = urlparse(env.get("MCP_URL", ""))
    stack = mcp.path.removeprefix("/mcp/").strip("/")
    if mcp.hostname == "mcp.grafana.com" and re.fullmatch(r"[a-zA-Z0-9-]+\.grafana\.net", stack):
        return f"https://{stack}"
    raise ValueError("set AGENTO11Y_GRAFANA_URL to the Grafana Cloud stack URL")


def nonblank(env: dict[str, str], key: str, default: str) -> str:
    """Like setdefault, but a key that .env defines as blank also gets the default."""
    return env.get(key, "").strip() or default


def require_resolved(env: dict[str, str], keys: tuple[str, ...]) -> None:
    for key in keys:
        value = env.get(key, "").strip()
        if not value or value.startswith("op://"):
            raise ValueError(f"{key} must be resolved; use op run --env-file=.env")


def suite_environment() -> dict[str, str]:
    """Only what publishing the suite needs: the stack and its service account."""
    env = dict(os.environ)
    url = cloud_url(env)
    env["AGENTO11Y_GRAFANA_URL"] = url
    env["AGENTO11Y_CONTROL_ENDPOINT"] = nonblank(
        env, "AGENTO11Y_CONTROL_ENDPOINT", url + "/a/grafana-agento11y-app"
    )
    env["AGENTO11Y_SERVICE_ACCOUNT_TOKEN"] = nonblank(
        env,
        "AGENTO11Y_SERVICE_ACCOUNT_TOKEN",
        env.get("GRAFANA_SERVICE_ACCOUNT_TOKEN", "").strip(),
    )
    env["AGENTO11Y_SUITE_ID"] = nonblank(env, "AGENTO11Y_SUITE_ID", "watcherbench-o11y-bench")
    require_resolved(env, ("AGENTO11Y_SERVICE_ACCOUNT_TOKEN",))
    return env
