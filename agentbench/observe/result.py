"""One redaction boundary for Agent results, before persistence or submission."""
from .store import json_value, redact


def sanitize_result(result, secrets):
    """Return a detached safe result and a content-free redaction receipt.

    Receipt fields are a fixed vocabulary, never Agent-controlled JSON paths.
    Execution status and protocol stop reasons retain their original meaning.
    """
    original = json_value(result)
    safe = redact(original, secrets)
    fields = [key for key in ('output', 'raw_output', 'error')
              if key in original and original[key] != safe[key]]
    return safe, {'status': 'applied' if safe != original else 'unchanged',
                  'fields': fields, 'changed_field_count': len(fields),
                  'policy': 'runtime_credentials_and_credential_fields'}
