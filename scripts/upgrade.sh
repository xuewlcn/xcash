#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

ENV_FILE="${ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
UPGRADE_REF="${1:-${UPGRADE_REF:-main}}"
SKIP_GIT_PULL="${SKIP_GIT_PULL:-false}"
# 默认空字符串 → 触发交互确认；显式传 true/false 可覆盖默认。
STOP_BEFORE_REHEARSAL="${STOP_BEFORE_REHEARSAL:-}"
UPGRADE_LOCK_FILE="${UPGRADE_LOCK_FILE:-/tmp/xcash-upgrade.lock}"

# cleanup 需要区分失败发生在哪个阶段：
# - production migrate 前：production 库未被触碰，只恢复本脚本停过的旧容器
# - production migrate 中：DB 可能处于中间态，不自动启动业务服务
# - production migrate 后：DB 已到新 schema，后置步骤失败时按新镜像尝试恢复服务
LOCK_ACQUIRED=false
APP_SERVICES_STOP_REQUESTED=false
APP_SERVICES_TO_RESTORE=()
PRODUCTION_MIGRATE_STARTED=false
PRODUCTION_MIGRATE_COMPLETED=false

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

  # 失败退出时把 TMP_DIR 下所有 *.log 一次性回放到 stderr，
  # 避免长流程中真正的失败原因被后续输出冲掉。
  # plan/.norm 等结构化数据不在回放范围（无人类可读价值，且 die 之前已经 diff 过）。
  if [[ "${exit_code}" -ne 0 && -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    shopt -s nullglob
    local log_file
    for log_file in "${TMP_DIR}"/*.log; do
      printf '\n[upgrade] === replay %s ===\n' "$(basename "${log_file}")" >&2
      cat "${log_file}" >&2
    done
    shopt -u nullglob
  fi

  # 只有持有升级锁的进程才允许恢复服务或清理 rehearsal 容器，避免并发启动失败
  # 的第二个进程误碰正在执行升级的一号进程。
  if [[ "${exit_code}" -ne 0 && "${LOCK_ACQUIRED}" == "true" ]]; then
    if [[ "${PRODUCTION_MIGRATE_STARTED}" == "true" && "${PRODUCTION_MIGRATE_COMPLETED}" != "true" ]]; then
      printf '\n[upgrade] WARNING: production migrate was in progress when failure occurred.\n' >&2
      printf '[upgrade] NOT restarting services automatically — DB may be mid-migration.\n' >&2
      printf '[upgrade] Verify schema manually, then resume with: docker compose up -d\n' >&2
    elif [[ "${PRODUCTION_MIGRATE_COMPLETED}" == "true" ]]; then
      printf '\n[upgrade] failure after production migrations completed; starting services on migrated schema\n' >&2
      run_cleanup_command "start services on migrated schema" \
        "${COMPOSE[@]}" up -d --remove-orphans
    elif [[ "${APP_SERVICES_STOP_REQUESTED}" == "true" ]]; then
      printf '\n[upgrade] failure before production migrate; restoring previously stopped app services\n' >&2
      restore_pre_migration_services
    fi
  fi

  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi

  if [[ "${LOCK_ACQUIRED}" == "true" ]]; then
    "${REHEARSAL_COMPOSE[@]}" rm -sf migration-rehearsal-db >/dev/null 2>&1 || true
  fi

  exit "${exit_code}"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

run_cleanup_command() {
  local description="$1"
  shift
  local output

  if ! output="$("$@" 2>&1)"; then
    printf '[upgrade] WARNING: failed to %s\n' "${description}" >&2
    printf '%s\n' "${output}" >&2
  fi
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

dump_main_database() {
  local output="$1"

  log "dump django-db (full)"
  "${COMPOSE[@]}" exec -T django-db sh -c \
    'pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >"${output}"
}

restore_main_database() {
  local service="$1"
  local input="$2"

  log "restore main dump into ${service}"
  "${REHEARSAL_COMPOSE[@]}" exec -T "${service}" sh -c \
    'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <"${input}"
}

run_main_manage() {
  local postgres_host="$1"
  shift

  # POSTGRES_PASSWORD 由 compose 的 env_file (.env) 注入，不再通过命令行 -e 传递，
  # 避免短时间内出现在宿主 ps aux 输出中。
  # one-off 容器在 compose 网络内访问 django-db，必须使用容器端口 5432，
  # 避免 .env 中宿主映射端口污染生产/演练 manage.py 连接。
  # -T 禁用 PTY，确保 stdout 是干净字节流，避免 ANSI 控制序列/CR 行尾污染 plan 比对。
  "${COMPOSE[@]}" run --rm --no-deps -T \
    -e XCASH_IGNORE_DATABASE_URL=true \
    -e POSTGRES_HOST="${postgres_host}" \
    -e POSTGRES_PORT=5432 \
    django python manage.py "$@"
}

stop_app_services() {
  local reason="$1"
  local running_services

  log "stop app services ${reason}"
  if [[ "${APP_SERVICES_STOP_REQUESTED}" != "true" ]]; then
    running_services="$("${COMPOSE[@]}" ps --services --filter status=running django worker beat signer)"
    if [[ -n "${running_services}" ]]; then
      while IFS= read -r service; do
        [[ -n "${service}" ]] && APP_SERVICES_TO_RESTORE+=("${service}")
      done <<<"${running_services}"
    fi
  fi

  APP_SERVICES_STOP_REQUESTED=true
  "${COMPOSE[@]}" stop django worker beat signer
}

restore_pre_migration_services() {
  if [[ "${#APP_SERVICES_TO_RESTORE[@]}" -eq 0 ]]; then
    printf '[upgrade] no app services were running before stop; nothing to restore\n' >&2
    return
  fi

  run_cleanup_command "restore previously running app services" \
    "${COMPOSE[@]}" start "${APP_SERVICES_TO_RESTORE[@]}"
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

# 默认停机演练：dump 前先停 django/worker/beat/signer，让演练库快照与
# production migrate 时刻完全一致；用户输入 n/no 才走"在线 dump"模式
# （停机时长更短，但演练快照与上线时刻数据可能不一致，data migration 风险更高）。
# 非交互场景（无 TTY 且未显式设 STOP_BEFORE_REHEARSAL）一律默认停机，安全优先。
resolve_stop_before_rehearsal() {
  if [[ "${STOP_BEFORE_REHEARSAL}" == "true" ]]; then
    log "STOP_BEFORE_REHEARSAL=true; will stop app services before rehearsal dump"
    return
  fi

  if [[ "${STOP_BEFORE_REHEARSAL}" == "false" ]]; then
    log "STOP_BEFORE_REHEARSAL=false; keep app services running during rehearsal dump"
    return
  fi

  if [[ ! -t 0 ]]; then
    log "no TTY; defaulting to STOP_BEFORE_REHEARSAL=true (safer rehearsal)"
    STOP_BEFORE_REHEARSAL=true
    return
  fi

  printf '[upgrade] About to dump production for rehearsal.\n' >&2
  printf '[upgrade] Default: stop app services first (rehearsal == production at migrate time, longer downtime).\n' >&2
  printf '[upgrade] Choose "n" to keep services running (shorter downtime, rehearsal snapshot may drift).\n' >&2
  read -r -p "[upgrade] Stop services before dump? [Y/n] " answer
  answer="${answer:-yes}"

  case "${answer}" in
    n | N | no | NO)
      STOP_BEFORE_REHEARSAL=false
      log "online dump selected; rehearsal data may diverge from production at migrate time"
      ;;
    *)
      STOP_BEFORE_REHEARSAL=true
      log "quiesced dump selected; will stop app services before dump"
      ;;
  esac
}

trap cleanup EXIT

require_command docker
require_command git
require_command flock

[[ -f "${ENV_FILE}" ]] || die "env file not found: ${ENV_FILE}"
[[ -f "${COMPOSE_FILE}" ]] || die "compose file not found: ${COMPOSE_FILE}"

# signer 专属密钥文件 .env.signer 若缺失则由 init_env.sh 生成（复用 .env 中已有的
# 共享项，绝不重随机 SIGNER_MNEMONIC_ENCRYPTION_KEY，故对已加密助记词安全）。
if [[ ! -f .env.signer ]]; then
  log "ensure .env.signer exists (generate via init_env.sh)"
  "$(dirname "$0")/init_env.sh"
fi
[[ -f .env.signer ]] || die "缺少 .env.signer（请先运行 scripts/init_env.sh）"

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

[[ -n "${POSTGRES_PASSWORD:-}" ]] || die "POSTGRES_PASSWORD is required"

# 互斥锁：避免两人同时执行 upgrade.sh 造成 dump/restore/migrate 交叉污染。
# 文件描述符 9 在脚本退出时自动释放，无需在 cleanup 中显式处理。
exec 9>"${UPGRADE_LOCK_FILE}"
flock -n 9 || die "another upgrade is in progress (lock: ${UPGRADE_LOCK_FILE})"
LOCK_ACQUIRED=true

TMP_DIR="$(mktemp -d)"
MAIN_DUMP="${TMP_DIR}/xcash-main.dump"
MAIN_REHEARSAL_PLAN="${TMP_DIR}/main-rehearsal.plan"
MAIN_PRODUCTION_PLAN="${TMP_DIR}/main-production.plan"

pull_code

log "build production images"
"${COMPOSE[@]}" build

# signer 现为 Go + SQLite：无独立 DB 容器，开机自建表，无需迁移彩排。
log "ensure database and cache dependencies are running"
"${COMPOSE[@]}" up -d django-db redis
wait_for_postgres django-db

resolve_stop_before_rehearsal

if [[ "${STOP_BEFORE_REHEARSAL}" == "true" ]]; then
  stop_app_services "before rehearsal dump"
fi

dump_main_database "${MAIN_DUMP}"

log "reset rehearsal database"
"${REHEARSAL_COMPOSE[@]}" rm -sf migration-rehearsal-db >/dev/null 2>&1 || true
"${REHEARSAL_COMPOSE[@]}" up -d migration-rehearsal-db
wait_for_postgres migration-rehearsal-db

restore_main_database migration-rehearsal-db "${MAIN_DUMP}"

log "run main database migration rehearsal"
# plan 阶段输出短：tee 同时写 plan 文件（用于比对）+ log 文件（用于失败回放），stdout 静默。
run_main_manage migration-rehearsal-db migrate --plan 2>&1 \
  | tee "${TMP_DIR}/main-rehearsal-plan.log" >"${MAIN_REHEARSAL_PLAN}"
# migrate / check 阶段输出长且重要：tee 写 log 文件 + terminal 实时显示。
run_main_manage migration-rehearsal-db migrate --noinput 2>&1 \
  | tee "${TMP_DIR}/main-rehearsal-migrate.log"
run_main_manage migration-rehearsal-db check --deploy 2>&1 \
  | tee "${TMP_DIR}/main-rehearsal-check.log"

if [[ "${STOP_BEFORE_REHEARSAL}" != "true" ]]; then
  stop_app_services "before production migration"
fi

log "verify production migration plans"
run_main_manage django-db migrate --plan 2>&1 \
  | tee "${TMP_DIR}/main-production-plan.log" >"${MAIN_PRODUCTION_PLAN}"
compare_plans "${MAIN_REHEARSAL_PLAN}" "${MAIN_PRODUCTION_PLAN}" "main database"

# 跨过此线后 production 主库可能进入（部分）迁移后状态；迁移完成后
# cleanup 才会按新 schema 尝试拉起服务。signer 用 SQLite，开机自建表，不在此流程内。
PRODUCTION_MIGRATE_STARTED=true

log "apply production migrations"
run_main_manage django-db migrate --noinput 2>&1 \
  | tee "${TMP_DIR}/main-production-migrate.log"
PRODUCTION_MIGRATE_COMPLETED=true

log "run production post-migration setup"
run_main_manage django-db collectstatic --noinput
run_main_manage django-db ensure_default_superuser

log "start application services"
"${COMPOSE[@]}" up -d --remove-orphans

log "upgrade completed"
