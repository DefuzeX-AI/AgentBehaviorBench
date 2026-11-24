"""Portable evidence is a lossless representation, not a UI replay snapshot."""
import json
import shutil
from pathlib import Path
import pytest

pytest.importorskip("harbor.models.trajectories")
from tests.atif_fixtures import fixture, child_bundle, lines, event, save
from agentbench.trajectory.atif.bundle import export_bundle
from agentbench.trajectory.atif.bundle_validation import verify_bundle
from agentbench.trajectory.atif.evidence_store import EvidenceStore, EvidenceResolver, preserve_bytes, restore_bytes, json_bytes, safe_path


def test_value_sharing_and_user_marker_keys(tmp_path):
    store = EvidenceStore(tmp_path, threshold=32)
    text = "中文 España " * 100
    a = store.raw_body(json.dumps({"content": text}, ensure_ascii=False), "runs/model-calls/0001/request")
    b = store.raw_body(json.dumps({"content": text}, ensure_ascii=False), "runs/model-calls/0002/request")
    changed = store.raw_body(json.dumps({"content": text + "changed"}, ensure_ascii=False), "runs/model-calls/0003/request")
    assert a == b and a != changed
    value = {"value": None, "body_refs": [{"path": "not-a-reference"}], "format": "user", "nested": [False, 1, 1.0, text]}
    ref = store.value(value)
    resolver = EvidenceResolver(tmp_path, store.files)
    assert json_bytes(resolver.resolve(ref)) == json_bytes(value)
    assert store.value(json.loads(json.dumps({"content": text}))) ["path"] == a["path"]


@pytest.mark.parametrize("data", [b'{ "x" : 1 }\r\n', b'{"x":1}\n', b'\x00\xff\xfe', '中文 España\n'.encode(), b'{"arguments":"{\\"x\\":"}', b''])
def test_original_bytes(data, tmp_path):
    store = EvidenceStore(tmp_path)
    description = preserve_bytes(store, data, "runs/files/original")
    assert restore_bytes(EvidenceResolver(tmp_path, store.files), description) == data


@pytest.mark.parametrize("layout", ["standalone", "steps", "legacy"])
def test_portable_roundtrip_and_stability(tmp_path, layout):
    source = tmp_path / "source"
    fixture(source, layout)
    a = export_bundle(source, tmp_path / "out")
    b = export_bundle(source, tmp_path / "out")
    pa, pb = Path(a["path"]), Path(b["path"])
    assert pa.name == "run-run-a" and pb.name == "run-run-a-2"
    ma, mb = [json.loads((p / "manifest.json").read_text()) for p in (pa, pb)]
    ma.pop("exported_at"); mb.pop("exported_at")
    assert ma == mb
    for name in ma["files"]:
        assert (pa/name).read_bytes() == (pb/name).read_bytes()
    trajectory_text = (pa / "trajectory.json").read_bytes().decode("utf-8")
    doc = json.loads(trajectory_text)
    assert trajectory_text == json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    assert "raw_records" not in doc['extra']['abb']
    shutil.rmtree(source)
    moved = tmp_path / "moved"
    shutil.move(pa, moved)
    assert verify_bundle(moved)["passed"]


def test_two_children_reused_call_ids(tmp_path):
    child_bundle(tmp_path/'source')
    result = export_bundle(tmp_path/'source', tmp_path/'out', adapters=["deepagents"])
    assert result['validation']['children'] == 2
    assert result['validation']['models'] == 2
    assert result['validation']['tools'] == 4


def test_sources_unknown_binary_and_secret_exclusion(tmp_path):
    source = tmp_path/'source'
    fixture(source)
    # Unknown fields and sources are retained, not interpreted as Agent identity.
    path = source/'network.jsonl'
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({"event":"unknown-event", "source":"custom-observer", "data":{"value":"秘密不是凭据 ¡Hola!"}}, ensure_ascii=False)+'\n')
    (source/'binary.dat').write_bytes(bytes(range(256)))
    (source/'proxy-private.pem').write_text('-----BEGIN PRIVATE KEY-----\nDO NOT EXPORT',encoding='utf-8')
    result = export_bundle(source,tmp_path/'out',evidence_files=['binary.dat'])
    manifest = json.loads((Path(result['path'])/'manifest.json').read_text())
    assert any(s['original_path']=='binary.dat' for s in manifest['sources'])
    assert not any(s['original_path']=='proxy-private.pem' for s in manifest['sources'])
    with pytest.raises(ValueError, match='Credential'):
        export_bundle(source,tmp_path/'out',evidence_files=['proxy-private.pem'])
    assert len(list((tmp_path/'out').glob('run-*'))) == 1


