# Egress observer

A small forward proxy that handles an Agent's **non-model** network traffic, kept
apart from the model interceptor so model calls and everything else are counted
separately.

## Where it sits

The Agent shares the model interceptor's network namespace, so every non-root TCP
connection still reaches mitmproxy first. The interceptor keeps full ownership of
declared model routes and tool routes. A request that matches neither is no longer
answered with a local `403 egress_denied`; the interceptor sends it upstream through
this proxy instead (`server_conn.via`). The observer then decides:

- a destination on the allowlist (by default the common package registries: PyPI,
  npm, Debian/Ubuntu archives, Maven Central, crates.io, the Go module proxy) is
  forwarded, so `pip install`, `npm install` and `apt-get install` work;
- anything else is refused with `403 Forbidden`.

Both outcomes are recorded. A refusal is behavioral evidence of the Agent, not a
failure of trace capture, so it no longer rejects the Case (issue #137).

The observer never decrypts a tunnel. mitmproxy reaches an upstream proxy with
`CONNECT` in transparent mode, for plain HTTP as well, so each record carries the
destination `host:port`, the decision, byte counts and duration, not URL paths.
(A client that uses the observer directly as an HTTP proxy with absolute-form
requests also gets the method, path without query, and response status recorded.)

## Events

One JSON object per line on stdout, prefixed with `DEFUZEX_EGRESS ` (the interceptor
uses `DEFUZEX_TRACE `). The host writes them to `egress.jsonl` next to
`network.jsonl`. They carry a `conn_id`, never a model `call_id`, and do not
participate in model trace acceptance.

| event | when | notable fields |
|---|---|---|
| `egress_ready` | listening | `port`, `allow` |
| `egress_request` | an allowed connection was opened | `method`, `host`, `port`, `path`, `rule` |
| `egress_response` | an allowed connection closed | `status`, `bytes_up`, `bytes_down`, `duration_ms` |
| `egress_denied` | destination not on the allowlist | `method`, `host`, `port`, `path`, `status: 403` |
| `egress_error` | malformed request or upstream unreachable | `error_code` (`bad_request`, `connect_failed`) |

## Configuration

`ABB_EGRESS_CONFIG` (JSON, set by the host):

```json
{"agent_id": "open-interpreter", "listen_port": 3128,
 "allow": [{"host": "pypi.org", "ports": [443]}, {"host": "*.debian.org", "ports": [80, 443]}]}
```

A rule host is either exact or `*.suffix` (strict subdomains). An empty allowlist
denies everything while still recording each attempt.

On the host side the allowlist comes from `agentbench/runtime/docker/policy.py`
(`EgressSettings`). `ABB_EGRESS=deny` restores the previous in-interceptor denial;
`ABB_EGRESS_ALLOW=host[:port],...` adds destinations.

## Tests

```bash
cd agentbench/services/egress-observer
PYTHONPATH=src python -m pytest tests
```
