#!/bin/bash
# ============================================================================
# SAM-Body4D — One-click RunPod Setup
# ============================================================================
# Usage: On a fresh RunPod GPU pod (A40/A6000/RTX 6000 Ada, 48GB+ VRAM)
#   with runpod/pytorch template and 50GB+ volume disk:
#
#   curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/master/setup_runpod.sh | bash
#
# Or if already cloned:
#   bash setup_runpod.sh
# ============================================================================
set -e

echo "============================================"
echo "  SAM-Body4D — RunPod Auto Setup"
echo "============================================"
echo ""

WORKSPACE="/workspace"
VENV="${WORKSPACE}/venv"
CKPT="${WORKSPACE}/checkpoints"
REPO="${WORKSPACE}/sam-body4d"

# ---- Step 1: System dependencies ----
echo "[1/6] Installing system dependencies..."
apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    libegl1-mesa-dev libgles2-mesa-dev libglfw3 libglfw3-dev \
    libosmesa6-dev > /dev/null 2>&1
echo "[OK]  System dependencies installed"

# ---- Step 2: Python 3.12 + venv ----
echo "[2/6] Setting up Python 3.12..."
# Always ensure Python 3.12 is installed (container disk gets wiped on restart)
if ! command -v python3.12 &> /dev/null; then
    apt-get install -y -qq python3.12 python3.12-venv python3.12-dev > /dev/null 2>&1
fi

# Check if venv exists AND works (python binary might be dead after restart)
if [ -f "${VENV}/bin/activate" ] && "${VENV}/bin/python" --version &> /dev/null; then
    source "${VENV}/bin/activate"
    echo "  (venv already exists, reusing)"
else
    echo "  (creating fresh venv)"
    rm -rf "${VENV}"
    python3.12 -m venv "${VENV}"
    source "${VENV}/bin/activate"
    pip install --upgrade pip setuptools wheel -q
fi
echo "[OK]  Python 3.12 venv ready"

# ---- Step 3: Install PyTorch + dependencies ----
echo "[3/6] Installing PyTorch and dependencies..."

# Auto-detect system CUDA version and pick matching PyTorch
detect_cuda_index() {
    # Get CUDA version from nvidia-smi (e.g., "12.8" -> try cu126, cu124, cu121)
    local cuda_ver=$(nvidia-smi 2>/dev/null | grep "CUDA Version" | awk '{print $9}')
    local cuda_major=$(echo "$cuda_ver" | cut -d. -f1)
    local cuda_minor=$(echo "$cuda_ver" | cut -d. -f2)

    if [ -z "$cuda_major" ] || [ -z "$cuda_ver" ]; then
        echo "cpu"
    elif [ "$cuda_major" = "12" ] && [ "$cuda_minor" -ge 8 ]; then
        # CUDA 12.8+ (Blackwell: RTX 5090, etc.) — needs nightly with cu128
        echo "nightly_cu128"
    elif [ "$cuda_major" = "12" ]; then
        for idx in cu126 cu124 cu121; do
            if pip install --dry-run torch==2.7.1 --index-url "https://download.pytorch.org/whl/${idx}" -q 2>/dev/null; then
                echo "$idx"
                return
            fi
        done
        echo "cu126"
    elif [ "$cuda_major" = "11" ]; then
        echo "cu118"
    else
        echo "cu126"
    fi
}

if ! python -c "import torch; torch.cuda.is_available()" 2>/dev/null; then
    CUDA_IDX=$(detect_cuda_index)
    echo "  Detected CUDA index: ${CUDA_IDX}"
    if [ "$CUDA_IDX" = "nightly_cu128" ]; then
        echo "  Installing PyTorch nightly for Blackwell GPU..."
        pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128 -q
    else
        pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url "https://download.pytorch.org/whl/${CUDA_IDX}" -q
    fi
else
    echo "  (PyTorch already installed)"
fi

# Clone or update repo
GITHUB_BRANCH="${GITHUB_BRANCH:-master}"
if [ -d "${REPO}/.git" ]; then
    cd "${REPO}"
    git fetch origin "${GITHUB_BRANCH}" --depth 1 -q
    git checkout "${GITHUB_BRANCH}" -q 2>/dev/null || git checkout -b "${GITHUB_BRANCH}" "origin/${GITHUB_BRANCH}" -q
    git reset --hard "origin/${GITHUB_BRANCH}" -q
    echo "  (repo updated, branch: ${GITHUB_BRANCH})"
