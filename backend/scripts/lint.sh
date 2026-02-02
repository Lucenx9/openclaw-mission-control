#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

. .venv/bin/activate

python -m black .
python -m isort .
python -m flake8 .
