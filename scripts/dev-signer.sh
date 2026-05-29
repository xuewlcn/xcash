#!/bin/bash
# 本地运行 Go signer（dev）。与 django 经 uv 本地运行对称：signer 也直接 go run，
# 不进容器。SQLite 落本地文件，监听 :8010（对应 dev settings 的 SIGNER_BASE_URL）。
set -o errexit
set -o nounset
set -o pipefail

ENV_FILE="${ENV_FILE:-.env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${PROJECT_DIR}/${ENV_FILE}" || -f "${ENV_FILE}" ]]; then
  # 复用主应用同一份 .env，确保 SIGNER_SHARED_SECRET 两侧一致，HMAC 才能校验通过。
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

# dev 默认：开 DEBUG（跳过限流、放宽密钥校验），监听 8010，sqlite 落本地（已被 .gitignore）。
export SIGNER_DEBUG="${SIGNER_DEBUG:-true}"
export SIGNER_LISTEN_ADDR="${SIGNER_LISTEN_ADDR:-:8010}"
export SIGNER_DB_PATH="${SIGNER_DB_PATH:-${PROJECT_DIR}/signer/dev-signer.sqlite}"

cd "${PROJECT_DIR}/signer"
exec go run ./cmd/signer
