"""Bounded HTTP evidence decoding. Never mutate the forwarded transport bytes."""
from dataclasses import dataclass
from typing import Callable
import zlib


class BodyGap(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceBody:
    body: bytes
    complete: bool
    metadata: dict


def _decode(data, encoding, limit):
    if encoding in ("", "identity"):
        result = data
    elif encoding in ("gzip", "deflate"):
        decoder = zlib.decompressobj(31 if encoding == "gzip" else 15)
        result = decoder.decompress(data, limit + 1)
        if len(result) > limit or decoder.unconsumed_tail:
            raise BodyGap("decoded_body_limit_exceeded")
        if not decoder.eof or decoder.unused_data:
            raise BodyGap("incomplete_or_trailing_compressed_body")
    elif encoding == "br":
        try:
            import brotli
        except ImportError:
            raise BodyGap("decoder_unavailable") from None
        decoder = brotli.Decompressor()
        try:
            result = decoder.process(data, output_buffer_limit=limit + 1)
        except TypeError:
            # Older decoders cannot enforce an output bound. Never decode unbounded.
            raise BodyGap("bounded_decoder_unavailable") from None
        if len(result) > limit:
            raise BodyGap("decoded_body_limit_exceeded")
        if not decoder.is_finished():
            raise BodyGap("incomplete_compressed_body")
    else:
        raise BodyGap("unsupported_content_encoding")
    if len(result) > limit:
        raise BodyGap("decoded_body_limit_exceeded")
    return result


def prepare_body(data: bytes, *, encoding: str, limit: int, complete: bool,
                 redact: Callable[[bytes], bytes]) -> EvidenceBody:
    """Decode an encoded capture, then sanitize it; report gaps without secret bytes.

    Callers that already decoded a response must pass identity here and retain
    the original Content-Encoding separately in their HTTP metadata.
    """
    if limit <= 0:
        raise ValueError("Evidence body limit must be positive")
    metadata = {"body_representation": "decoded_redacted", "captured_content_encoding": encoding}
    try:
        body = data
        for part in reversed(encoding.lower().split(",")):
            body = _decode(body, part.strip(), limit)
    except BodyGap as exc:
        return EvidenceBody(b"", False, {**metadata, "body_gap": str(exc)})
    except Exception:
        return EvidenceBody(b"", False, {**metadata, "body_gap": "body_decode_failed"})
    # Redaction failures must propagate: never publish unsanitized evidence.
    return EvidenceBody(redact(body), complete, metadata)
