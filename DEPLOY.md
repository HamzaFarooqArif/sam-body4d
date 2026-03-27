# SAM-Body4D — Docker & RunPod Deployment Guide

## Overview

This setup packages SAM-Body4D into a Docker container with:
- All model checkpoints baked in (~15GB image)
- Gradio web UI on port 7860
- GPU support (CUDA 11.8)
- No HuggingFace token needed (uses community mirrors)

---

## Option 1: Run Locally with Docker

### Prerequisites
- Docker with NVIDIA Container Toolkit (`nvidia-docker`)
- GPU with 24GB+ VRAM (A5000, A6000, A100, RTX 4090)

### Build & Run

```bash
# Build the image (takes 20-40 min, downloads ~15GB of models)
docker build -t sam-body4d .

# Run
docker run --gpus all -p 7860:7860 -v $(pwd)/outputs:/app/outputs sam-body4d
```

Or with docker-compose:

```bash
docker-compose up --build
```

Open http://localhost:7860 in your browser.

---

## Option 2: Deploy on RunPod (GPU Pod)

### Step 1: Push image to Docker Hub

```bash
# Build
docker build -t sam-body4d .

# Tag for Docker Hub (replace YOUR_USERNAME)
docker tag sam-body4d YOUR_USERNAME/sam-body4d:latest

# Push
docker push YOUR_USERNAME/sam-body4d:latest
```

### Step 2: Create RunPod Template

1. Go to https://www.runpod.io/console/user/templates
2. Click **"New Template"**
3. Fill in:
   - **Template Name**: SAM-Body4D
   - **Container Image**: `YOUR_USERNAME/sam-body4d:latest`
   - **Container Disk**: 50 GB (models are baked in)
   - **Volume Disk**: 20 GB (for outputs)
   - **Volume Mount Path**: `/app/outputs`
   - **Expose HTTP Ports**: `7860`
   - **Docker Command**: (leave empty — uses default CMD)
4. Click **Save**

### Step 3: Launch GPU Pod

1. Go to https://www.runpod.io/console/gpu-cloud
2. Click **"Deploy"** on a GPU with 24GB+ VRAM:
   - **A5000 (24GB)** — minimum, may be tight
   - **A6000 (48GB)** — recommended
   - **A100 (80GB)** — fastest
3. Select your **"SAM-Body4D"** template
4. Click **"Deploy On-Demand"** (or Spot for cheaper)
5. Once running, click **"Connect"** → **"HTTP Service [Port 7860]"**

### Step 4: Use the Web UI

1. The Gradio interface will load in your browser
2. Upload a video (MP4)
3. The system auto-detects humans in the first frame
4. Click through the steps to generate masks and 4D meshes
5. Download results from the output panel

---

## Option 3: RunPod Serverless (pay-per-request)

For serverless deployment, use the `scripts/offline_app.py` script instead.
This is more complex to set up — see RunPod serverless docs for handler setup.
The GPU Pod approach above is simpler and recommended for most users.

---

## Troubleshooting

### Out of Memory
- Reduce `batch_size` in `configs/body4d.yaml` (default: 64)
- Use a GPU with more VRAM
- Try shorter videos

### Slow Startup
- First launch loads all models into GPU memory (~2-3 min)
- Subsequent requests are fast

### Missing Checkpoints
- The Dockerfile downloads all models during build
- If a download fails, rebuild: `docker build --no-cache -t sam-body4d .`

### Gradio Not Accessible
- Ensure port 7860 is exposed in RunPod template
- Check pod logs for startup errors

---

## GPU Memory Requirements

| Component          | VRAM Usage (approx) |
|--------------------|---------------------|
| SAM-3              | ~4 GB               |
| SAM-3D-Body        | ~6 GB               |
| Diffusion-VAS      | ~8 GB               |
| MoGe-2 + Depth     | ~3 GB               |
| **Total peak**     | **~20-24 GB**       |

A6000 (48GB) is recommended for comfortable headroom.
