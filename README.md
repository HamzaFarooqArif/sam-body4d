<!-- <h1 align="center">SAM-Body4D</h1> -->

# SAM-Body4D

Based on [**SAM-Body4D**](https://github.com/gaomingqi/sam-body4d) by [Mingqi Gao](https://mingqigao.com), [Yunqi Miao](https://yoqim.github.io/), [Jungong Han](https://jungonghan.github.io/)

**SAM-Body4D** is a **training-free** method for **temporally consistent** and **robust** 4D human mesh recovery from videos.
By leveraging **pixel-level human continuity** from promptable video segmentation **together with occlusion recovery**, it reliably preserves identity and full-body geometry in challenging in-the-wild scenes.

[ Paper](https://arxiv.org/pdf/2512.08406) | [ Project Page](https://mingqigao.com/projects/sam-body4d/index.html) | [ Original Repo](https://github.com/gaomingqi/sam-body4d)


## Key Features

- **Temporally consistent human meshes across the entire video**
- **Robust multi-human recovery under heavy occlusions**
- **Robust 4D reconstruction under camera motion**
- **Adjustable frame rate** — trade quality for speed
- **Frontend/backend split** — develop UI locally for free, process on cloud GPU
- **Async processing** — progress tracking, no timeouts
- **One-command cloud deployment** on RunPod


## Quick Start — RunPod

### Requirements

- **GPU**: 48 GB+ VRAM (A40, A6000, RTX 6000 Ada)
- **RunPod template**: `runpod/pytorch` (any version)
- **Container disk**: 20 GB+
- **Volume disk**: 50 GB (mounted at `/workspace`)
- **HTTP ports**: `7860, 8000`

### First-time Setup

1. Create a RunPod GPU pod with the requirements above
2. Open the web terminal and run:

```bash
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/feature/frontend-backend-split/setup_runpod.sh | GITHUB_BRANCH=feature/frontend-backend-split bash
```

This automatically installs everything and starts the server (~10-30 min first time).

### After Pod Restart

The venv breaks on restart (container disk wipes Python 3.12). Run from the web terminal:

```bash
bash /workspace/sam-body4d/start.sh
```

If venv is OK: pulls code, starts server (~30 sec).
If venv is broken: runs full setup, then starts server (~10 min).

### Auto-start (Optional)

Set this as the pod's **Start Command** in RunPod template:

```bash
bash -c "cd /workspace/sam-body4d && git pull; bash /workspace/sam-body4d/start.sh"
```


## Architecture

```
server.py (pod entry point — one process, one GPU load)
├── backend/pipeline.py    — model loading + video processing
├── backend/mock.py        — fake pipeline for free local dev
├── frontend/ui.py         — Gradio UI (shared by all modes)
├── Gradio UI on :7860     — for users
└── FastAPI API on :8000   — for local development
    ├── POST /init_video           — upload video, create session
    ├── POST /add_point            — annotate, get real mask overlay
    ├── POST /add_target           — finalize annotation target
    ├── POST /session_generate_masks_async  — start mask generation (async)
    ├── POST /session_generate_4d_async     — start 4D generation (async)
    ├── GET  /job/{id}             — poll progress (0-100%)
    ├── GET  /job/{id}/result      — download results
    ├── POST /process              — one-shot: video in, results out
    └── GET  /health               — server status
```

### Entry Points

| File | Where | What it does |
|------|-------|-------------|
| `server.py` | Pod | Loads models once, serves UI (:7860) + API (:8000) |
| `local_ui.py --mock` | Your PC | Free dev with fake data, no GPU needed |
| `local_ui.py --api URL` | Your PC | Local UI talking to pod API for real results |
| `app.py` | Anywhere | Original all-in-one (still works as fallback) |
| `start.sh` | Pod | Auto-fixes broken venv + starts server |
| `setup_runpod.sh` | Pod | Full first-time setup |


## Development Modes

### Mode 1: Free local dev (no pod, no cost)
```bash
cd sam-body4d
python local_ui.py --mock
```
Full UI with fake model outputs. Iterate on UI changes, video preprocessing, frame rate control — all free, no GPU needed.

### Mode 2: Local dev with real results (pod running)
```bash
python local_ui.py --api https://your-pod-id-8000.proxy.runpod.net
```
Your local UI sends clicks and videos to the pod. Real SAM-3 masks, real 4D meshes. Uses async polling — no Cloudflare timeout issues.

### Mode 3: Production (pod serves everything)
Pod runs `server.py` via the setup script. Users access Gradio on `:7860`. You can simultaneously develop against `:8000` from your PC.

### Deploying code changes
```bash
# On your PC
git push

# On pod (server keeps running, no reinstall needed)
cd /workspace/sam-body4d && git pull
pkill -9 -f server.py
source /workspace/venv/bin/activate && export PYOPENGL_PLATFORM=egl && nohup python server.py > /workspace/server.log 2>&1 &
```


## UI Features

- **Video upload** — drag and drop MP4
- **Frame rate slider** — adjust processing frame rate (10-100%), click Apply to preview
- **Frame navigation** — scrub through frames with slider
- **Click-to-annotate** — positive/negative points for target selection
- **Multi-target support** — annotate multiple people
- **Mask Generation** — SAM-3 video segmentation with progress bar
- **4D Generation** — full mesh recovery with adaptive progress tracking
- **Async processing** — no timeout issues, real-time progress updates


## Docker (Alternative)

```bash
docker build -t sam-body4d .
docker run --gpus all -p 7860:7860 -p 8000:8000 -v $(pwd)/outputs:/app/outputs sam-body4d
```

Or with docker-compose:
```bash
docker-compose up --build
```


## Local Installation (without Docker or RunPod)

Requires a GPU with 48 GB+ VRAM.

#### 1. Create Environment
```bash
conda create -n body4d python=3.12 -y
conda activate body4d
```

#### 2. Install PyTorch, Detectron2, SAM3
```bash
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu126
pip install 'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' --no-build-isolation --no-deps
pip install -e models/sam3
```
Choose PyTorch CUDA version matching your system: https://pytorch.org/get-started/previous-versions/

#### 3. Install Dependencies
```bash
pip install -e .
pip install fastapi uvicorn python-multipart
```

#### 4. Download Checkpoints
```bash
python scripts/setup.py --ckpt-root /path/to/checkpoints
```

Or place manually:
```
checkpoints/
├── sam3/sam3.pt
├── sam-3d-body-dinov3/
│   ├── model.ckpt
│   ├── model_config.yaml
│   └── assets/mhr_model.pt
├── moge-2-vitl-normal/model.pt
├── diffusion-vas-amodal-segmentation/
├── diffusion-vas-content-completion/
└── depth_anything_v2_vitl.pth
```

#### 5. Run
```bash
python server.py      # Gradio :7860 + API :8000
```


## Resource Usage

| Resource | Usage |
|----------|-------|
| GPU VRAM | ~28 GB peak |
| System RAM | ~25 GB |
| Disk (checkpoints) | ~15 GB |
| Processing time (100% fps) | ~6 min per video |
| Processing time (50% fps) | ~3 min per video |
| Processing time (25% fps) | ~1.5 min per video |

For detailed profiling, see [resources.md](assets/doc/resources.md).


## Project Structure

```
sam-body4d/
├── server.py              — pod entry point (Gradio + API, one process)
├── local_ui.py            — PC entry point (--mock or --api)
├── app.py                 — original all-in-one (still works)
├── start.sh               — pod auto-start script
├── setup_runpod.sh        — full first-time RunPod setup
├── backend/
│   ├── pipeline.py        — model loading + processing logic
│   └── mock.py            — fake pipeline for free local dev
├── frontend/
│   └── ui.py              — shared Gradio UI definition
├── models/
│   ├── sam3/              — SAM-3 video segmentation
│   ├── sam_3d_body/       — SAM-3D-Body mesh recovery
│   └── diffusion_vas/     — Diffusion-VAS occlusion recovery
├── utils/                 — helper functions
├── configs/               — model config files
├── scripts/               — batch processing, setup
├── docker/                — Docker support files
├── Dockerfile
└── docker-compose.yml
```


## Citation

```bibtex
@article{gao2025sambody4d,
  title   = {SAM-Body4D: Training-Free 4D Human Body Mesh Recovery from Videos},
  author  = {Gao, Mingqi and Miao, Yunqi and Han, Jungong},
  journal = {arXiv preprint arXiv:2512.08406},
  year    = {2025},
  url     = {https://arxiv.org/abs/2512.08406}
}
```

## Acknowledgements

Built upon [SAM-3](https://github.com/facebookresearch/sam3), [Diffusion-VAS](https://github.com/Kaihua-Chen/diffusion-vas) and [SAM-3D-Body](https://github.com/facebookresearch/sam-3d-body). Community model mirrors by [jetjodh](https://huggingface.co/jetjodh).
