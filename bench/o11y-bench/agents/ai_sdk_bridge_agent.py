"""Harbor adapter that runs the Go AI SDK WatcherBench binary."""

import os
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from harbor.agents.base import BaseAgent
from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


VIEWER_STDOUT = "/logs/agent/command-0/stdout.txt"


def normalize_model(model_name: str | None) -> str:
    return model_name or os.environ.get("MODEL", "anthropic/claude-sonnet-4-6")


def binary_path() -> Path:
    configured = os.environ.get("WATCHERBENCH_BINARY", "dist/watcherbench-linux-arm64")
    return Path(configured).resolve()


def select_mcp_url(mcp_servers: list[Any]) -> str:
    for server in mcp_servers:
        raw = getattr(server, "url", "")
        host = (urlparse(raw).hostname or "").lower()
        if raw and host not in {"localhost", "127.0.0.1", "::1"}:
            return raw
    return os.environ.get("MCP_URL", "")


def runner_command() -> str:
    command = (
        "set -o pipefail; mkdir -p /logs/agent/command-0; "
        "/app/watcherbench bench-agent "
        "--instruction /app/instruction.txt "
        '--model "$MODEL" '
        '--mcp-url "$MCP_URL" '
        "2>&1 | tee " + shlex.quote(VIEWER_STDOUT)
    )
    return "bash -lc " + shlex.quote(command)


class AiSdkBridgeAgent(BaseAgent):
    """Runs the Go AI SDK agent inside an o11y-bench task container."""

    def __init__(
        self,
        logs_dir: Path,
        model_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(logs_dir=logs_dir, model_name=model_name, **kwargs)

    @staticmethod
    def name() -> str:
        return "watcherbench-ai-sdk"

    def version(self) -> str:
        return "0.1.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        binary = binary_path()
        if not binary.exists():
            raise FileNotFoundError(f"missing WatcherBench binary: {binary}")
        await environment.upload_file(source_path=binary, target_path="/app/watcherbench")
        await environment.exec(command="chmod +x /app/watcherbench")

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        instruction_path = self.logs_dir / "instruction.txt"
        instruction_path.write_text(instruction)
        await environment.upload_file(source_path=instruction_path, target_path="/app/instruction.txt")
        result = await environment.exec(command=runner_command(), env=self.env())
        context.metadata = {**(context.metadata or {}), "agent": self.name()}
        if result.return_code != 0:
            raise NonZeroAgentExitCodeError(f"agent exited with code {result.return_code}")

    def env(self) -> dict[str, str]:
        env = {
            "MODEL": normalize_model(self.model_name),
            "MCP_URL": select_mcp_url(self.mcp_servers),
        }
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        # The container cannot run the browser OAuth login, so forward a
        # short-lived access token minted on the host (`watcherbench mcp-token`).
        # Only send it to the server it was minted for, never to a
        # task-provided MCP URL.
        mcp_token = os.environ.get("MCP_ACCESS_TOKEN")
        if mcp_token and env["MCP_URL"] and env["MCP_URL"] == os.environ.get("MCP_URL"):
            env["MCP_ACCESS_TOKEN"] = mcp_token
        return env

