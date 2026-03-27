#!/bin/bash
# ============================================================================
# SAM-Body4D startup script for RunPod / Docker
# ============================================================================
set -e

echo "============================================"
echo "  SAM-Body4D — Starting Gradio Web UI"
echo "============================================"
echo ""

# ---- Pull latest code from GitHub ----
GITHUB_REPO="${GITHUB_REPO:-https://github.com/HamzaFarooqArif/sam-body4d.git}"
GITHUB_BRANCH="${GITHUB_BRANCH:-master}"
CODE_DIR="/app/code"

echo "Pulling latest code from ${GITHUB_REPO} (${GITHUB_BRANCH})..."
if [ -d "${CODE_DIR}/.git" ]; then
    cd "${CODE_DIR}"
    git fetch origin "${GITHUB_BRANCH}" --depth 1
    git reset --hard "origin/${GITHUB_BRANCH}"
    echo "[OK] Code updated"
else
    git clone --depth 1 --branch "${GITHUB_BRANCH}" "${GITHUB_REPO}" "${CODE_DIR}" 2>/dev/null || \
    git clone --depth 1 "${GITHUB_REPO}" "${CODE_DIR}"
    echo "[OK] Code cloned"
fi

# Link checkpoints into the code directory
ln -sfn /app/checkpoints "${CODE_DIR}/checkpoints"

# Install/update the code package (fast — deps already in image)
cd "${CODE_DIR}"
pip install -e . --no-deps --quiet 2>/dev/null || true
pip install -e models/sam3 --no-deps --quiet 2>/dev/null || true

# ---- Generate config pointing to checkpoints ----
CKPT_ROOT="/app/checkpoints"
python "${CODE_DIR}/docker/generate_config.py"

# ---- Verify checkpoints exist ----
MISSING=0

check_file() {
    if [ ! -f "$1" ]; then
        echo "[MISSING] $1"
        MISSING=1
    else
        echo "[OK]      $1"
    fi
}

check_dir() {
    if [ ! -d "$1" ] || [ -z "$(ls -A "$1" 2>/dev/null)" ]; then
        echo "[MISSING] $1"
        MISSING=1
    else
        echo "[OK]      $1"
    fi
}

echo ""
echo "Checking model checkpoints..."
check_file "${CKPT_ROOT}/sam3/sam3.pt"
check_file "${CKPT_ROOT}/sam-3d-body-dinov3/model.ckpt"
check_file "${CKPT_ROOT}/sam-3d-body-dinov3/model_config.yaml"
check_file "${CKPT_ROOT}/sam-3d-body-dinov3/assets/mhr_model.pt"
check_file "${CKPT_ROOT}/moge-2-vitl-normal/model.pt"
check_file "${CKPT_ROOT}/depth_anything_v2_vitl.pth"
check_dir  "${CKPT_ROOT}/diffusion-vas-amodal-segmentation"
check_dir  "${CKPT_ROOT}/diffusion-vas-content-completion"
echo ""

if [ "$MISSING" -eq 1 ]; then
    echo "[WARNING] Some checkpoints are missing. The app may fail to load."
    echo ""
fi

# ---- Ensure output directory exists ----
mkdir -p "${CODE_DIR}/outputs"

# ---- Set headless rendering ----
export PYOPENGL_PLATFORM=egl

# ---- Add code paths ----
export PYTHONPATH="${CODE_DIR}:${CODE_DIR}/models/sam_3d_body:${CODE_DIR}/models/diffusion_vas:${PYTHONPATH}"

# ---- Launch Gradio ----
echo "Launching Gradio on port 7860..."
cd "${CODE_DIR}"
exec python app.py
