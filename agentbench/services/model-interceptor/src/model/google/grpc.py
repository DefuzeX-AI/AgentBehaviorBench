"""Gemini protobuf and gRPC envelopes, without changing the Agent client."""
import io
import gzip
import json
import struct
from google.ai.generativelanguage_v1beta.types import GenerateContentRequest, GenerateContentResponse


MAX_MESSAGE = 32 * 1024 * 1024


def unpack_request(content, encoding="identity"):
    if len(content) < 5:
        raise ValueError("Incomplete gRPC frame")
    flag, size = struct.unpack(">BI", content[:5])
    if size > MAX_MESSAGE or len(content) != size + 5 or flag not in (0, 1):
        raise ValueError("Expected one bounded gRPC request message")
    data = content[5:]
    if flag:
        if encoding != "gzip":
            raise ValueError("Unsupported gRPC compression")
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(MAX_MESSAGE + 1)
        if len(data) > MAX_MESSAGE:
            raise ValueError("Decompressed gRPC message exceeds supported size")
    message = GenerateContentRequest.deserialize(data)
    # Unknown wire fields must not silently disappear during model translation.
    raw = GenerateContentRequest.pb(message)
    known = type(raw)()
    known.CopyFrom(raw)
    known.DiscardUnknownFields()
    if known.SerializeToString() != raw.SerializeToString():
        raise ValueError("Unknown Gemini protobuf fields")
    return json.loads(GenerateContentRequest.to_json(message, preserving_proto_field_name=False,
                                                    always_print_fields_with_no_presence=False))


def pack_response(payload):
    message = GenerateContentResponse.from_json(json.dumps(payload))
    data = GenerateContentResponse.serialize(message)
    return struct.pack(">BI", 0, len(data)) + data
