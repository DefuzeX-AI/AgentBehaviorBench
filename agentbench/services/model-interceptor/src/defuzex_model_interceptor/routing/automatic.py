"""Resolve adapter-owned signatures without requiring per-Agent model routes."""
from ..config import Route
from ..error import InterceptorAuthenticationError, TargetRoutingError


class AutomaticModelRouter:
    """Recognize installed wire adapters and bind the actual per-run credential.

    Explicit routes remain available for nonstandard endpoints. Recognition
    never sends a request or changes its headers; authentication probes operate
    on copies. A recognized but unauthenticated model call cannot become a tool
    request. Ambiguous signatures or credentials fail with a concrete error.
    """

    def __init__(self, factories, credentials, authentication):
        self.signatures = tuple((name, signature) for name, factory in factories.items()
                                if (signature := getattr(factory(), "signature", None)) is not None)
        self.credentials = credentials
        self.authentication = authentication

    def recognize(self, request):
        """Identify a wire format without treating recognition as authorization."""
        matches = [(name, signature) for name, signature in self.signatures if signature.matches(request)]
        if not matches:
            return None
        score = max(signature.specificity(request) for _, signature in matches)
        matches = [(name, signature) for name, signature in matches if signature.specificity(request) == score]
        if len(matches) != 1:
            raise TargetRoutingError("Ambiguous model protocol: " + ", ".join(name for name, _ in matches))
        return matches[0]

    def resolve(self, request):
        recognized = self.recognize(request)
        if recognized is None:
            return None
        protocol, signature = recognized
        credentials = []
        for credential in self.credentials:
            if credential.auth_plugin != signature.auth_plugin:
                continue
            auth = self.authentication[credential.auth_plugin]
            candidate = request.copy()
            try:
                options = dict(temporary_token=credential.token, upstream_secret="recognition-only")
                if hasattr(auth, "authorize_request"):
                    auth.authorize_request(candidate, **options)
                else:
                    auth.authorize(candidate.headers, **options)
            except InterceptorAuthenticationError:
                continue
            credentials.append(credential)
        if not credentials:
            raise InterceptorAuthenticationError(
                f"Recognized {protocol}, but no configured per-run credential authenticated this request")
        if len(credentials) != 1:
            raise InterceptorAuthenticationError(f"Ambiguous per-run credential for {protocol}")
        credential = credentials[0]
        return Route(f"auto:{protocol}:{credential.credential_id}",
                     (request.pretty_host.rstrip('.').lower(),), (request.port,), (request.method.upper(),),
                     (request.path.split('?', 1)[0],), protocol, credential.credential_id)
