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
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/feature/angular-frontend/setup_runpod.sh | GITHUB_BRANCH=feature/angular-frontend bash
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
| `server.py` | Pod | Loads models, serves Angular UI (:7860) + API (:8000) |
| `start.sh` | Pod | Auto-fixes broken venv + starts server |
| `setup_runpod.sh` | Pod | Full first-time setup |
| `angular-frontend/` | Your PC | Angular source for local dev (`npx ng serve`) |


## Development Modes

### Mode 1: Local Angular dev (no pod needed for UI work)
```bash
cd angular-frontend
npm install
npx ng serve
```
Develop UI at http://localhost:4200. Point to pod API URL for real results, or just work on UI layout/styling without a pod.

### Mode 2: Production (pod serves everything)
Pod runs `server.py` — Angular UI on `:7860`, API on `:8000`. Users just open the pod URL.

### Deploying code changes
```bash
# Rebuild Angular
cd angular-frontend && npx ng build --configuration=production
cp -r dist/angular-frontend/browser ../static

# Commit and push
git add static/ && git commit -m "rebuild frontend" && git push

# On pod — pull and restart
cd /workspace/sam-body4d && git pull
pkill -9 -f server.py
source /workspace/venv/bin/activate && export PYOPENGL_PLATFORM=egl && nohup python server.py > /workspace/server.log 2>&1 &
```


## Angular Frontend (feature/angular-frontend branch)

A modern Angular + Material UI frontend that connects to the same backend API.

### Setup
```bash
cd angular-frontend
npm install
npx ng serve
```
Open http://localhost:4200. Enter your pod API URL in the toolbar and click the connect icon.

### Features
- **Material UI dark theme** with violet palette
- **Drag-and-drop video upload** with upload spinner
- **Local frame scrubbing** — instant frame navigation using HTML5 video + canvas (no API calls)
- **Click-to-annotate** with loading spinner, duplicate click prevention
- **Positive/negative point toggle**
- **Multi-target support** with chip display
- **Frame rate slider** with Apply — adjusts frame count and maps indices
- **Mask Generation** with Material progress bar and elapsed time
- **4D Generation** with progress bar, auto-extracts video from result zip
- **API URL persistence** in localStorage
- **Connection status indicator** in toolbar
- **Clear error messages** (e.g., "Cannot add targets after mask generation")

### Workflow
1. Upload video (uploaded to pod + loaded locally for scrubbing)
2. Navigate to frame with slider
3. Click to annotate person → Add Target (repeat for multiple people)
4. Click Mask Generation → progress bar → result video
5. Click 4D Generation → progress bar → result video with meshes

**Note:** All targets must be annotated before Mask Generation. SAM-3 does not allow adding new targets after propagation.


## Local Angular Development

To modify the Angular frontend:

```bash
cd angular-frontend
npm install
npx ng serve
```

Open http://localhost:4200. It auto-detects RunPod API URL or falls back to localhost:8000.

After changes, rebuild and copy to static/:
```bash
npx ng build --configuration=production
cp -r dist/angular-frontend/browser ../static
```

Commit the updated `static/` folder and push.


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
├── server.py              — pod entry point (Angular UI :7860 + API :8000)
├── start.sh               — pod auto-start script
├── setup_runpod.sh        — full first-time RunPod setup
├── static/                — pre-built Angular app (served on :7860)
├── angular-frontend/      — Angular source code (for development)
├── backend/
│   └── pipeline.py        — model loading + processing logic
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
