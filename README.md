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


## Quick Start — RunPod (One Command)

Deploy on a RunPod GPU pod with a single command. No HuggingFace token needed — uses freely accessible community model mirrors.

### Requirements

- **GPU**: 48 GB+ VRAM (A40, A6000, RTX 6000 Ada)
- **RunPod template**: `runpod/pytorch` (any version)
- **Container disk**: 20 GB+
- **Volume disk**: 50 GB (mounted at `/workspace`)
- **HTTP ports**: `7860, 8000`

### Deploy

1. Create a RunPod GPU pod with the requirements above
2. SSH into the pod
3. Run:

```bash
# master branch (original all-in-one app.py)
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/master/setup_runpod.sh | bash

# feature branch (frontend/backend split with API)
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/feature/frontend-backend-split/setup_runpod.sh | GITHUB_BRANCH=feature/frontend-backend-split bash
```

4. Open HTTP port `7860` (Web UI) and `8000` (API) from RunPod

The script automatically:
- Installs system dependencies and Python 3.12
- Detects your CUDA version and installs matching PyTorch
- Clones this repo and installs all dependencies
- Downloads all model checkpoints (~15 GB) from community mirrors (no HuggingFace token needed)
- Starts `server.py` which serves Gradio UI on `:7860` and API on `:8000`

### Re-running after pod restart

If your volume disk still has checkpoints from a previous run, the script skips downloads and launches in under 2 minutes.

```bash
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/master/setup_runpod.sh | bash
```


## Architecture

The project is split into frontend and backend for flexible development:

```
server.py (pod entry point)
├── backend/pipeline.py    — model loading + processing (GPU)
├── frontend/ui.py         — Gradio UI (no model imports)
├── Gradio UI on :7860     — for users
└── FastAPI on :8000       — for local development
```

### Entry Points

| File | Where | What it does |
|------|-------|-------------|
| `server.py` | Pod | Loads models once, serves UI (:7860) + API (:8000) |
| `local_ui.py --mock` | Your PC | Free dev with fake data, no GPU needed |
| `local_ui.py --api URL` | Your PC | Local UI talking to pod API for real results |
| `app.py` | Anywhere | Original all-in-one (unchanged, still works) |


## Development

### Mode 1: Free local dev (no pod, no cost)
```bash
python local_ui.py --mock
```
Runs the full UI with fake model outputs. Use this to iterate on UI changes, video preprocessing, output formatting, etc.

### Mode 2: Local dev with real results (pod running)
```bash
python local_ui.py --api https://pod-url:8000
```
Your local UI sends videos to the pod's API and gets real 3D results back.

### Mode 3: Production (pod serves everything)
Pod runs `server.py` via the setup script. Users access Gradio on `:7860`. You can simultaneously develop against `:8000`.

### Deploying code changes
```bash
# On your PC — push changes
git push

# On pod — pull and restart
cd /workspace/sam-body4d && git pull
# restart server.py
```

No need to re-download models or reinstall dependencies.


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


## Local Installation (without Docker or RunPod)

#### 1. Create and Activate Environment
```bash
conda create -n body4d python=3.12 -y
conda activate body4d
```

#### 2. Install PyTorch, Detectron2, and SAM3
```bash
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu126
pip install 'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' --no-build-isolation --no-deps
pip install -e models/sam3
```
Choose the PyTorch CUDA version matching your system: https://pytorch.org/get-started/previous-versions/

#### 3. Install Dependencies
```bash
pip install -e .
pip install fastapi uvicorn python-multipart
```

#### 4. Download Checkpoints

```bash
python scripts/setup.py --ckpt-root /path/to/checkpoints
```

Or download manually and place under your checkpoint root:

```
checkpoints/
├── sam3/
│   └── sam3.pt
├── sam-3d-body-dinov3/
│   ├── model.ckpt
│   ├── model_config.yaml
│   └── assets/
│       └── mhr_model.pt
├── moge-2-vitl-normal/
│   └── model.pt
├── diffusion-vas-amodal-segmentation/
├── diffusion-vas-content-completion/
└── depth_anything_v2_vitl.pth
```

#### 5. Run
```bash
# Full server (Gradio + API)
python server.py

# Or original all-in-one
python app.py
```

## Batch Processing

Run the full pipeline on a video without the UI:

```bash
python scripts/offline_app.py --input_video <path>
```

Input can be a directory of frames or an `.mp4` file. The pipeline auto-detects humans and performs 4D reconstruction.


## Resource Usage

| Resource | Usage |
|----------|-------|
| GPU VRAM | ~28 GB peak |
| System RAM | ~25 GB |
| Disk (checkpoints) | ~15 GB |
| Processing time | ~6 min per video |

For detailed profiling, see [resources.md](assets/doc/resources.md).


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
