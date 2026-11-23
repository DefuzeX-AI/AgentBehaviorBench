"""Own the Agent observation window for a single Case attempt."""
import os
from pathlib import Path

from .evidence import EvidenceWriter
from .profiles import PROFILES, auto, file_export, opensoul
from .receiver import Receiver


class CaptureSession:
    def __init__(self, config, directory, agent_id):
        self.config = config
        self.sink = EvidenceWriter(directory, config)
        self.receiver = self.instrumentation = None
        self.environment = {}
        self.previous = {}
        self.workdir = Path.cwd()
        self.finished = False
        self.file_spool = None
        self.gateway_spool = None
        implementation = PROFILES[config.profile]
        if implementation is None:
            return
        try:
            if implementation is file_export:
                from tempfile import TemporaryDirectory
                self.file_spool = TemporaryDirectory(prefix="abb-otel-file-")
                self.workdir = Path(self.file_spool.name)
            else:
                self.receiver = Receiver(config.protocol, self.sink)
            endpoint = self.receiver.endpoint if self.receiver else ""
            self.environment = implementation.environment(config, endpoint, agent_id)
            if config.profile == "opensoul":
                from tempfile import TemporaryDirectory
                self.gateway_spool = TemporaryDirectory(prefix="abb-otel-gateway-")
                self.environment["ABB_OTEL_GATEWAY_LOG"] = str(Path(self.gateway_spool.name) / "gateway.log")
            if self.file_spool:
                self.environment['ABB_OTEL_FILE'] = str(self.workdir / config.file)
                if config.file_format == 'whip-session':
                    self.environment['ABB_OTEL_SESSION_FILE'] = str(self.workdir / 'session-id')
        except Exception as exc:
            self.sink.error = type(exc).__name__

    def attach(self, adapter, framework, agent_id):
        if framework == "acp":
            adapter.trace_environment = self.environment
        elif self.receiver:
            if self.config.profile == "python-auto":
                try:
                    self.instrumentation = auto.instrument_graph(self.receiver.endpoint, agent_id, self.config.capture_content)
                except Exception as exc:
                    self.sink.error = type(exc).__name__
            else:
                for key, value in self.environment.items():
                    self.previous[key] = os.environ.get(key)
                    os.environ[key] = value

    def close(self):
        if self.finished:
            return
        self.finished = True
        try:
            if self.instrumentation:
                instrumentor, provider = self.instrumentation
                instrumentor.uninstrument()
                provider.shutdown()
            elif self.previous:
                # An in-process native binding can register its own global SDK provider.
                from opentelemetry import trace
                flush = getattr(trace.get_tracer_provider(), "force_flush", None)
                if flush and flush() is False:
                    self.sink.error = "Agent tracer provider failed to flush"
            if self.gateway_spool:
                self.sink.error = opensoul.exporter_error(Path(self.gateway_spool.name) / "gateway.log", self.sink.secrets) or self.sink.error
            if self.config.profile == "file-export":
                file_export.collect(self.config, self.workdir, self.sink)
        except Exception as exc:
            self.sink.error = type(exc).__name__
        finally:
            for key, value in self.previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if self.receiver:
                self.receiver.close()
            if self.file_spool:
                self.file_spool.cleanup()
            if self.gateway_spool:
                self.gateway_spool.cleanup()
        state = self.config.profile if self.config.profile in ("unsupported", "unconfigured") else (
            "incomplete" if self.sink.error else "received" if self.sink.count else "zero_spans")
        self.sink.status(state)
