"""Start the native NV-Ingest pipeline in its isolated environment.

The broker is explicitly loopback-only; no documents are submitted here.
"""
import argparse
import os
from pathlib import Path
import socket
import sys

from dotenv import dotenv_values


UNUSED_EXTRACTORS = {
    "audio_extractor", "docx_extractor", "pptx_extractor",
    "image_extractor", "html_extractor", "infographic_extractor",
}


def pdf_pipeline_config(default):
    """Keep native PDF/text/table/chart processing, reduce queued work/replicas.

    This limits concurrency, NOT memory usage. The upstream 10 GB extraction
    heuristics are not evidence that a one-document run fits this host.
    """
    from copy import deepcopy
    result = deepcopy(default)
    stages = [s for s in result["stages"] if s["name"] not in UNUSED_EXTRACTORS]
    names = {s["name"] for s in stages}
    for stage in stages:
        stage["replicas"] = {"min_replicas": 1, "max_replicas": 1, "static_replicas": 1}
        stage["runs_after"] = [n for n in stage.get("runs_after", []) if n in names]
        broker = stage.get("config", {}).get("broker_client")
        if broker:
            broker["host"] = "127.0.0.1"
    result["stages"] = stages
    # The upstream default is a single ordered chain; reconnect skipped
    # standalone-file extractors instead of leaving disconnected edges.
    result["edges"] = [{"from": a["name"], "to": b["name"], "queue_size": 1}
                       for a, b in zip(stages, stages[1:])]
    result["pipeline"]["launch_simple_broker"] = False
    result["pipeline"]["disable_dynamic_scaling"] = True
    result["name"] = "Biomedical PDF pipeline (one replica per native stage)"
    return result


class RedactedStream:
    def __init__(self, stream, secrets):
        self.stream = stream
        self.secrets = secrets

    def write(self, value):
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED]")
        return self.stream.write(value)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate config without starting services")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    values = dotenv_values(root / ".env")
    key = os.environ.get("NVIDIA_API_KEY") or values.get("NVIDIA_API_KEY")
    if not key:
        raise SystemExit("NVIDIA_API_KEY is not configured")
    secrets = [v for k, v in values.items() if v and any(t in k for t in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
    secrets.append(key)
    sys.stdout = RedactedStream(sys.stdout, secrets)
    sys.stderr = RedactedStream(sys.stderr, secrets)
    os.environ["NVIDIA_API_KEY"] = key
    os.environ["NGC_API_KEY"] = key
    # Only hosted extraction models: no local GPU services.
    for prefix, model in (
        ("OCR", "nemotron-ocr-v1"),
        ("YOLOX", "nemotron-page-elements-v3"),
        ("YOLOX_GRAPHIC_ELEMENTS", "nemotron-graphic-elements-v1"),
        ("YOLOX_TABLE_STRUCTURE", "nemotron-table-structure-v1"),
    ):
        os.environ[prefix + "_HTTP_ENDPOINT"] = "https://ai.api.nvidia.com/v1/cv/nvidia/" + model
        os.environ[prefix + "_INFER_PROTOCOL"] = "http"
    os.environ["RAY_USAGE_STATS_ENABLED"] = "0"
    os.environ["EMBEDDING_NIM_MODEL_NAME"] = "nvidia/nemotron-3-embed-1b"
    os.environ["EMBEDDING_NIM_ENDPOINT"] = "https://integrate.api.nvidia.com/v1"
    # Avoid CPU thread multiplication across the individual worker processes.
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    from nv_ingest.pipeline.config.loaders import load_default_libmode_config
    from nv_ingest.pipeline.pipeline_schema import PipelineConfigSchema
    from nv_ingest.framework.orchestration.process.dependent_services import start_simple_message_broker
    from nv_ingest.framework.orchestration.ray.util.pipeline.pipeline_runners import run_pipeline

    config = PipelineConfigSchema.model_validate(
        pdf_pipeline_config(load_default_libmode_config().model_dump(by_alias=True)))
    # Import all selected actors now: entry-point-only imports missed the
    # earlier Triton/protobuf and OpenCV shared-library incompatibilities.
    import importlib
    for stage in config.stages:
        module, attribute = stage.actor.split(":")
        getattr(importlib.import_module(module), attribute)
    print(f"Native PDF pipeline config/imports: OK; stages={len(config.stages)}; "
          "replicas=1/stage; edge queue=1; broker=127.0.0.1:7671", flush=True)
    print("PDF text/table/chart stages retained. Memory fit is NOT yet verified; submit only one PDF initially.", flush=True)
    if args.check:
        return
    # Refuse to reuse an unknown service or terminate another user's process.
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 7671))
    finally:
        probe.close()
    broker = start_simple_message_broker({"host": "127.0.0.1", "port": 7671})
    try:
        import ray
        if ray.is_initialized():
            raise RuntimeError("Refusing to reuse an existing Ray runtime")
        # Native launch skips ray.init when already initialized. Disable its
        # otherwise all-interface dashboard and keep this runtime local.
        ray.init(include_dashboard=False, num_cpus=2,
                 object_store_memory=256 * 1024 * 1024,
                 _node_ip_address="127.0.0.1")
        print("Starting NV-Ingest; leave this terminal open. Ctrl-C stops this launcher.", flush=True)
        run_pipeline(pipeline_config=config, block=True, disable_dynamic_scaling=True,
                     run_in_subprocess=False, quiet=False)
    finally:
        if "ray" in locals() and ray.is_initialized():
            ray.shutdown()
        if broker.is_alive():
            broker.terminate()
        broker.join(timeout=5)


if __name__ == "__main__":
    main()
