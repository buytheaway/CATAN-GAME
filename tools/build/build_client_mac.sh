#!/usr/bin/env bash
set -euo pipefail
python -m PyInstaller --clean -y tools/build/CatanClient.spec
