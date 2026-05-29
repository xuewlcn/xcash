#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

ENV_FILE="${ENV_FILE:-.env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Go signer 用 SQLite，开机自建表，无需独立迁移步骤；signer 由 `make dev-up-signer` 单独本地运行。
# 这里只初始化主库与本地联调链配置。
ENV_FILE="${ENV_FILE}" "${SCRIPT_DIR}/dev-manage.sh" migrate
ENV_FILE="${ENV_FILE}" "${SCRIPT_DIR}/dev-manage.sh" init_local_chains
