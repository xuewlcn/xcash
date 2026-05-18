#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
UPGRADE_REF="${1:-${UPGRADE_REF:-main}}"
SKIP_GIT_PULL="${SKIP_GIT_PULL:-false}"
QUIESCE_BEFORE_REHEARSAL="${QUIESCE_BEFORE_REHEARSAL:-false}"
CONFIRM_ONLINE_DUMP_RISK="${CONFIRM_ONLINE_DUMP_RISK:-}"
UPGRADE_LOCK_FILE="${UPGRADE_LOCK_FILE:-/tmp/xcash-upgrade.lock}"

COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")
REHEARSAL_COMPOSE=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --profile migration-rehearsal)
TMP_DIR=""

log() {
  printf '[upgrade] %s\n' "$*"
}

die() {
  printf '[upgrade] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  local exit_code=$?

  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi

  "${REHEARSAL_COMPOSE[@]}" rm -sf migration-rehearsal-db >/dev/null 2>&1 || true

  exit "${exit_code}"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

ensure_git_clean() {
  if [[ "${ALLOW_DIRTY_UPGRADE:-false}" == "true" ]]; then
    return
  fi

  if [[ -n "$(git status --porcelain)" ]]; then
    die "git worktree is dirty; commit or stash changes before production upgrade"
  fi
}

pull_code() {
  if [[ "${SKIP_GIT_PULL}" == "true" ]]; then
    log "skip git pull; using current working tree"
    return
  fi

  ensure_git_clean
  log "fetch and fast-forward ${UPGRADE_REF}"
  git fetch --prune
  git checkout "${UPGRADE_REF}"
  git pull --ff-only
  ensure_git_clean
}

wait_for_postgres() {
  local service="$1"
  local compose=("${COMPOSE[@]}")

  if [[ "${service}" == migration-rehearsal-* ]]; then
    compose=("${REHEARSAL_COMPOSE[@]}")
  fi

  log "wait for ${service}"
  "${compose[@]}" exec -T "${service}" sh -c \
    'until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do sleep 1; done'
}

dump_database() {
  local service="$1"
  local output="$2"

  log "dump ${service}"
  "${COMPOSE[@]}" exec -T "${service}" sh -c \
    'pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >"${output}"
}

restore_database() {
  local service="$1"
  local input="$2"
  local compose=("${COMPOSE[@]}")

  if [[ "${service}" == migration-rehearsal-* ]]; then
    compose=("${REHEARSAL_COMPOSE[@]}")
  fi

  log "restore dump into ${service}"
  "${compose[@]}" exec -T "${service}" sh -c \
    'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <"${input}"
}

run_main_manage() {
  local postgres_host="$1"
  shift

  # POSTGRES_PASSWORD 由 compose 的 env_file (.env) 注入，不再通过命令行 -e 传递，
  # 避免短时间内出现在宿主 ps aux 输出中。
  # -T 禁用 PTY，确保 stdout 是干净字节流，避免 ANSI 控制序列/CR 行尾污染 plan 比对。
  "${COMPOSE[@]}" run --rm --no-deps -T \
    -e XCASH_IGNORE_DATABASE_URL=true \
    -e POSTGRES_HOST="${postgres_host}" \
    django python manage.py "$@"
}

run_signer_manage() {
  local postgres_host="$1"
  shift

  # SIGNER_POSTGRES_PASSWORD 由 compose 的 env_file (.env) 注入，理由同 run_main_manage。
  # -T 同样用于消除 PTY 引入的不确定字节，参见 run_main_manage 注释。
  "${COMPOSE[@]}" run --rm --no-deps -T \
    -e SIGNER_POSTGRES_HOST="${postgres_host}" \
    signer bash -lc 'cd /app/signer && python manage.py "$@"' signer-manage "$@"
}

# 从 migrate --plan 输出中只保留真正的迁移行（形如 "  app_label.NNNN_name"），
# 丢弃提示文案、空行、日志、以及可能漏入的 compose 进度残留，让 diff 比对鲁棒。
# 操作明细行（形如 "    Add field xxx"）首字母为大写，不匹配 [a-z_]，会被自然过滤。
extract_plan() {
  grep -E '^[[:space:]]+[a-z_][a-z0-9_]*\.[0-9]{4}_' "$1" || true
}

compare_plans() {
  local rehearsal_plan="$1"
  local production_plan="$2"
  local label="$3"
  local rehearsal_norm="${rehearsal_plan}.norm"
  local production_norm="${production_plan}.norm"

  extract_plan "${rehearsal_plan}" >"${rehearsal_norm}"
  extract_plan "${production_plan}" >"${production_norm}"

  if ! diff -u "${rehearsal_norm}" "${production_norm}"; then
    die "${label} migrate --plan differs between rehearsal and production"
  fi
}

confirm_online_dump_risk() {
  if [[ "${QUIESCE_BEFORE_REHEARSAL}" == "true" ]]; then
    return
  fi

  if [[ "${CONFIRM_ONLINE_DUMP_RISK}" == "yes" ]]; then
    log "online dump risk accepted via CONFIRM_ONLINE_DUMP_RISK=yes"
    return
  fi

  if [[ "${CONFIRM_ONLINE_DUMP_RISK}" == "no" ]]; then
    die "online dump risk was rejected; set QUIESCE_BEFORE_REHEARSAL=true to stop app services before dump"
  fi

  if [[ ! -t 0 ]]; then
    die "online dump risk requires confirmation; set CONFIRM_ONLINE_DUMP_RISK=yes or QUIESCE_BEFORE_REHEARSAL=true"
  fi

  printf '[upgrade] WARNING: app services will keep writing while the production database dump is taken.\n' >&2
  printf '[upgrade] Data migrations may pass on the dump snapshot but fail or behave differently on the live database.\n' >&2
  read -r -p "[upgrade] Continue with online dump? [Y/n] " answer
  answer="${answer:-yes}"

  case "${answer}" in
    y | Y | yes | YES)
      log "online dump risk accepted interactively"
      ;;
    *)
      die "online dump risk was rejected; set QUIESCE_BEFORE_REHEARSAL=true to stop app services before dump"
      ;;
  esac
}

