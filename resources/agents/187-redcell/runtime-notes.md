# Native REDCELL session planner

The transport deploys native PostgreSQL, Redis and SeaweedFS inside the case,
runs native migrations and seed initialization, authenticates through the
original API, and calls `/api/v1/sessions/draft/chat`. Native prompts,
`propose_session`, credentials storage and rate limits remain active.

This entrypoint validates the original session-planning conversation. It does
not launch a Kali engagement or approve a proposed assessment automatically.

SeaweedFS uses its supported `-volume.port=8081` setting because the default
8080 conflicts with ABB's interception proxy in the shared network namespace.
The S3 endpoint remains on 8333. Readiness uses the native `/healthz` endpoint;
service exits and redacted service logs are retained on failure.

Services are local to the case and are terminated afterward. The image runs
Linux containers on a Linux Docker engine, including Docker Desktop hosts;
the build commands do not hardcode a CPU architecture.
