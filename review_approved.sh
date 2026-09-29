#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VISION_PYTHON="${VISION_PYTHON:-/home/waky/.venvs/vision/bin/python}"

export PYTHONPATH="$PROJECT_DIR/vendor:$PROJECT_DIR${PYTHONPATH:+:$PYTHONPATH}"
cd "$PROJECT_DIR"
exec "$VISION_PYTHON" -m auto_labeller.approved_review_app
