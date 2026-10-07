#!/usr/bin/env bash
# One-command server deployment helper for python-lingjing-ai-server.
#
# Subcommands:
#   bootstrap   Install deps, run smoke import test, then start the server
#               (the one-command entry point for a fresh server).
#   install     Create venv and install requirements.txt only.
#   start       Start uvicorn in the background (creates pid/log).
#   stop        Graceful stop, falls back to SIGKILL after 10s.
#   restart     stop && start.
#   status      Print pid and effective endpoint.
#   logs        tail -f the uvicorn log.
#   ws-logs     tail -f the WebSocket traffic log (all send/receive frames).
#   test        Run pytest from the venv (uses requirements-dev.txt).
#   smoke       Import app.main once to verify the install is wired up.
#   uninstall   Remove venv, pid, logs (data/ kept).
#
# Environment overrides (also picked up from .env):
#   PYTHON_BIN          Specific python interpreter (default: auto-detect >=3.10).
#   VENV_DIR            Virtualenv path (default: <repo>/.venv).
#   ENV_FILE            .env file path (default: <repo>/.env).
#   APP_HOST APP_PORT   Bind address/port (default: 0.0.0.0:9909).
#   WORKERS             uvicorn workers (default: 1 — see SQLite caveat below).
#   PIP_INDEX_URL       Set to a mirror for faster install in CN, e.g.
#                       https://pypi.tuna.tsinghua.edu.cn/simple
#   MIRROR=cn           Shortcut that sets PIP_INDEX_URL to Tsinghua mirror.
#   PID_FILE LOG_FILE   Override pid/log locations.
#   WS_LOG_FILE         WebSocket traffic log (default: logs/websocket.log).
#
# SQLite caveat: the bundled SQLite stores share an in-process connection pool,
# so WORKERS>1 can cause `database is locked` under heavy realtime writes.
# Stick to 1 worker unless you have switched the backing store.
set -Eeuo pipefail

# All paths are derived from the repository root unless overridden by env vars.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-${PROJECT_DIR}/.venv}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env}"
PID_FILE="${PID_FILE:-${PROJECT_DIR}/run/uvicorn.pid}"
LOG_FILE="${LOG_FILE:-${PROJECT_DIR}/logs/uvicorn.log}"
WS_LOG_FILE="${WS_LOG_FILE:-${PROJECT_DIR}/logs/websocket.log}"
HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-9909}"
WORKERS="${WORKERS:-1}"
DATA_DIR="${DATA_DIR:-${PROJECT_DIR}/data}"
REQUIRED_PY_MAJOR=3
REQUIRED_PY_MINOR=10

cd "${PROJECT_DIR}"

