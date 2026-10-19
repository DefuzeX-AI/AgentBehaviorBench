"""Portable Case snapshots for the default worker, without interpreting SDK data."""
import hashlib
import json
from collections.abc import Mapping

from agentbench.sdk.common.artifacts import plain

SCHEMA = 'abb.sdk.case.v1'


def case_bytes(value):
    return json.dumps(plain(value), sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(',', ':')).encode('utf-8')


def digest(content):
    return hashlib.sha256(content).hexdigest()


def snapshot(value):
    value = plain(value)
    if not isinstance(value, Mapping) or not isinstance(value.get('case_id'), str) or not value['case_id'].strip():
        raise ValueError('SDK Run.case must be a JSON object with a non-empty case_id')
    return json.loads(case_bytes(value))


def pack_case(case, *, factory, index, workspace):
    return {'schema': SCHEMA, 'factory': factory, 'case_index': index,
            'workspace': workspace, 'case': snapshot(case)}


def unpack_case(document, *, factory, index):
    if (not isinstance(document, dict) or document.get('schema') != SCHEMA
            or document.get('factory') != factory or type(document.get('case_index')) is not int
            or document['case_index'] != index):
        raise ValueError('Saved Case does not belong to this SDK and Case slot')
    return snapshot(document['case'])
