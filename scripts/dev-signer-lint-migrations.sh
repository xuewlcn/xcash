#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

BASE_REF="${MIGRATION_LINTER_BASE:-origin/main}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIGNER_ROOT="$(cd "${SCRIPT_DIR}/../signer" && pwd)"

if ! git rev-parse --verify --quiet "${BASE_REF}" >/dev/null; then
  BASE_REF="HEAD"
fi

export SIGNER_ENABLE_MIGRATION_LINTER=true

exec "${SCRIPT_DIR}/dev-signer-manage.sh" lintmigrations \
  --git-commit-id "${BASE_REF}" \
  --project-root-path "${SIGNER_ROOT}" \
  --no-cache
