#!/bin/sh
# Local acceptance only. When the host forwards WATCHTOWER_LOOPBACK_FIXTURE=1,
# serve the static site below on the container's own loopback (127.0.0.1:8000)
# so the native scanners have a real HTTP service to observe. Unset, this only
# runs the launch command unchanged.
if [ "${WATCHTOWER_LOOPBACK_FIXTURE:-}" = "1" ]; then
    python -m http.server 8000 --bind 127.0.0.1 \
        --directory /opt/watchtower-fixture/site >/dev/null 2>&1 &
fi
exec "$@"
