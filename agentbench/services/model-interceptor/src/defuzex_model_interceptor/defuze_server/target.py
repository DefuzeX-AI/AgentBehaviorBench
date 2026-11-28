"""Reuse native wire conversion while owning Defuze access and billing headers."""
from uuid import uuid4
from ..targets.compatible_json import CompatibleJSONTarget
from . import access
from .config import PROTOCOLS, validate


class DefuzeServerTarget(CompatibleJSONTarget):
    name = 'defuze_server'

    def preflight(self, target, secrets):
        validate(target)
        if not secrets or any(not key for key in secrets):
            raise access.AccessError('credential_missing')
        for secret in set(secrets):
            access.check(target.base_url, secret)

    def prepare_request(self, request, *, route, target):
        validate(target)
        if route.protocol_plugin not in PROTOCOLS:
            raise ValueError('Unsupported Defuze model protocol: ' + route.protocol_plugin)
        prepared = super().prepare_request(request, route=route, target=target)
        # Created once per prepared outbound request; transport retries reuse it.
        # An independent Agent retry is a new request, not a deduplication claim.
        request.headers['Idempotency-Key'] = str(uuid4())
        return prepared
