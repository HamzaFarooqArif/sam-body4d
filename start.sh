#!/bin/bash
# ============================================================================
# Pod Start Command — runs on every pod start
# Fixes broken venv if needed, then launches server
# ============================================================================

VENV="/workspace/venv"
REPO="/workspace/sam-body4d"

# Check if venv python works
if "${VENV}/bin/python" --version &> /dev/null && "${VENV}/bin/python" -c "import torch; import fastapi" &> /dev/null; then
    # Everything works — just pull latest code and start
    echo "[start.sh] Venv OK. Pulling latest code and starting server..."
    cd "${REPO}" && git pull -q 2>/dev/null
    source "${VENV}/bin/activate"
    export PYOPENGL_PLATFORM=egl
    exec python server.py
else
    # Venv broken or missing — run full setup
    echo "[start.sh] Venv broken or missing. Running full setup..."
    rm -rf "${VENV}"
    curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/feature/angular-frontend/setup_runpod.sh | GITHUB_BRANCH=feature/angular-frontend bash
fi
