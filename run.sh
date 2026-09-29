#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${VISION_PYTHON:-}" ]]; then
  if [[ -x /home/waky/.venvs/vision/bin/python ]]; then
    VISION_PYTHON=/home/waky/.venvs/vision/bin/python
  else
    VISION_PYTHON="$(command -v python3)"
  fi
fi

if [[ -d "$PROJECT_DIR/vendor" ]]; then
  export PYTHONPATH="$PROJECT_DIR/vendor${PYTHONPATH:+:$PYTHONPATH}"
fi
export PYTHONPATH="$PROJECT_DIR${PYTHONPATH:+:$PYTHONPATH}"

if ! "$VISION_PYTHON" -c "import cv2, numpy, ultralytics" >/dev/null 2>&1; then
  echo "$VISION_PYTHON ortamında cv2/numpy/ultralytics eksik. README içindeki kurulum adımlarına bakın." >&2
  exit 1
fi

mkdir -p "$PROJECT_DIR/.runtime/ultralytics"
export YOLO_CONFIG_DIR="$PROJECT_DIR/.runtime/ultralytics"
cd "$PROJECT_DIR"
exec "$VISION_PYTHON" -m auto_labeller.server
