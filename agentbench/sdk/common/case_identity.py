"""Content identity independent of provider-assigned Case and step identifiers."""
import hashlib
import json
from collections.abc import Mapping
import unicodedata


def case_content_sha256(case):
    def field(value, key):
        return value[key] if isinstance(value, Mapping) else getattr(value, key)

    def normalize(value):
        if isinstance(value, str):
            return ' '.join(unicodedata.normalize('NFKC', value).split())
        if isinstance(value, Mapping):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        return value

    inputs = [{'payload_type': field(item, 'payload_type'), 'payload': normalize(field(item, 'payload'))}
              for item in field(case, 'inputs')]
    if not inputs:
        raise ValueError('Cannot fingerprint an empty Case')
    encoded = json.dumps(inputs, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