else
    git clone --depth 1 --branch "${GITHUB_BRANCH}" https://github.com/HamzaFarooqArif/sam-body4d.git "${REPO}"
    echo "  (repo cloned, branch: ${GITHUB_BRANCH})"
fi

cd "${REPO}"
pip install 'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' --no-build-isolation --no-deps -q 2>/dev/null || true
pip install -e models/sam3 -q 2>/dev/null
pip install -e . -q 2>/dev/null
pip install numpy==1.26.4 scipy scikit-learn scikit-image pyopengl trimesh -q 2>/dev/null
echo "[OK]  All Python dependencies installed"

# ---- Step 4: Download checkpoints ----
echo "[4/6] Downloading model checkpoints (if missing)..."
mkdir -p "${CKPT}"

python -c "
from huggingface_hub import hf_hub_download, snapshot_download
import os

ckpt = '${CKPT}'

# SAM-3
if not os.path.exists(f'{ckpt}/sam3/sam3.pt'):
    print('  Downloading SAM-3...')
    hf_hub_download('jetjodh/sam3', 'sam3.pt', local_dir=f'{ckpt}/sam3')
else:
    print('  SAM-3 already exists')

# SAM-3D-Body
if not os.path.exists(f'{ckpt}/sam-3d-body-dinov3/model.ckpt'):
    print('  Downloading SAM-3D-Body...')
    hf_hub_download('jetjodh/sam-3d-body-dinov3', 'model.ckpt', local_dir=f'{ckpt}/sam-3d-body-dinov3')
    hf_hub_download('jetjodh/sam-3d-body-dinov3', 'model_config.yaml', local_dir=f'{ckpt}/sam-3d-body-dinov3')
    hf_hub_download('jetjodh/sam-3d-body-dinov3', 'assets/mhr_model.pt', local_dir=f'{ckpt}/sam-3d-body-dinov3')
else:
    print('  SAM-3D-Body already exists')

# MoGe-2
if not os.path.exists(f'{ckpt}/moge-2-vitl-normal/model.pt'):
    print('  Downloading MoGe-2...')
    hf_hub_download('Ruicheng/moge-2-vitl-normal', 'model.pt', local_dir=f'{ckpt}/moge-2-vitl-normal')
else:
    print('  MoGe-2 already exists')

# Diffusion-VAS
if not os.path.exists(f'{ckpt}/diffusion-vas-amodal-segmentation/image_encoder'):
    print('  Downloading Diffusion-VAS amodal...')
    snapshot_download('kaihuac/diffusion-vas-amodal-segmentation', local_dir=f'{ckpt}/diffusion-vas-amodal-segmentation')
else:
    print('  Diffusion-VAS amodal already exists')

if not os.path.exists(f'{ckpt}/diffusion-vas-content-completion/image_encoder'):
    print('  Downloading Diffusion-VAS content...')
    snapshot_download('kaihuac/diffusion-vas-content-completion', local_dir=f'{ckpt}/diffusion-vas-content-completion')
else:
    print('  Diffusion-VAS content already exists')

# Depth Anything V2
if not os.path.exists(f'{ckpt}/depth_anything_v2_vitl.pth'):
    print('  Downloading Depth Anything V2...')
    import urllib.request
    urllib.request.urlretrieve('https://huggingface.co/depth-anything/Depth-Anything-V2-Large/resolve/main/depth_anything_v2_vitl.pth', f'{ckpt}/depth_anything_v2_vitl.pth')
else:
    print('  Depth Anything V2 already exists')

print('  All checkpoints ready!')
"
echo "[OK]  Checkpoints ready"

# ---- Step 5: Generate config ----
echo "[5/6] Generating config..."
export CKPT_ROOT="${CKPT}"
export CODE_DIR="${REPO}"
python "${REPO}/docker/generate_config.py"

# ---- Step 6: Install extra deps for server mode ----
pip install fastapi uvicorn python-multipart -q 2>/dev/null

# ---- Step 7: Launch ----
echo "[6/6] Launching server..."
echo ""
echo "============================================"
echo "  Setup complete! Server starting..."
echo "  App:  port 7860 (UI + API)"
echo "============================================"
echo ""

export PYOPENGL_PLATFORM=egl
cd "${REPO}"
exec python server.py
