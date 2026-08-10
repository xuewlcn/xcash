#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

# shellcheck source=scripts/dev-env.sh
source "$(dirname "${BASH_SOURCE[0]}")/dev-env.sh"

SCHEDULE_FILE="${CELERY_BEAT_SCHEDULE_FILE:-/tmp/xcash-celerybeat-schedule}"
LOCK_DIR="${CELERY_BEAT_LOCK_DIR:-/tmp/xcash-celerybeat.lock}"
PID_FILE="${LOCK_DIR}/pid"
child_pid=""

cleanup() {
  local exit_code=$?

  if [[ -n "${child_pid}" ]] && kill -0 "${child_pid}" 2>/dev/null; then
    kill "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" 2>/dev/null || true
  fi

  rm -f "${SCHEDULE_FILE}" "${SCHEDULE_FILE}-shm" "${SCHEDULE_FILE}-wal"
  rm -f "${PID_FILE}"
  rmdir "${LOCK_DIR}" 2>/dev/null || true

  exit "${exit_code}"
}

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  if [[ -f "${PID_FILE}" ]]; then
    stale_pid="$(cat "${PID_FILE}")"
    if [[ -n "${stale_pid}" ]] && kill -0 "${stale_pid}" 2>/dev/null; then
      echo "Celery beat seems to already be running (pid: ${stale_pid}, lock: ${LOCK_DIR})."
      exit 1
    fi
  fi

  rm -f "${PID_FILE}"
  rmdir "${LOCK_DIR}" 2>/dev/null || true

  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    echo "Unable to acquire Celery beat lock: ${LOCK_DIR}"
    exit 1
  fi
fi

trap cleanup EXIT INT TERM

# 每次开发启动前清理调度状态文件，避免上次异常退出后遗留旧的 sqlite shm/wal 文件继续参与调度。
rm -f "${SCHEDULE_FILE}" "${SCHEDULE_FILE}-shm" "${SCHEDULE_FILE}-wal"

uv run celery -A config.celery beat -l INFO -s "${SCHEDULE_FILE}" &
child_pid=$!
echo "${child_pid}" > "${PID_FILE}"
wait "${child_pid}"
