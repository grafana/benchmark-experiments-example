"""Stack URL derivation and validation."""

import unittest

from stack_env import cloud_url

MCP = "https://mcp.grafana.com/mcp/test.grafana.net"


class StackUrlTests(unittest.TestCase):
    def test_stack_url_comes_from_configured_hosted_mcp(self) -> None:
        for mcp in (MCP, MCP + "/"):
            with self.subTest(mcp=mcp):
                self.assertEqual(cloud_url({"MCP_URL": mcp}), "https://test.grafana.net")
        self.assertEqual(
            cloud_url({"AGENTO11Y_GRAFANA_URL": "", "MCP_URL": MCP}), "https://test.grafana.net"
        )
        for bad in ("http://private/mcp", "https://mcp.grafana.com/test.grafana.net"):
            with self.subTest(mcp=bad), self.assertRaises(ValueError):
                cloud_url({"MCP_URL": bad})

    def test_configured_url_must_be_a_bare_https_stack(self) -> None:
        self.assertEqual(
            cloud_url({"AGENTO11Y_GRAFANA_URL": "https://test.grafana.net/"}),
            "https://test.grafana.net",
        )
        for bad in (
            "http://example",
            "https://<your-stack>.grafana.net",
            "https://test.grafana.net/a/grafana-agento11y-app",
            "https://:secret@test.grafana.net",
            "https://user@test.grafana.net",
        ):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                cloud_url({"AGENTO11Y_GRAFANA_URL": bad})


if __name__ == "__main__":
    unittest.main()