@pytest.mark.parametrize('attack', ['corrupt','missing','symlink','traversal','missing_ref','extra'])
def test_tampering_rejected(tmp_path, attack):
    fixture(tmp_path/'source')
    result=export_bundle(tmp_path/'source',tmp_path/'out')
    root=Path(result['path'])
    manifest=json.loads((root/'manifest.json').read_text())
    path=next(p for p in manifest['files'] if p != 'trajectory.json')
    if attack=='corrupt':
        (root/path).write_bytes(b'changed')
    elif attack=='missing':
        (root/path).unlink()
    elif attack=='symlink':
        (root/path).unlink(); (root/path).symlink_to(tmp_path/'source/run.json')
    elif attack=='traversal':
        manifest['files']['../escape'] = manifest['files'].pop(path)
        save(root/'manifest.json', manifest)
    elif attack=='missing_ref':
        manifest['sources'][0]['pieces_ref']['path']='runs/missing.json'
        save(root/'manifest.json', manifest)
    else:
        (root/'unexpected.key').write_text('extra',encoding='utf-8')
    with pytest.raises((ValueError,FileNotFoundError)):
        verify_bundle(root)


def test_source_mutation_does_not_publish(tmp_path, monkeypatch):
    import agentbench.trajectory.atif.bundle as module
    fixture(tmp_path/'source')
    real=module.compact_document
    def change(*args):
        result=real(*args)
        save(tmp_path/'source/run.json', {'run_id':'changed','status':'succeeded'})
        return result
    monkeypatch.setattr(module, 'compact_document', change)
    with pytest.raises(ValueError,match='changed'):
        export_bundle(tmp_path/'source',tmp_path/'out')
    assert not list((tmp_path/'out').glob('run-*'))
    assert list((tmp_path/'out').glob('export-failed-*.json'))


def test_partial_delta_preserved(tmp_path):
    fixture(tmp_path/'source',finished=False)
    lines(tmp_path/'source/network.jsonl', [event('llm_request',call_id='partial',payload={'messages':[]}),
        event('llm_delta',call_id='partial',sequence=1,payload={'choices':[{'delta':{'content':'半段 ¡Hola!'}}]})])
    with pytest.raises(ValueError,match='finished'):
        export_bundle(tmp_path/'source',tmp_path/'out')
    result=export_bundle(tmp_path/'source',tmp_path/'out',allow_incomplete=True)
    assert result['coverage']['status']=='partial'
    assert verify_bundle(result['path'])['passed']


@pytest.mark.parametrize('name', ['/absolute', '../up', 'a/../../up', 'C:/file', 'a\\b', 'a/./b'])
def test_path_guard(tmp_path,name):
    with pytest.raises(ValueError):
        safe_path(tmp_path,name)


def test_historical_two_children_content_contract(tmp_path):
    source = Path(__file__).parent / "fixtures/atif/two_children"
    result = export_bundle(source, tmp_path/'out', adapters=['deepagents'])
    assert result['validation']['models'] == 11
    assert result['validation']['tools'] == 12
    assert result['validation']['children'] == 2
    assert result['validation']['content_checks'] == 59
    assert result['validation']['records_reconstructed'] == 174


