# ============================================================================
# SAM-Body4D Docker Image for RunPod (GPU Pod with Gradio Web UI)
# ============================================================================
# Build:
#   docker build -t sam-body4d .
#
# Run locally:
#   docker run --gpus all -p 7860:7860 sam-body4d
#
# RunPod: Deploy as GPU Pod template, expose HTTP port 7860
# ============================================================================

FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Disable HuggingFace cache to avoid duplicate files
ENV HF_HUB_DISABLE_SYMLINKS_WARNING=1

# ---- System dependencies ----
# Python 3.12 PPA (Ubuntu 22.04 ships 3.10 by default)
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev \
    git wget curl \
    ffmpeg \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxrender1 libxext6 \
    libegl1-mesa-dev libgles2-mesa-dev \
    libglfw3 libglfw3-dev \
    libosmesa6-dev \
    build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

# Make python3.12 the default and install pip for it
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

# Upgrade pip
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# ---- Set working directory ----
WORKDIR /app

# ---- Install PyTorch (CUDA 11.8) ----
RUN pip install --no-cache-dir \
    torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
    --index-url https://download.pytorch.org/whl/cu118

# ---- Install Detectron2 ----
RUN pip install --no-cache-dir \
    'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' \
    --no-build-isolation --no-deps

# ---- Copy project files ----
COPY . /app/

# ---- Install SAM3 subpackage ----
RUN pip install --no-cache-dir -e models/sam3

# ---- Install project + all dependencies ----
RUN pip install --no-cache-dir -e .

# ---- Install additional deps that may be missing ----
RUN pip install --no-cache-dir \
    scipy \
    scikit-learn \
    scikit-image \
    huggingface_hub \
    pyopengl \
    trimesh

# ---- Set up headless rendering for pyrender ----
ENV PYOPENGL_PLATFORM=egl
ENV CKPT_ROOT=/app/checkpoints

# ---- Download model checkpoints ----
# All downloads use community mirrors or public repos (no HF token needed)
# Each step cleans the HF cache to avoid storing duplicate files

# 1. SAM-3 (community mirror)
RUN python -c "\
from huggingface_hub import hf_hub_download; \
hf_hub_download('jetjodh/sam3', 'sam3.pt', local_dir='/app/checkpoints/sam3')" \
    && rm -rf /root/.cache/huggingface \
    && echo '[OK] SAM-3 downloaded'

# 2. SAM-3D-Body (community mirror)
RUN python -c "\
from huggingface_hub import hf_hub_download; \
hf_hub_download('jetjodh/sam-3d-body-dinov3', 'model.ckpt', local_dir='/app/checkpoints/sam-3d-body-dinov3'); \
hf_hub_download('jetjodh/sam-3d-body-dinov3', 'model_config.yaml', local_dir='/app/checkpoints/sam-3d-body-dinov3'); \
hf_hub_download('jetjodh/sam-3d-body-dinov3', 'assets/mhr_model.pt', local_dir='/app/checkpoints/sam-3d-body-dinov3')" \
    && rm -rf /root/.cache/huggingface \
    && echo '[OK] SAM-3D-Body downloaded'

# 3. MoGe-2 (public)
RUN python -c "\
from huggingface_hub import hf_hub_download; \
hf_hub_download('Ruicheng/moge-2-vitl-normal', 'model.pt', local_dir='/app/checkpoints/moge-2-vitl-normal')" \
    && rm -rf /root/.cache/huggingface \
    && echo '[OK] MoGe-2 downloaded'

# 4. Diffusion-VAS (public)
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('kaihuac/diffusion-vas-amodal-segmentation', local_dir='/app/checkpoints/diffusion-vas-amodal-segmentation'); \
snapshot_download('kaihuac/diffusion-vas-content-completion', local_dir='/app/checkpoints/diffusion-vas-content-completion')" \
    && rm -rf /root/.cache/huggingface \
    && echo '[OK] Diffusion-VAS downloaded'

# 5. Depth Anything V2 (direct download, no HF cache)
RUN wget -q -O /app/checkpoints/depth_anything_v2_vitl.pth \
    "https://huggingface.co/depth-anything/Depth-Anything-V2-Large/resolve/main/depth_anything_v2_vitl.pth" \
    && echo '[OK] Depth Anything V2 downloaded'

# ---- Generate config pointing to baked-in checkpoints ----
RUN python /app/docker/generate_config.py

# ---- Create output directory ----
RUN mkdir -p /app/outputs

# ---- Expose Gradio port ----
EXPOSE 7860

# ---- Startup ----
RUN chmod +x /app/docker/start.sh

CMD ["/app/docker/start.sh"]
