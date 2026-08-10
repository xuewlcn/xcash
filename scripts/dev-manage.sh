#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

# shellcheck source=scripts/dev-env.sh
source "$(dirname "${BASH_SOURCE[0]}")/dev-env.sh"

exec uv run python manage.py "$@"
