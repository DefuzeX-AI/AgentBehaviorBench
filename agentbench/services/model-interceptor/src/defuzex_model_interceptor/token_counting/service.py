"""Local request handler selected after normal route authentication."""
import hashlib
import json
from dataclasses import dataclass
from .counters import ENCODINGS, estimate
from .protocols import PROTOCOLS, UnsupportedInput


@dataclass(frozen=True)
class CountReply:
    status: int
    body: dict
    evidence: dict


class TokenCountingService:
    """No I/O until a supported counting request arrives; no Agent-specific names.

    Args:
        options: Opt-in mode and explicit target-model-to-encoding mapping.
        model: Actual generation target, not the Agent's pre-routing model alias.
    """
    def __init__(self, options, model):
        if set(options) - {'mode', 'models', 'max_input_bytes'}:
            raise ValueError('Unknown token_counting option')
        self.mode = options.get('mode', 'upstream')
        if self.mode not in ('upstream', 'local_estimate'):
            raise ValueError('Unknown token_counting mode')
        self.models = options.get('models', {})
        if not isinstance(self.models, dict) or any(
            not isinstance(k, str) or not k or v not in ENCODINGS for k, v in self.models.items()
        ):
            raise ValueError('token_counting.models must map exact model IDs to bundled encodings')
        self.limit = options.get('max_input_bytes', 2_000_000)
        if type(self.limit) is not int or not 1024 <= self.limit <= 8_000_000:
            raise ValueError('max_input_bytes must be between 1024 and 8000000')
        self.model = model

    def handle(self, protocol, content):
        """Return CountReply, or None to keep the existing upstream route.

        Known unsupported inputs return 404, permitting native clients such as
        MiniMax to cache endpoint unavailability and use their own estimator.
        Invalid requests return 400. Neither result is a successful generation.
        """
        if self.mode != 'local_estimate' or protocol not in PROTOCOLS:
            return None
        evidence = {'source': 'local_estimate', 'model': self.model,
                    'request_sha256': hashlib.sha256(content).hexdigest()}
        def error(status, code, message):
            return CountReply(status, {'error': {'code': code, 'message': message}}, evidence)
        if len(content) > self.limit:
            return error(413, 'input_too_large', 'Counting input exceeds configured limit')
        encoding = self.models.get(self.model)
        if encoding is None:
            return error(404, 'counting_unavailable', 'No local tokenizer configured for target model')
        try:
            body = json.loads(content)
            if not isinstance(body, dict):
                raise ValueError('Counting request must be an object')
            payload = PROTOCOLS[protocol].normalize(body)
            tokens, algorithm = estimate(payload, encoding)
        except UnsupportedInput as exc:
            return error(404, 'counting_unavailable', str(exc))
        except (ValueError, TypeError, RecursionError):
            return error(400, 'invalid_counting_request', 'Invalid token counting input')
        evidence.update(encoding=encoding, algorithm=algorithm, input_tokens=tokens,
                        source_model=body.get('model'), estimate=True)
        return CountReply(200, PROTOCOLS[protocol].response(tokens), evidence)
