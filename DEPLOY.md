# SAM-Body4D — Deployment & Development Guide

## Architecture

```
Pod (server.py)                    Your PC (local_ui.py)
+---------------------------+      +---------------------------+
| Gradio UI    :7860        |      | --mock   (free, fake data)|
| API          :8000        |      | --api URL (real results)  |
| Models loaded once in GPU |      | No GPU needed             |
+---------------------------+      +---------------------------+
```

## Quick Start — RunPod (Recommended)

### Requirements
- GPU: 48 GB+ VRAM (A40, A6000, RTX 6000 Ada)
- RunPod template: `runpod/pytorch`
- Container disk: 20 GB+
- Volume disk: 50 GB
- HTTP ports: `7860, 8000`

### Deploy
```bash
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/master/setup_runpod.sh | bash
```

This starts `server.py` which serves:
- **Port 7860** — Gradio Web UI (for users)
- **Port 8000** — API (for local development)

---

## Development Modes

### Mode 1: Free local dev (mock)
No pod needed. Fake data, instant results.
```bash
python local_ui.py --mock
```

### Mode 2: Local dev with real results
Pod running `server.py`. Your PC talks to it.
```bash
python local_ui.py --api https://pod-url:8000
```

### Mode 3: Production
Pod runs everything. Users access Gradio on port 7860.
```bash
# On pod (via setup_runpod.sh or manually):
python server.py
```

### Deploying code changes
```bash
# On your PC:
git push

# On pod:
cd /workspace/sam-body4d && git pull
# Restart server.py
```

---

## Docker (Alternative)

### Build & Run
```bash
docker build -t sam-body4d .
docker run --gpus all -p 7860:7860 -p 8000:8000 -v $(pwd)/outputs:/app/outputs sam-body4d
```

Or with docker-compose:
```bash
docker-compose up --build
```

### Push to Docker Hub
```bash
docker tag sam-body4d YOUR_USERNAME/sam-body4d:latest
docker push YOUR_USERNAME/sam-body4d:latest
```

### RunPod Template (Docker)
- Container Image: `YOUR_USERNAME/sam-body4d:latest`
- Container Disk: 50 GB
- Volume Disk: 20 GB
- Expose HTTP Ports: `7860, 8000`

---

## Troubleshooting

### Out of Memory (RAM)
- Reduce `batch_size` in `configs/body4d.yaml`
- Use shorter videos
- Use a pod with more RAM

### Out of VRAM
- Use GPU with 48 GB+ VRAM
- Disable occlusion recovery: set `completion.enable: false` in config

### Slow Startup
- First launch loads all models (~2-3 min)
- Subsequent requests are fast

---

## Resource Usage

| Resource | Usage |
|----------|-------|
| GPU VRAM | ~28 GB peak |
| System RAM | ~25 GB |
| Disk (checkpoints) | ~15 GB |
| Processing time | ~6 min per video |