def test_partial_arguments_and_delta_identity(tmp_path):
    source = tmp_path/'source'
    fixture(source)
    rows = [event('llm_request', call_id='stream', payload={'messages':[]}),
        event('llm_delta', call_id='stream', sequence=1, payload={'choices':[{'delta':{'tool_calls':[{'index':0,'id':'tc','function':{'name':'write','arguments':'{"path":'}}]}}]}),
        event('llm_error', call_id='stream', error='cancelled')]
    lines(source/'network.jsonl', rows)
    result = export_bundle(source,tmp_path/'out')
    root = Path(result['path'])
    manifest=json.loads((root/'manifest.json').read_text())
    resolver=EvidenceResolver(root,manifest['files'])
    streams=list(root.glob('runs/model-calls/*/stream-events.jsonl'))
    assert len(streams)==1
    captured=[resolver.unpack(json.loads(line)) for line in streams[0].read_text().splitlines()]
    assert captured[0]['raw'] == rows[1]
    record=[resolver.resolve(op['ref']) for op in manifest['operations'].values() if op['kind']=='model' and resolver.resolve(op['ref']).get('call_id')=='stream'][0]
    assert record['status']=='error'
    assert record['output']['tool_calls'][0]['arguments']=='{"path":'


def test_requests_share_only_when_identical(tmp_path):
    source=tmp_path/'source';fixture(source)
    first=json.dumps({'messages':[{'role':'user','content':'original '*200}]})
    second=json.dumps({'messages':[{'role':'user','content':'changed '*200}]})
    rows=[event('llm_request',call_id='one',raw_body=first,source_raw_body=first,payload=json.loads(first)),
          event('llm_response',call_id='one',payload={'choices':[{'message':{'content':'same'}}]}),
          event('llm_request',call_id='two',raw_body=second,source_raw_body=first,payload=json.loads(second)),
          event('llm_response',call_id='two',payload={'choices':[{'message':{'content':'same'}}]})]
    lines(source/'network.jsonl',rows)
    result=export_bundle(source,tmp_path/'out')
    root=Path(result['path']);manifest=json.loads((root/'manifest.json').read_text())
    resolver=EvidenceResolver(root,manifest['files'])
    calls=[json.loads(p.read_text()) for p in root.glob('runs/model-calls/*/call.json')]
    calls={resolver.resolve(c['record_ref']).get('call_id'):c for c in calls}
    one,two=calls['one']['body_refs'],calls['two']['body_refs']
    assert one['raw_request.raw_body']['path']==one['raw_request.source_raw_body']['path']==two['raw_request.source_raw_body']['path']
    assert two['raw_request.raw_body']['path']!=two['raw_request.source_raw_body']['path']
    assert result['validation']['models']==3  # Independent callback is not guessed to be either wire call.


def test_atomic_publication_cannot_replace_even_empty_directory(tmp_path):
    from agentbench.trajectory.atif.publication import publish_directory
    source,destination=tmp_path/'staging',tmp_path/'existing'
    source.mkdir();(source/'proof').write_bytes(b'new')
    destination.mkdir()
    with pytest.raises(FileExistsError):
        publish_directory(source,destination)
    assert not list(destination.iterdir()) and (source/'proof').read_bytes()==b'new'


def test_concurrent_names_preserve_both_exports(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    source=tmp_path/'source';fixture(source)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _: export_bundle(source,tmp_path/'out'),range(2)))
    assert len({r['path'] for r in results})==2
    assert all(verify_bundle(r['path'])['passed'] for r in results)


