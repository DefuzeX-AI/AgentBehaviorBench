#!/bin/sh
# Build-only public release fetcher. Never used as an Agent tool or model client.
set -eu
[ "$#" -eq 3 ] || exit 64
url=$1
out=$2
expected=$3
[ "${#expected}" -eq 64 ] || exit 64
case "$expected" in *[!0-9a-f]*) exit 64;; esac
case "$url" in https://github.com/*) ;; *) exit 64;; esac
if [ -f "$out" ] && printf '%s  %s\n' "$expected" "$out" | sha256sum --check --status; then
    printf 'PUBLIC_RELEASE_CACHED_SHA256_VERIFIED\n' >&2
    exit 0
fi
attempt=1
last=1
while [ "$attempt" -le 3 ]; do
    offset=0
    if [ -f "$out" ]; then offset=$(wc -c < "$out" | tr -d ' '); fi
    printf 'PUBLIC_RELEASE_FETCH attempt=%s resume_bytes=%s\n' "$attempt" "$offset" >&2
    if curl --fail --location --retry 0 --connect-timeout 20 --max-time 600 \
        --continue-at - --output "$out" "$url"; then
        if printf '%s  %s\n' "$expected" "$out" | sha256sum --check --status; then
            printf 'PUBLIC_RELEASE_SHA256_VERIFIED\n' >&2
            exit 0
        fi
        printf 'Public release SHA256 mismatch; refusing installation\n' >&2
        exit 65
    else
        last=$?
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -le 3 ]; then sleep 2; fi
done
exit "$last"
