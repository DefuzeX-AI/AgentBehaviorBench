"""Unit-local model setup must preserve native behavior and credential boundaries."""
import importlib.util
import json
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "resources/agents/116-icode/bootstrap/launch.py"
spec = importlib.util.spec_from_file_location("icode_launcher", PATH)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.env = {"ABB_AGENT_MODEL_PROVIDER": "deepseek", "ABB_AGENT_MODEL": "unit-test-model",
                    "ABB_AGENT_MODEL_BASE_URL": "https://provider.example/v1",
                    "ABB_AGENT_MODEL_API_KEY": "unit-test-credential", "HTTPS_PROXY": "http://proxy:80",
                    "SSL_CERT_FILE": "/tmp/abb-ca.pem", "NO_PROXY": "localhost"}

    def test_native_entrypoint_and_no_secret_on_disk_or_argv(self):
        command, env, profile = launcher.prepare(self.env, Path("/tmp/case-home"))
        self.assertEqual(command, ["/opt/icode-venv/bin/icode", "acp", "--agent", "Code", "--approval", "manual",
                                   "--workdir", "/home/agent/workspace"])
        self.assertNotIn(self.env["ABB_AGENT_MODEL_API_KEY"], json.dumps([command, profile]))
        self.assertEqual(profile["api_key"], "{{ABB_AGENT_MODEL_API_KEY}}")
        self.assertEqual(env["ABB_AGENT_MODEL_API_KEY"], self.env["ABB_AGENT_MODEL_API_KEY"])
        self.assertEqual(profile["model_id"], self.env["ABB_AGENT_MODEL"])
        self.assertEqual(profile["base_url"], self.env["ABB_AGENT_MODEL_BASE_URL"])

    def test_preserves_proxy_ca_and_native_defaults(self):
        _, env, profile = launcher.prepare(self.env, Path("/tmp/case-home"))
        for key in ("HTTPS_PROXY", "SSL_CERT_FILE", "NO_PROXY"):
            self.assertEqual(env[key], self.env[key])
        self.assertFalse({"bypass_proxy", "http_max_retries", "max_output_tokens", "chat_options"} & profile.keys())

    def test_native_providers(self):
        for provider, expected in launcher.PROVIDERS.items():
            with self.subTest(provider=provider):
                _, _, profile = launcher.prepare({**self.env, "ABB_AGENT_MODEL_PROVIDER": provider}, Path("/tmp/home"))
                self.assertEqual(profile["provider"], expected)
                self.assertEqual(profile["api_style"], "chat_completions")

    def test_fresh_home_and_profile_pointer(self):
        for value in ("/tmp/case-a", "/tmp/case-b"):
            _, env, _ = launcher.prepare(self.env, Path(value))
            self.assertEqual(env["HOME"], str(Path(value)))
            self.assertEqual(env["CHRYS_MODEL_PROFILE"], launcher.PROFILE_ID)

    def test_rejects_missing_selection(self):
        for key in launcher.REQUIRED:
            with self.subTest(key=key), self.assertRaises(ValueError):
                launcher.prepare({**self.env, key: ""}, Path("/tmp/home"))

    def test_rejects_unsafe_endpoint(self):
        for value in ("http://provider.example", "https://u:p@provider.example", "https://provider.example?key=x",
                      "https://provider.example/#x", "https:///missing-host"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                launcher.prepare({**self.env, "ABB_AGENT_MODEL_BASE_URL": value}, Path("/tmp/home"))

    def test_rejects_unknown_provider(self):
        with self.assertRaises(ValueError):
            launcher.prepare({**self.env, "ABB_AGENT_MODEL_PROVIDER": "unknown"}, Path("/tmp/home"))


if __name__ == "__main__":
    unittest.main()
