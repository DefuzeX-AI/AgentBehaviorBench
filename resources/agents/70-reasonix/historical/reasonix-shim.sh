#!/bin/sh
# Historical builds only: forward to the source-built binary, dropping any
# `acp` flag this commit does not define (recorded at image build time in
# acp-flags). Every other invocation, and every defined flag, passes unchanged.
real=/opt/reasonix/libexec/reasonix
flags=/opt/reasonix/libexec/acp-flags
[ "$1" = acp ] || exec "$real" "$@"
shift
drop_value=0
first=1
for arg do
    if [ "$first" = 1 ]; then set -- acp; first=0; fi
    if [ "$drop_value" = 1 ]; then drop_value=0; continue; fi
    case "$arg" in
        --*=*|-*=*) name=${arg%%=*}; name=${name#-}; name=${name#-}; inline=1 ;;
        --*|-*) name=${arg#-}; name=${name#-}; inline=0 ;;
        *) set -- "$@" "$arg"; continue ;;
    esac
    if grep -qx -- "$name" "$flags"; then
        set -- "$@" "$arg"
    else
        echo "reasonix historical shim: dropping unsupported acp flag $arg" >&2
        # Value flags launch.py passes as two words; --workspace-only is boolean.
        case "$name" in workspace-only) ;; *) [ "$inline" = 0 ] && drop_value=1 ;; esac
    fi
done
[ "$first" = 1 ] && set -- acp
# Map the non-ACP stopReason "error" of older commits (see acp-stop-reason.py).
exec python3 /opt/reasonix/libexec/acp-stop-reason.py "$real" "$@"
