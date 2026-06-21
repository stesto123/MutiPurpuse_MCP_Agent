#!/usr/bin/env bash
set -euo pipefail

PYTHONPATH="${PYTHONPATH:-src}" python3 -m ai_scout init-local "$@"
