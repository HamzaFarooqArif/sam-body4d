# SAM-Body4D — Angular Frontend

This branch (`feature/angular-frontend`) serves an Angular + Material UI frontend with the SAM-Body4D processing backend. Single port deployment on RunPod.

For project introduction and model details, see the [`feature/frontend-backend-split`](https://github.com/HamzaFarooqArif/sam-body4d/tree/feature/frontend-backend-split) branch.


## RunPod Deployment

### Hardware Requirements
- **GPU**: 24 GB+ VRAM (minimum), 48 GB+ recommended
- **System RAM**: 62 GB+ recommended
- **RunPod template**: `runpod/pytorch` (any version)
- **Container disk**: 20 GB+
- **Volume disk**: 50 GB (persists checkpoints across stops)
- **HTTP port**: `7860`

### Tested GPUs
| GPU | VRAM | Cost/hr | Status |
|-----|------|---------|--------|
| RTX 6000 Ada | 48 GB | $0.77 | Tested, works |
| A40 | 48 GB | $0.40 | Tested, works |
| H100 | 80 GB | $2.69 | Tested, works (fastest) |
| RTX 5090 | 32 GB | $1.78 | Tested, needs PyTorch nightly (auto-detected) |

### Resource Usage
| Resource | Idle (models loaded) | Peak (processing) |
|----------|---------------------|-------------------|
| GPU VRAM | ~22 GB | ~22-28 GB |
| System RAM | ~25 GB | ~96 GB |
| Disk (checkpoints) | ~15 GB | |
| Processing (100% fps) | | ~6 min/video |
| Processing (50% fps) | | ~3 min/video |

### First-time Setup
1. Create a RunPod GPU pod with the requirements above
2. Open the web terminal and run:
```bash
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/feature/angular-frontend/setup_runpod.sh | GITHUB_BRANCH=feature/angular-frontend bash
```
This installs everything and starts the server (~10-30 min first time). Checkpoints download automatically from community mirrors (no HuggingFace token needed).

3. Open HTTP port **7860** from RunPod Connect tab

### After Pod Restart
Container disk wipes on restart (Python 3.12 lost). Run from web terminal:
```bash
bash /workspace/sam-body4d/start.sh
```
- If venv OK: pulls code, starts server (~30 sec)
- If venv broken: runs full setup (~10 min)

Checkpoints on volume disk are preserved — no re-download needed.

### Auto-start (Optional)
Set as pod **Start Command** in RunPod template:
```bash
bash -c "cd /workspace/sam-body4d && git pull; bash /workspace/sam-body4d/start.sh"
```

### Updating Code on Pod
```bash
cd /workspace/sam-body4d && git fetch origin feature/angular-frontend && git reset --hard FETCH_HEAD
pkill -9 -f server.py
source /workspace/venv/bin/activate && export PYOPENGL_PLATFORM=egl && nohup python server.py > /workspace/server.log 2>&1 &
```
Wait ~5 min for models to load. No reinstall needed for code-only changes.


## How It Works

Everything on one port:
- `pod:7860/` — Angular UI (pre-built static files)
- `pod:7860/api/*` — FastAPI backend (model processing)

### API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Server status |
| `/api/init_video` | POST | Upload video, create session |
| `/api/get_frame` | POST | Get specific frame from session |
| `/api/add_point` | POST | Add annotation point, get mask overlay |
| `/api/add_target` | POST | Finalize current target |
| `/api/session_generate_masks_async` | POST | Start mask generation (async) |
| `/api/session_generate_4d_async` | POST | Start 4D generation (async) |
| `/api/job/{id}` | GET | Poll job progress |
| `/api/job/{id}/result` | GET | Download results |
| `/api/delete_session` | POST | Clean up session, free GPU memory |
| `/api/process` | POST | One-shot: video in, results out |

### Workflow
1. Upload video or click an example (loads locally, no backend yet)
2. Adjust **Processing Range** (start/end frames) and **Frame Rate** (%)
3. Click **Apply & Upload** — trims to range, uploads to backend
4. Navigate to a frame where targets are visible
5. Click to annotate (positive/negative points)
6. Add Target for each person
7. Mask Generation — tracks targets across all frames
8. 4D Generation — recovers 3D meshes

**Notes:**
- All targets must be annotated on the same frame (SAM-3 limitation)
- Range trimming happens on frontend (browser), backend receives pre-trimmed video
- Frame rate reduction handled by backend via frame_step
- Non-MP4 uploads (e.g. WebM from trimming) auto-converted on backend via ffmpeg


## Local Angular Development

### Prerequisites
- Node.js 20+
- Angular CLI (`npm install -g @angular/cli`)

### Setup
```bash
cd angular-frontend
npm install
```

### Run locally
Edit `proxy.conf.json` to point to your pod:
```json
{ "/api": { "target": "https://your-pod-7860.proxy.runpod.net/", "secure": false, "changeOrigin": true } }
```
```bash
npx ng serve --proxy-config proxy.conf.json
```
Open http://localhost:4200. Shows **DEV** badge with URL input field for pod connection.

### Rebuild and deploy
```bash
cd angular-frontend
npx ng build --configuration=production
cp -r dist/angular-frontend/browser ../static
git add static/ && git commit -m "rebuild frontend" && git push
```
Then update the pod (see "Updating Code on Pod" above).


## Project Structure
```
sam-body4d/
├── server.py              — single entry point (UI + API on :7860)
├── start.sh               — pod auto-start (fixes broken venv)
├── setup_runpod.sh        — first-time RunPod setup
├── static/                — pre-built Angular app (committed to git)
├── angular-frontend/      — Angular source code
│   ├── src/app/
│   │   ├── services/      — ApiService, SessionService, FrameExtractorService
│   │   └── components/    — Examples, VideoUpload, FrameViewer, Controls, Results
│   ├── public/examples/   — example videos + thumbnails
│   └── proxy.conf.json    — dev proxy config
├── backend/
│   └── pipeline.py        — model loading + processing logic
├── models/
│   ├── sam3/              — SAM-3 video segmentation
│   ├── sam_3d_body/       — SAM-3D-Body mesh recovery
│   └── diffusion_vas/     — Diffusion-VAS occlusion recovery
├── utils/                 — helper functions
├── configs/               — model config (auto-generated)
├── scripts/               — batch processing
├── docker/                — Docker support (alternative deployment)
├── Dockerfile
└── docker-compose.yml
```
