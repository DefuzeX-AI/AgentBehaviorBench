#!/usr/bin/env bash
# Install OS-level packages required to build the python venv on a fresh server.
#
# Usage:
#   sudo scripts/install-system-deps.sh
#
# Detects Debian/Ubuntu (apt) or RHEL/CentOS/Rocky/Alma (yum/dnf). On other
# distributions it prints the package list and exits.
set -Eeuo pipefail

PY_PKG_DEBIAN=(python3 python3-venv python3-dev build-essential libffi-dev libssl-dev curl ca-certificates)
PY_PKG_RHEL=(python3 python3-devel gcc gcc-c++ make libffi-devel openssl-devel curl ca-certificates)

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: this script needs root. Run with sudo." >&2
    exit 1
  fi
}

main() {
  require_root
  if command -v apt-get >/dev/null 2>&1; then
    echo "[deps] Detected apt. Installing: ${PY_PKG_DEBIAN[*]}"
    DEBIAN_FRONTEND=noninteractive apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${PY_PKG_DEBIAN[@]}"
  elif command -v dnf >/dev/null 2>&1; then
    echo "[deps] Detected dnf. Installing: ${PY_PKG_RHEL[*]}"
    dnf install -y "${PY_PKG_RHEL[@]}"
  elif command -v yum >/dev/null 2>&1; then
    echo "[deps] Detected yum. Installing: ${PY_PKG_RHEL[*]}"
    yum install -y "${PY_PKG_RHEL[@]}"
  else
    cat <<EOF >&2
ERROR: no supported package manager found (apt-get/dnf/yum).
Install these packages manually, then re-run scripts/deploy.sh bootstrap:
  Debian/Ubuntu : ${PY_PKG_DEBIAN[*]}
  RHEL/CentOS   : ${PY_PKG_RHEL[*]}
EOF
    exit 1
  fi
  echo "[deps] System dependencies installed."
}

main "$@"
