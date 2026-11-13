#!/bin/sh
# Installed by historical/Dockerfile only when the built revision's `reasonix acp`
# rejects --permission-mode ("flag provided but not defined"), as the 1.x releases
# do. bootstrap/launch.py always passes `--permission-mode auto`; this drops that
# flag and its value, so such a session starts in the revision's default ask mode
# and ABB answers its permission requests with the unit's permission_policy.
# Every other argument and every other subcommand reach the binary unchanged.
set -eu
real=/opt/reasonix/libexec/reasonix
[ "${1:-}" = acp ] || exec "$real" "$@"
echo "reasonix (historical build): dropping --permission-mode; this revision's acp does not define it" >&2
skip=0
for arg do
  shift
  if [ "$skip" = 1 ]; then skip=0; continue; fi
  case $arg in
    --permission-mode) skip=1; continue ;;
    --permission-mode=*) continue ;;
  esac
  set -- "$@" "$arg"
done
exec "$real" "$@"
