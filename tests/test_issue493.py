"""Native setup must isolate credentials and retain model interception boundaries."""
import importlib.util
import json
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "resources/agents/116-synergy/bootstrap/launch.py"
spec = importlib.util.spec_from_file_location("synergy_launcher", path)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.env = {"ABB_AGENT_MODEL": "unit-model", "ABB_AGENT_MODEL_API_KEY": "test-private-credential",
                    "ABB_AGENT_MODEL_BASE_URL": "https://provider.example/v1",
                    "HTTPS_PROXY": "http://proxy:80", "SSL_CERT_FILE": "/tmp/ca.pem", "NO_PROXY": "existing.local"}

    def test_native_cli(self):
        command, _, _ = launcher.prepare(self.env, Path("/tmp/case-home"))
        self.assertEqual(command, ["bun", "/opt/agent/bootstrap/acp.ts", "acp",
            "--cwd", "/home/agent/workspace", "--hostname", "127.0.0.1", "--port", "0"])

    def test_no_secret_in_profile_or_argv(self):
        command, child, docs = launcher.prepare(self.env, Path("/tmp/case-home"))
        self.assertNotIn(self.env["ABB_AGENT_MODEL_API_KEY"], json.dumps([command, docs]))
        p = docs["20-providers.jsonc"]["provider"]["abb"]
        self.assertEqual(p["options"]["apiKey"], "{env:ABB_AGENT_MODEL_API_KEY}")
        self.assertEqual(child["ABB_AGENT_MODEL_API_KEY"], self.env["ABB_AGENT_MODEL_API_KEY"])
        self.assertEqual(p["options"]["baseURL"], self.env["ABB_AGENT_MODEL_BASE_URL"])
        self.assertEqual(docs["10-models.jsonc"]["model"], "abb/unit-model")

    def test_preserves_proxy_and_ca_with_only_loopback_added(self):
        _, child, _ = launcher.prepare(self.env, Path("/tmp/home"))
        self.assertEqual(child["HTTPS_PROXY"], self.env["HTTPS_PROXY"])
        self.assertEqual(child["SSL_CERT_FILE"], self.env["SSL_CERT_FILE"])
        self.assertEqual(set(child["NO_PROXY"].split(",")), {"existing.local", "127.0.0.1", "localhost"})
        self.assertNotIn("provider.example", child["NO_PROXY"])

    def test_keeps_native_guarded_and_forge(self):
        _, _, docs = launcher.prepare(self.env, Path("/tmp/home"))
        self.assertEqual(docs["60-agents.jsonc"], {"default_agent": "forge"})
        self.assertEqual(docs["80-permissions.jsonc"], {"controlProfile": "guarded", "sandbox": {"enabled": False}})
        self.assertNotIn("tools", docs["80-permissions.jsonc"])
        self.assertNotIn("permission", docs["80-permissions.jsonc"])

    def test_isolated_native_home(self):
        for name in ("case-a", "case-b"):
            home = Path("/home/agent") / name
            _, child, _ = launcher.prepare(self.env, home)
            self.assertEqual(child["HOME"], str(home))
            self.assertEqual(child["SYNERGY_HOME"], str(home))

    def test_rejects_missing_selection(self):
        for key in launcher.REQUIRED:
            with self.subTest(key=key), self.assertRaises(ValueError):
                launcher.prepare({**self.env, key: ""}, Path("/tmp/home"))

    def test_rejects_unsafe_endpoint(self):
        for value in ("http://provider.example", "https://u:p@provider.example", "https://provider.example?key=x", "https://provider.example/#x", "https:///no-host"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                launcher.prepare({**self.env, "ABB_AGENT_MODEL_BASE_URL": value}, Path("/tmp/home"))


if __name__ == "__main__":
    unittest.main()
