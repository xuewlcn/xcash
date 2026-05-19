#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

# signer 库持有所有钱包私钥，上线流程不对 signer 做带数据的演练（仅 schema-only），
# 因此 signer 的迁移必须是纯 schema-only：禁止 RunPython / RunSQL，避免出现
# data migration 在生产因数据形态差异 / 锁竞争失败但演练无法发现的盲区。
# 若确有需要修改 signer 数据，写一次性 management command 在 upgrade 前后手动跑。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIGNER_MIGRATIONS_GLOB="${SCRIPT_DIR}/../signer/*/migrations"

shopt -s nullglob
matches=""
for dir in ${SIGNER_MIGRATIONS_GLOB}; do
  hits=$(grep -nE 'RunPython|RunSQL' "${dir}"/*.py 2>/dev/null || true)
  if [[ -n "${hits}" ]]; then
    matches+="${hits}"$'\n'
  fi
done

if [[ -n "${matches}" ]]; then
  printf '[check-signer-no-runpython] signer migrations must be schema-only.\n' >&2
  printf '[check-signer-no-runpython] Found forbidden RunPython/RunSQL:\n' >&2
  printf '%s' "${matches}" >&2
  exit 1
fi
