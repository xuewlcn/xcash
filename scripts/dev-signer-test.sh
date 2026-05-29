#!/bin/bash
# Go signer 提交前检查：vet + 全量测试（含派生/签名 parity）。供 pre-commit 调用。
set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}/signer"
go vet ./...
# 与生产同路径：纯 Go secp256k1，保证 parity 在无 cgo 下也成立。
CGO_ENABLED=0 go test ./...