trap cleanup EXIT

require_command docker
require_command git
require_command flock

[[ -f "${ENV_FILE}" ]] || die "env file not found: ${ENV_FILE}"
[[ -f "${COMPOSE_FILE}" ]] || die "compose file not found: ${COMPOSE_FILE}"

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

[[ -n "${POSTGRES_PASSWORD:-}" ]] || die "POSTGRES_PASSWORD is required"
[[ -n "${SIGNER_POSTGRES_PASSWORD:-}" ]] || die "SIGNER_POSTGRES_PASSWORD is required"

# 互斥锁：避免两人同时执行 upgrade.sh 造成 dump/restore/migrate 交叉污染。
# 文件描述符 9 在脚本退出时自动释放，无需在 cleanup 中显式处理。
exec 9>"${UPGRADE_LOCK_FILE}"
flock -n 9 || die "another upgrade is in progress (lock: ${UPGRADE_LOCK_FILE})"

TMP_DIR="$(mktemp -d)"
MAIN_DUMP="${TMP_DIR}/xcash-main.dump"
MAIN_REHEARSAL_PLAN="${TMP_DIR}/main-rehearsal.plan"
MAIN_PRODUCTION_PLAN="${TMP_DIR}/main-production.plan"

pull_code

log "build production images"
"${COMPOSE[@]}" build

log "ensure database and cache dependencies are running"
"${COMPOSE[@]}" up -d django-db signer-db redis
wait_for_postgres django-db
wait_for_postgres signer-db

if [[ "${QUIESCE_BEFORE_REHEARSAL}" == "true" ]]; then
  log "stop app services before rehearsal"
  "${COMPOSE[@]}" stop django worker beat signer || true
fi

confirm_online_dump_risk
dump_database django-db "${MAIN_DUMP}"

log "reset rehearsal databases"
"${REHEARSAL_COMPOSE[@]}" rm -sf migration-rehearsal-db >/dev/null 2>&1 || true
"${REHEARSAL_COMPOSE[@]}" up -d migration-rehearsal-db
wait_for_postgres migration-rehearsal-db

restore_database migration-rehearsal-db "${MAIN_DUMP}"

log "run main database migration rehearsal"
run_main_manage migration-rehearsal-db migrate --plan | tee "${MAIN_REHEARSAL_PLAN}"
run_main_manage migration-rehearsal-db migrate --noinput
run_main_manage migration-rehearsal-db check --deploy

log "stop app services before production migration"
"${COMPOSE[@]}" stop django worker beat signer || true

log "verify production migration plans"
run_main_manage django-db migrate --plan | tee "${MAIN_PRODUCTION_PLAN}"
compare_plans "${MAIN_REHEARSAL_PLAN}" "${MAIN_PRODUCTION_PLAN}" "main database"

log "apply production migrations"
run_main_manage django-db migrate --noinput
run_signer_manage signer-db migrate --noinput

log "run production post-migration setup"
run_main_manage django-db collectstatic --noinput
run_main_manage django-db ensure_default_superuser

log "start application services"
"${COMPOSE[@]}" up -d --remove-orphans

log "upgrade completed"