log()  { printf '[deploy] %s\n' "$*"; }
warn() { printf '[deploy] WARN: %s\n' "$*" >&2; }
fail() { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

load_env() {
  # Precedence: explicit shell env > .env > built-in defaults. This matches
  # operator intuition — when you do `APP_PORT=9000 deploy.sh start`, you mean
  # it and the value committed to .env must NOT clobber the override.
  local explicit_host="${APP_HOST:-}"
  local explicit_port="${APP_PORT:-}"
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi
  [[ -n "${explicit_host}" ]] && APP_HOST="${explicit_host}"
  [[ -n "${explicit_port}" ]] && APP_PORT="${explicit_port}"
  HOST="${APP_HOST:-${HOST}}"
  PORT="${APP_PORT:-${PORT}}"
}

py_meets_version() {
  # Return 0 if $1 points to a python >= REQUIRED_PY_*.
  local candidate="$1"
  command -v "${candidate}" >/dev/null 2>&1 || return 1
  "${candidate}" -c "
import sys
sys.exit(0 if sys.version_info >= (${REQUIRED_PY_MAJOR}, ${REQUIRED_PY_MINOR}) else 1)
" >/dev/null 2>&1
}

ensure_python() {
  # Honor explicit PYTHON_BIN if it satisfies the version floor.
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    py_meets_version "${PYTHON_BIN}" \
      || fail "PYTHON_BIN=${PYTHON_BIN} does not satisfy Python >= ${REQUIRED_PY_MAJOR}.${REQUIRED_PY_MINOR}"
    return
  fi
  # Probe in descending preference. Newer interpreters are picked first because
  # the project is developed against 3.13 and only requires >=3.10.
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if py_meets_version "${candidate}"; then
      PYTHON_BIN="$(command -v "${candidate}")"
      log "Using interpreter: ${PYTHON_BIN} ($("${PYTHON_BIN}" -V 2>&1))"
      return
    fi
  done
  fail "No Python >= ${REQUIRED_PY_MAJOR}.${REQUIRED_PY_MINOR} found on PATH. Install python${REQUIRED_PY_MAJOR}.${REQUIRED_PY_MINOR}+ (and python3-venv on Debian/Ubuntu) or set PYTHON_BIN."
}

ensure_env_file() {
  # Bootstrap .env on a fresh server; operators should then edit secrets/DB URL.
  if [[ ! -f "${ENV_FILE}" ]]; then
    if [[ -f "${PROJECT_DIR}/.env.example" ]]; then
      cp "${PROJECT_DIR}/.env.example" "${ENV_FILE}"
      log "Created ${ENV_FILE} from .env.example. Review production settings (AI_API_KEY, DB paths, ...)."
    else
      warn "${ENV_FILE} not found and .env.example is missing. The app will fall back to built-in defaults."
    fi
  fi
}

ensure_runtime_dirs() {
  # SQLite stream storage, pid files, and logs should exist before uvicorn starts.
  mkdir -p "${DATA_DIR}" "$(dirname "${PID_FILE}")" "$(dirname "${LOG_FILE}")"
}

resolve_mirror() {
  # `MIRROR=cn` is a convenience shortcut for users deploying inside China.
  # An explicit PIP_INDEX_URL always wins so CI can pin its own index.
  if [[ -z "${PIP_INDEX_URL:-}" && "${MIRROR:-}" == "cn" ]]; then
    export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
    export PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-https://pypi.org/simple}"
    log "Using Tsinghua PyPI mirror: ${PIP_INDEX_URL}"
  elif [[ -n "${PIP_INDEX_URL:-}" ]]; then
    log "Using PIP_INDEX_URL: ${PIP_INDEX_URL}"
  fi
}

pip_install() {
  # Centralized pip wrapper so all install calls share the same flags & retries.
  local args=(install --disable-pip-version-check --no-input)
  if [[ "${PIP_RETRIES:-3}" -gt 0 ]]; then
    args+=(--retries "${PIP_RETRIES:-3}" --timeout "${PIP_TIMEOUT:-60}")
  fi
  "${VENV_DIR}/bin/python" -m pip "${args[@]}" "$@"
}

# Sentinel file lets `start` skip re-running pip when requirements.txt has not
# changed. This is what makes `start` safe on air-gapped servers: once
# `bootstrap` finished successfully, subsequent restarts never touch the network.
INSTALL_STAMP="${VENV_DIR}/.deps_installed.stamp"

current_install_signature() {
  # Hash python version + requirements.txt content so any change forces a
  # re-install. We strip the filename from sha256sum's output because absolute
  # vs relative paths would otherwise produce different signatures for the
  # same file content.
  local py_version
  py_version="$("${VENV_DIR}/bin/python" -V 2>&1 || true)"
  local req_hash
  req_hash="$(sha256sum "${PROJECT_DIR}/requirements.txt" 2>/dev/null | awk '{print $1}')"
  printf 'py=%s req=%s\n' "${py_version}" "${req_hash}" | sha256sum | awk '{print $1}'
}

deps_up_to_date() {
  # Returns 0 if the stamp file matches the current requirements signature.
  [[ -x "${VENV_DIR}/bin/python" ]] || return 1
  [[ -f "${INSTALL_STAMP}" ]] || return 1
  local current
  current="$(current_install_signature)"
  local stored
  stored="$(cat "${INSTALL_STAMP}" 2>/dev/null || true)"
  [[ "${current}" == "${stored}" ]]
}

mark_deps_installed() {
  current_install_signature >"${INSTALL_STAMP}"
}

install_dependencies() {
  # Keep dependencies isolated from the server's system Python.
  ensure_python
  resolve_mirror
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    log "Creating virtualenv at ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}" \
      || fail "venv creation failed. On Debian/Ubuntu install: apt install python3-venv python3-dev build-essential"
  fi
  if [[ "${FORCE_INSTALL:-0}" != "1" ]] && deps_up_to_date; then
    log "Dependencies already up to date (stamp matches). Skipping pip install."
    return
  fi
  # Pip's own upgrade is best-effort — on offline servers it's normal to skip.
  log "Upgrading pip / wheel / setuptools (best-effort)"
  pip_install --upgrade pip wheel setuptools \
    || warn "pip upgrade failed (offline?). Continuing with the existing pip."
  log "Installing requirements.txt"
  pip_install -r "${PROJECT_DIR}/requirements.txt" \
    || fail "pip install -r requirements.txt failed. Set MIRROR=cn for a CN PyPI mirror, or check network/proxy."
  mark_deps_installed
}

install_dev_dependencies() {
  install_dependencies
  log "Installing requirements-dev.txt"
  pip_install -r "${PROJECT_DIR}/requirements-dev.txt" \
    || fail "pip install -r requirements-dev.txt failed."
}

smoke_test() {
  # Catch missing deps / broken imports BEFORE uvicorn forks into the background,
  # because a uvicorn import failure only shows up in the log file.
  log "Smoke test: importing app.main"
  local smoke_log
  smoke_log="$(mktemp 2>/dev/null || echo "${PROJECT_DIR}/run/smoke.log")"
  if ! PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}" \
       "${VENV_DIR}/bin/python" -c "import app.main; print('OK', app.main.app.title)" \
       >"${smoke_log}" 2>&1; then
    warn "Smoke test failed. Output:"
    cat "${smoke_log}" >&2 || true
    rm -f "${smoke_log}"
    fail "app.main import failed — fix the error above before starting uvicorn."
  fi
  rm -f "${smoke_log}"
  log "Smoke test passed."
}

