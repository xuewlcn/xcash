#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

# shellcheck source=scripts/dev-env.sh
source "$(dirname "${BASH_SOURCE[0]}")/dev-env.sh"

export CELERY_STRESS_WORKER_CONCURRENCY="${CELERY_STRESS_WORKER_CONCURRENCY:-2}"

# 压测任务独占队列，避免一次性调度海量 case 时把普通业务 worker 撑满。
exec uv run watchfiles --filter python celery.__main__.main --args "-A config.celery worker -l INFO --pool=threads --concurrency=${CELERY_STRESS_WORKER_CONCURRENCY} -Q stress"
