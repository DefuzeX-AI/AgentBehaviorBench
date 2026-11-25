"""ACP transport through Home Assistant's native onboarding and conversation APIs."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
from uuid import uuid4

import httpx
import aiohttp
from acp import Agent, InitializeResponse, NewSessionResponse, PromptResponse, run_agent, update_agent_message_text
from acp.schema import AgentCapabilities, Implementation, TextContentBlock



def startup_error(reason, paths, environment, extra_secrets=()):
    """Retain bounded native startup evidence after container teardown."""
    parts = []
    for path in paths:
        if path.is_file():
            parts.append(path.name + ":\n" + path.read_text(errors="replace")[-4000:])
    memory_events = Path("/sys/fs/cgroup/memory.events")
    if memory_events.is_file():
        parts.append("memory.events:\n" + memory_events.read_text())
    text = "\n".join(parts)[-12000:]
    values = list(extra_secrets) + [v for k, v in environment.items()
        if any(word in k.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET", "PASS"))]
    for value in sorted(set(str(v) for v in values if v and len(str(v)) >= 6), key=len, reverse=True):
        text = text.replace(value, "[redacted]")
    return RuntimeError(reason + ("\nNative logs:\n" + text if text else ""))

class HomeAgent(Agent):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.tasks = {}
        self.process = None

    def on_connect(self, conn):
        self.conn = conn

    async def initialize(self, protocol_version, client_capabilities, client_info=None):
        return InitializeResponse(protocolVersion=protocol_version,
            agentInfo=Implementation(name="Home Generative Agent native API transport", version="1"),
            agentCapabilities=AgentCapabilities())

    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        if mcp_servers:
            raise ValueError("External ACP MCP provisioning is unavailable")
        if self.process is None:
            state = Path.home()/"hga-state"
            state.mkdir(exist_ok=True)
            shutil.copytree("/opt/native-custom-components", state/"custom_components", dirs_exist_ok=True)
            (state/"configuration.yaml").write_text("default_config:\nhttp:\n  server_host: 127.0.0.1\n")
            self.log = (state/"native-server.log").open("w")
            self.process = await asyncio.create_subprocess_exec(sys.executable, "-m", "homeassistant", "--config", str(state),
                env=dict(os.environ, TIKTOKEN_CACHE_DIR="/opt/tiktoken"),
                stdout=self.log, stderr=asyncio.subprocess.STDOUT)
            self.client = httpx.AsyncClient(base_url="http://127.0.0.1:8123", trust_env=False, timeout=60)
            for _ in range(180):
                if self.process.returncode is not None:
                    raise startup_error("Home Assistant exited", [state/"native-server.log"], os.environ)
                try:
                    response = await self.client.get("/api/onboarding")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(1)
            else:
                raise startup_error("Home Assistant startup deadline exceeded", [state/"native-server.log"], os.environ)
            client_id = "http://127.0.0.1:8123/"
            signup = await self.request("/api/onboarding/users", {"name": "ABB local owner", "username": "abb-local",
                "password": secrets.token_urlsafe(24), "client_id": client_id, "language": "en"})
            token = await self.client.post("/auth/token", data={"grant_type": "authorization_code",
                "code": signup["auth_code"], "client_id": client_id})
            token.raise_for_status()
            self.client.headers["Authorization"] = "Bearer " + token.json()["access_token"]
            flow = await self.request("/api/config/config_entries/flow", {"handler": "home_generative_agent", "show_advanced_options": True})
            if flow["type"] == "form":
                flow = await self.request("/api/config/config_entries/flow/"+flow["flow_id"], {})
            if flow["type"] != "create_entry":
                raise RuntimeError("Native HGA configuration failed: " + json.dumps(flow))
            entries = await self.client.get("/api/config/config_entries/entry")
            entries.raise_for_status()
            self.entry_id = next(e["entry_id"] for e in entries.json() if e["domain"] == "home_generative_agent")
            prefix = "/api/config/config_entries/subentries/flow"
            flow = await self.request(prefix, {"handler": [self.entry_id, "model_provider"]})
            choices = {"deployment": {"deployment": "edge"},
                "provider": {"provider_type": "openai_compatible", "name": "Configured model endpoint"},
                "settings": {"base_url": os.environ["ABB_AGENT_MODEL_BASE_URL"], "api_key": os.environ["ABB_AGENT_MODEL_API_KEY"]}}
            for _ in range(6):
                if flow["type"] == "create_entry":
                    break
                if flow.get("errors") or flow.get("step_id") not in choices:
                    raise RuntimeError("Native HGA provider configuration refused: " + str(flow.get("errors") or flow.get("step_id")))
                flow = await self.request(prefix+"/"+flow["flow_id"], choices[flow["step_id"]])
            else:
                raise RuntimeError("Native HGA provider flow did not finish")
            # Model selection belongs to the native Conversation feature subentry.
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect("http://127.0.0.1:8123/api/websocket") as ws:
                    if (await ws.receive_json(timeout=15)).get("type") != "auth_required":
                        raise RuntimeError("Unexpected native Home Assistant auth handshake")
                    await ws.send_json({"type": "auth", "access_token": token.json()["access_token"]})
                    if (await ws.receive_json(timeout=15)).get("type") != "auth_ok":
                        raise RuntimeError("Native Home Assistant websocket authentication failed")
                    await ws.send_json({"id": 1, "type": "config_entries/subentries/list", "entry_id": self.entry_id})
                    listed = await ws.receive_json(timeout=15)
                    if not listed.get("success"):
                        raise RuntimeError("Native Home Assistant subentry listing failed")
            subentries = listed["result"]
            provider = next(s for s in subentries if s["subentry_type"] == "model_provider")
            conversation = next(s for s in subentries if s["subentry_type"] == "feature"
                and s.get("unique_id") == self.entry_id + "_conversation")
            flow = await self.request(prefix, {"handler": [self.entry_id, "feature"],
                "subentry_id": conversation["subentry_id"]})
            for _ in range(4):
                if flow["type"] == "abort" and flow.get("reason") == "reconfigure_successful":
                    break
                if flow.get("errors") or flow.get("step_id") not in ("feature_provider", "feature_model"):
                    raise RuntimeError("Native HGA conversation configuration refused: " + str(flow.get("errors") or flow.get("reason") or flow.get("step_id")))
                # Preserve rendered native model defaults and every unrelated option.
                values = {f["name"]: f["default"] for f in flow.get("data_schema", []) if "default" in f}
                if flow["step_id"] == "feature_provider":
                    values["model_provider_id"] = provider["subentry_id"]
                else:
                    values["model_name"] = os.environ["ABB_AGENT_MODEL"]
                flow = await self.request(prefix+"/"+flow["flow_id"], values)
            else:
                raise RuntimeError("Native HGA conversation configuration did not finish")
            await self.request(f"/api/config/config_entries/entry/{self.entry_id}/reload", {})
            for _ in range(120):
                states = await self.client.get("/api/states")
                states.raise_for_status()
                candidates = [row["entity_id"] for row in states.json()
                    if row["entity_id"].startswith("conversation.") and "generative" in row["entity_id"] and row["state"] != "unavailable"]
                if candidates:
                    self.agent_id = candidates[0]
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Native HGA conversation entity did not become available")
        session = uuid4().hex
        self.sessions[session] = None
        return NewSessionResponse(sessionId=session)

    async def request(self, path, data):
        response = await self.client.post(path, json=data)
        response.raise_for_status()
        return response.json()

    async def prompt(self, prompt, session_id, **kwargs):
        if session_id not in self.sessions or session_id in self.tasks:
            raise ValueError("Unknown or busy session")
        if any(not isinstance(block, TextContentBlock) for block in prompt):
            raise ValueError("Only text input is supported")
        self.tasks[session_id] = asyncio.current_task()
        try:
            payload = {"text": ''.join(block.text for block in prompt), "language": "zh", "agent_id": self.agent_id}
            if self.sessions[session_id]:
                payload["conversation_id"] = self.sessions[session_id]
            result = await self.request("/api/conversation/process", payload)
            print(json.dumps(result, ensure_ascii=False), file=sys.stderr, flush=True)
            if result.get("response", {}).get("response_type") == "error":
                raise RuntimeError("Native HGA conversation returned an error")
            reply = result.get("response", {}).get("speech", {}).get("plain", {}).get("speech")
            if not reply:
                raise RuntimeError("Native HGA returned no speech response")
            if "unable to respond (" in reply:
                print(str(startup_error("Native HGA returned its error response",
                    [Path.home()/"hga-state/native-server.log"], os.environ,
                    [self.client.headers["Authorization"].split(" ", 1)[1]])), file=sys.stderr, flush=True)
            self.sessions[session_id] = result.get("conversation_id")
            await self.conn.session_update(session_id=session_id, update=update_agent_message_text(reply))
            return PromptResponse(stopReason="end_turn")
        except asyncio.CancelledError:
            if self.process and self.process.returncode is None:
                self.process.terminate()
                await self.process.wait()
            return PromptResponse(stopReason="cancelled")
        finally:
            self.tasks.pop(session_id, None)

    async def cancel(self, session_id, **kwargs):
        if session_id in self.tasks:
            self.tasks[session_id].cancel()


asyncio.run(run_agent(HomeAgent()))