run_tests() {
  install_dev_dependencies
  log "Running pytest"
  PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}" \
    "${VENV_DIR}/bin/python" -m pytest -q "$@"
}

is_running() {
  # A stale pid file is treated as not running.
  [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" >/dev/null 2>&1
}

check_port_free() {
  # Best-effort port-in-use detection. Missing ss/lsof is non-fatal.
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -E "[:.]${port}$" >/dev/null; then
      warn "Port ${port} is already in use. uvicorn will fail to bind. Use 'deploy.sh stop' or change APP_PORT."
      return 1
    fi
  fi
  return 0
}

start_app() {
  # Start uvicorn as a background process suitable for simple VM deployments.
  load_env
  ensure_env_file
  ensure_runtime_dirs

  if is_running; then
    log "Already running: pid $(cat "${PID_FILE}")"
    return
  fi

  # `start` reuses an existing venv whenever possible. Use `bootstrap` or
  # `FORCE_INSTALL=1 start` to force a re-install (e.g. after editing requirements).
  if [[ -x "${VENV_DIR}/bin/python" ]]; then
    if deps_up_to_date && [[ "${FORCE_INSTALL:-0}" != "1" ]]; then
      log "Reusing existing venv at ${VENV_DIR}"
    else
      install_dependencies
    fi
  else
    install_dependencies
  fi
  smoke_test

  check_port_free "${PORT}" || true

  log "Starting uvicorn on ${HOST}:${PORT} (workers=${WORKERS})"
  nohup "${VENV_DIR}/bin/python" -m uvicorn app.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    >>"${LOG_FILE}" 2>&1 &

  echo "$!" >"${PID_FILE}"
  # Wait briefly so we can give the operator immediate feedback.
  local i
  for i in {1..20}; do
    if is_running; then
      sleep 0.25
    else
      break
    fi
  done

  if is_running; then
    log "Started: pid $(cat "${PID_FILE}")   endpoint http://${HOST}:${PORT}/health"
    log "Logs:    ${LOG_FILE}"
    log "WS logs: ${WS_LOG_FILE}"
  else
    warn "uvicorn exited shortly after startup. Last log lines:"
    tail -n 80 "${LOG_FILE}" >&2 || true
    rm -f "${PID_FILE}"
    exit 1
  fi
}

stop_app() {
  # Try graceful shutdown first, then force kill if the process is stuck.
  if ! is_running; then
    log "Not running"
    rm -f "${PID_FILE}"
    return
  fi

  local pid
  pid="$(cat "${PID_FILE}")"
  log "Stopping pid ${pid}"
  kill "${pid}" 2>/dev/null || true
  local i
  for i in {1..20}; do
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      rm -f "${PID_FILE}"
      log "Stopped"
      return
    fi
    sleep 0.5
  done

  warn "Process did not stop gracefully, killing ${pid}"
  kill -9 "${pid}" >/dev/null 2>&1 || true
  rm -f "${PID_FILE}"
}

status_app() {
  # Print the effective endpoint after loading .env.
  load_env
  if is_running; then
    log "Running: pid $(cat "${PID_FILE}")   endpoint http://${HOST}:${PORT}"
  else
    log "Not running (port ${PORT})"
  fi
}

show_logs() {
  # Follow the uvicorn log file for quick operational debugging.
  mkdir -p "$(dirname "${LOG_FILE}")"
  touch "${LOG_FILE}"
  tail -n "${TAIL_LINES:-120}" -f "${LOG_FILE}"
}

show_ws_logs() {
  # Follow dedicated WebSocket send/receive traffic.
  mkdir -p "$(dirname "${WS_LOG_FILE}")"
  touch "${WS_LOG_FILE}"
  tail -n "${TAIL_LINES:-120}" -f "${WS_LOG_FILE}"
}

bootstrap_all() {
  # The "one command" entry point: prep filesystem, install, smoke test, start.
  log "Bootstrapping python-lingjing-ai-server in ${PROJECT_DIR}"
  load_env
  ensure_env_file
  ensure_runtime_dirs
  install_dependencies
  smoke_test
  start_app
}

uninstall_all() {
  # Tear down venv + runtime artifacts but keep data/ (DB files) intact.
  if is_running; then
    stop_app
  fi
  if [[ -d "${VENV_DIR}" ]]; then
    log "Removing ${VENV_DIR}"
    rm -rf "${VENV_DIR}"
  fi
  rm -f "${PID_FILE}"
  if [[ -f "${LOG_FILE}" ]]; then
    log "Truncating ${LOG_FILE}"
    : >"${LOG_FILE}"
  fi
  log "Done. Data files under ${DATA_DIR} preserved."
}

usage() {
  cat <<'EOF'
Usage: scripts/deploy.sh {bootstrap|install|start|stop|restart|status|logs|ws-logs|test|smoke|uninstall}

Quick start on a fresh server:
    scripts/deploy.sh bootstrap         # install + smoke test + start

Daily ops:
    scripts/deploy.sh start | stop | restart | status | logs | ws-logs

CN mirror shortcut:
    MIRROR=cn scripts/deploy.sh bootstrap
EOF
}

case "${1:-bootstrap}" in
  bootstrap)
    bootstrap_all
    ;;
  install)
    ensure_env_file
    ensure_runtime_dirs
    install_dependencies
    ;;
  start)
    start_app
    ;;
  stop)
    stop_app
    ;;
  restart)
    stop_app
    start_app
    ;;
  status)
    status_app
    ;;
  logs)
    show_logs
    ;;
  ws-logs)
    show_ws_logs
    ;;
  test)
    shift || true
    run_tests "$@"
    ;;
  smoke)
    ensure_runtime_dirs
    install_dependencies
    smoke_test
    ;;
  uninstall)
    uninstall_all
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
