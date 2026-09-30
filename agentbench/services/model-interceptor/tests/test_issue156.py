"""Opt-in, offline Docker regression for native loopback communication.

Set ABB_LOOPBACK_TEST_IMAGE to a built interceptor image. The checkout's source
is mounted over its installed implementation; no image rebuild or API key needed.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid


@unittest.skipUnless(os.environ.get("ABB_LOOPBACK_TEST_IMAGE"), "Requires Docker and an interceptor image")
class LoopbackAcceptanceTest(unittest.TestCase):
    def test_local_transport_and_external_boundary(self):
        image = os.environ["ABB_LOOPBACK_TEST_IMAGE"]
        service = Path(__file__).resolve().parents[1]
        name = "abb-loopback-" + uuid.uuid4().hex[:12]

        def docker(*args, check=True):
            return subprocess.run(["docker", *args], capture_output=True, text=True,
                                  timeout=60, check=check)

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"agent_id": "loopback-test", "mode": "observe", "max_trace_bytes": 1048576,
                                         "credentials": [], "routes": [], "tool_routes": []}))
            try:
                docker("network", "create", "--internal", name)
                gateway = json.loads(docker("network", "inspect", name).stdout)[0]["IPAM"]["Config"][0]["Gateway"]
                docker("run", "-d", "--name", name, "--network", name,
                       "--cap-drop=ALL", "--cap-add=NET_ADMIN", "--cap-add=NET_RAW",
                       "--security-opt=no-new-privileges", "--read-only", "--tmpfs=/tmp",
                       "--tmpfs=/run/defuzex", "--mount",
                       f"type=bind,source={config},target=/run/secrets/interceptor_config,readonly",
                       "--mount", f"type=bind,source={service},target=/work,readonly",
                       "-e", "PYTHONPATH=/work/src", image)
                for _ in range(100):
                    logs = docker("logs", name).stdout
                    if "interceptor_ready" in logs:
                        break
                    time.sleep(0.1)
                else:
                    self.fail("Interceptor did not start: " + docker("logs", name).stderr)
                probe = docker("run", "--rm", "--user=1000:1000", "--cap-drop=ALL",
                               "--security-opt=no-new-privileges", "--network", "container:" + name,
                               "-e", "ABB_EXTERNAL_TEST_HOST=" + gateway,
                               "--mount", f"type=bind,source={service},target=/work,readonly",
                               "--entrypoint=python", image,
                               "/work/tests/fixtures/loopback_probe.py", check=False)
                print(probe.stdout + probe.stderr, flush=True)
                self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
                logs = docker("logs", name).stdout
                self.assertNotIn('"event": "tool_request"', logs)
            finally:
                docker("rm", "-f", name, check=False)
                docker("network", "rm", name, check=False)


if __name__ == "__main__":
    unittest.main()
