#!/bin/sh
# Installed only by historical/Dockerfile, and only when the built revision's
# `reasonix acp` lacks a flag that bootstrap/launch.py passes (1.x releases
# have no --permission-mode; some have no --profile). Those flags are dropped;
# every other argument and every other subcommand reach the binary unchanged.
set -eu
real=/opt/reasonix/libexec/reasonix
unsupported='@UNSUPPORTED@'
[ "${1:-}" = acp ] || exec "$real" "$@"
echo "reasonix (historical build): ignoring acp flags not defined by this revision: $unsupported" >&2
skip=0
for arg do
  shift
  if [ "$skip" = 1 ]; then skip=0; continue; fi
  case $arg in
    --*)
      name=${arg#--}; name=${name%%=*}
      case " $unsupported " in
        *" $name "*)
          # --workspace-only is the launcher's only boolean flag; the others take a value.
          case $arg in *=*) ;; *) [ "$name" = workspace-only ] || skip=1 ;; esac
          continue ;;
      esac ;;
  esac
  set -- "$@" "$arg"
done
exec "$real" "$@"
