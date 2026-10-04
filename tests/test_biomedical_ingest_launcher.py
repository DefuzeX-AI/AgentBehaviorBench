import io

from scripts.start_biomedical_ingest import RedactedStream
from scripts.start_biomedical_ingest import pdf_pipeline_config


def test_launcher_stream_redacts_credentials():
    output = io.StringIO()
    stream = RedactedStream(output, ["private-api-key", "private-token"])
    stream.write("error private-api-key / private-token")
    stream.flush()
    assert output.getvalue() == "error [REDACTED] / [REDACTED]"


def test_launcher_stream_preserves_nonsecret_output():
    output = io.StringIO()
    stream = RedactedStream(output, ["private-api-key"])
    stream.write("config OK\n")
    assert output.getvalue() == "config OK\n"


def test_pdf_config_keeps_pdf_tables_charts_and_reconnects_chain():
    names = ["source_stage", "pdf_extractor", "audio_extractor",
             "table_extractor", "chart_extractor", "text_embedder", "default_drain"]
    original = {"name": "original", "pipeline": {"launch_simple_broker": True},
                "stages": [{"name": name, "replicas": {}, "config": {}}
                           for name in names], "edges": []}
    result = pdf_pipeline_config(original)
    assert original["pipeline"]["launch_simple_broker"] is True
    assert len(original["stages"]) == 7
    retained = [s["name"] for s in result["stages"]]
    assert retained == [n for n in names if n != "audio_extractor"]
    assert [(e["from"], e["to"]) for e in result["edges"]] == list(zip(retained, retained[1:]))
    assert all(e["queue_size"] == 1 for e in result["edges"])
    assert all(s["replicas"]["static_replicas"] == 1 for s in result["stages"])


def test_pdf_config_uses_loopback_and_removes_stale_dependencies():
    original = {"pipeline": {}, "stages": [
        {"name": "source_stage", "config": {"broker_client": {"host": "0.0.0.0"}}},
        {"name": "text_splitter", "config": {}, "runs_after": ["audio_extractor", "source_stage"]},
    ]}
    result = pdf_pipeline_config(original)
    assert result["stages"][0]["config"]["broker_client"]["host"] == "127.0.0.1"
    assert result["stages"][1]["runs_after"] == ["source_stage"]
