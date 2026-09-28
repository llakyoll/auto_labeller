#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VISION_PYTHON="${VISION_PYTHON:-/home/waky/.venvs/vision/bin/python}"

if [[ ! -d "$PROJECT_DIR/vendor/cv2" ]]; then
  echo "Proje OpenCV kurulumu eksik. README içindeki kurulum komutunu çalıştırın." >&2
  exit 1
fi

mkdir -p "$PROJECT_DIR/.runtime/ultralytics"
export PYTHONPATH="$PROJECT_DIR/vendor:$PROJECT_DIR${PYTHONPATH:+:$PYTHONPATH}"
export YOLO_CONFIG_DIR="$PROJECT_DIR/.runtime/ultralytics"
cd "$PROJECT_DIR"
exec "$VISION_PYTHON" -m auto_labeller.server
