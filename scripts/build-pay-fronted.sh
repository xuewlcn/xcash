#!/usr/bin/env bash

set -o errexit
set -o pipefail
set -o nounset

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAY_FRONTEND_DIR="${ROOT_DIR}/pay-fronted"
STATIC_PAY_DIR="${ROOT_DIR}/xcash/static/pay"
BUILD_TMP_DIR="${ROOT_DIR}/xcash/static/.pay-build-tmp"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm not found. Install pnpm or enable it with corepack before building pay-fronted." >&2
  exit 1
fi

rm -rf "${BUILD_TMP_DIR}"
trap 'rm -rf "${BUILD_TMP_DIR}"' EXIT

(
  cd "${PAY_FRONTEND_DIR}"
  pnpm build --outDir "${BUILD_TMP_DIR}" --emptyOutDir
)

find "${BUILD_TMP_DIR}" -name .DS_Store -type f -delete

rm -rf "${STATIC_PAY_DIR}"
mv "${BUILD_TMP_DIR}" "${STATIC_PAY_DIR}"

echo "pay-fronted built into ${STATIC_PAY_DIR}"