def test_opaque_record_and_mixed_sources(tmp_path):
    source=tmp_path/'source';folder=fixture(source)
    lines(folder/'otel.jsonl',[{'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'observer'}}]}}]}])
    lines(folder/'acp-events.jsonl',[{'event':'notice','data':{'opaque':'preserve me'}}])
    with (source/'network.jsonl').open('ab') as stream:
        stream.write(b'not JSON but still recorded\n')
    result=export_bundle(source,tmp_path/'out')
    assert result['coverage']['status']=='partial'
    root=Path(result['path']);manifest=json.loads((root/'manifest.json').read_text())
    assert any('otel.jsonl' in s['original_path'] for s in manifest['sources'])
    assert any('acp-events.jsonl' in s['original_path'] for s in manifest['sources'])
    assert verify_bundle(root)['passed']


def test_reconstruction_does_not_use_filesystem_mtime_as_record_identity(tmp_path):
    import os
    source=tmp_path/'source';folder=fixture(source)
    request=folder.parent/'input/request.json'
    os.utime(request,(1,1))
    result=export_bundle(source,tmp_path/'out')
    shutil.rmtree(source)
    assert verify_bundle(result['path'])['passed']


def test_old_bundle_with_dangling_native_otel_reference_is_rejected(tmp_path, monkeypatch):
    import agentbench.trajectory.atif.bundle as writer
    import agentbench.trajectory.atif.bundle_validation as verifier
    source = tmp_path / "source"
    folder = fixture(source)
    (source / folder / "otel.jsonl").write_text(json.dumps({
        "schema": "abb.observe.event.v1", "source": "otel", "event": "span",
        "data": {"attributes": {"abb.input_ref": "otel-payloads/missing.json"}}
    }) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing native evidence"):
        export_bundle(source, tmp_path / "out")
    assert not list((tmp_path / "out").glob("run-*"))
    # Simulate the former writer, which validated only the supplied file list.
    with monkeypatch.context() as old:
        old.setattr(writer, "validate_native_references", lambda _: {})
        old.setattr(verifier, "validate_native_references", lambda _: {})
        result = export_bundle(source, tmp_path / "old")
    with pytest.raises(ValueError, match="Missing native evidence"):
        verify_bundle(result["path"])


def test_intercepted_calls_only_in_trace(tmp_path):
    source = tmp_path / "source"
    folder = fixture(source, layout="steps")
    # One joined span and one unowned call, with different wire-only text.
    wire = []
    for call_id, span_id in (("attached", "model"), ("unattached", None)):
        wire.extend([event("llm_request", call_id=call_id, framework_span_id=span_id,
                           payload={"messages": [{"role": "system", "content": "network-only-system"}]}),
                     event("llm_response", call_id=call_id, payload={"choices": [
                         {"message": {"content": "network-only-" + call_id}}]})])
    lines(source / "network.jsonl", wire)
    save(folder / "result.json", {"status": "succeeded", "output": "Delivered"})
    exported = export_bundle(source, tmp_path / "out")
    root = Path(exported["path"])
    payload = (root / "trajectory.json").read_text(encoding="utf-8")
    assert "network-only" not in payload and "unassigned_records" not in payload
    assert [s["message"] for s in json.loads(payload)["steps"] if s["source"] == "agent"] == [
        "你好 ¡España!", "", "Delivered"]
    assert exported["validation"]["models"] == 2
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    resolver = EvidenceResolver(root, manifest["files"])
    stored = [resolver.resolve(op["ref"]) for op in manifest["operations"].values() if op["kind"] == "model"]
    assert {r["output"]["text"] for r in stored} == {"network-only-attached", "network-only-unattached"}


def test_acp_delivered_chunks_survive_missing_final_result(tmp_path):
    folder = fixture(tmp_path / "source", layout="steps", tool=False)
    lines(folder / "framework.jsonl", [])
    save(folder / "result.json", {"status": "cancelled"})
    save(folder / "acp-summary.json", {"session": {"sessionId": "session"}})
    lines(folder / "acp-events.jsonl", [
        event("session_update", session_id=session, update={"sessionUpdate": "agent_message_chunk",
              "content": {"type": "text", "text": value}})
        for session, value in [("session", "¡Ho"), ("different", "other"), ("session", "la!")]])
    exported = export_bundle(tmp_path / "source", tmp_path / "out")
    doc = json.loads((Path(exported["path"]) / "trajectory.json").read_text(encoding="utf-8"))
    assert [(s["source"], s["message"]) for s in doc["steps"]] == [("user", "你好 ¡España!"), ("agent", "¡Hola!")]


def test_bundle_replays_agent_otlp_evidence(tmp_path):
    source = tmp_path / "source"
    fixture(source)
    save(source / "otel/status.json", {"profile": "native-otlp", "span_count": 1, "status": "received"})
    entry = {"schema": "abb.agent-otel.v1", "origin": "agent_native", "scope": {"name": "target"},
             "resource": {}, "span": {"name": "unassigned", "traceId": "ab" * 16, "spanId": "cd" * 8}}
    (source / "otel/spans.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    bundle = Path(export_bundle(source, tmp_path / "archives")["path"])
    files = {s["original_path"] for s in json.loads((bundle / "manifest.json").read_text())["sources"]}
    assert {"otel/spans.jsonl", "otel/status.json"} <= files
    assert verify_bundle(bundle)["passed"]
