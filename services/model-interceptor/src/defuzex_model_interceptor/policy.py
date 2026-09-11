"""Deny undeclared traffic; tool exceptions never authorize model hosts."""
import fnmatch


class EgressPolicy:
    def __init__(self, config):
        self.config = config

    @staticmethod
    def matches(rule, request):
        return (request.port in rule.ports
                and request.method.upper() in rule.methods
                and any(fnmatch.fnmatchcase(request.pretty_host.rstrip('.').lower(), h) for h in rule.host_patterns)
                and any(fnmatch.fnmatchcase(request.path.split('?', 1)[0], p) for p in rule.path_patterns))

    def permits_tool(self, request):
        host = request.pretty_host.rstrip('.').lower()
        if any(fnmatch.fnmatchcase(host, p) for r in self.config.routes for p in r.host_patterns):
            return False
        return any(self.matches(r, request) for r in self.config.tool_routes)
