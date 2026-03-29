# SAM-Body4D — Angular Frontend

This branch (`feature/angular-frontend`) serves the Angular + Material UI frontend from the pod. Single port deployment.

For project introduction, architecture, and workflow details, see the [`feature/frontend-backend-split`](https://github.com/HamzaFarooqArif/sam-body4d/tree/feature/frontend-backend-split) branch.


## RunPod Deployment

### Requirements
- **GPU**: 48 GB+ VRAM (A40, A6000, RTX 6000 Ada)
- **RunPod template**: `runpod/pytorch`
- **Container disk**: 20 GB+
- **Volume disk**: 50 GB
- **HTTP port**: `7860`

### First-time Setup
```bash
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/feature/angular-frontend/setup_runpod.sh | GITHUB_BRANCH=feature/angular-frontend bash
```

### After Pod Restart
```bash
bash /workspace/sam-body4d/start.sh
```

### Auto-start (Optional)
Set as pod **Start Command**:
```bash
bash -c "cd /workspace/sam-body4d && git pull; bash /workspace/sam-body4d/start.sh"
```

### Access
Open HTTP port **7860** from RunPod. Everything served on one port:
- `/` — Angular UI
- `/api/*` — Backend API


## Local Angular Development

### Setup
```bash
cd angular-frontend
npm install
```

### Run with proxy to pod
Edit `proxy.conf.json` — set target to your pod URL:
```json
{ "/api": { "target": "https://your-pod-7860.proxy.runpod.net/", "secure": false, "changeOrigin": true } }
```
```bash
npx ng serve --proxy-config proxy.conf.json
```

Or leave proxy empty and paste the pod URL in the **DEV toolbar** input field.

### Rebuild and deploy
```bash
npx ng build --configuration=production
cp -r dist/angular-frontend/browser ../static
git add static/ && git commit -m "rebuild frontend" && git push
```

On pod:
```bash
cd /workspace/sam-body4d && git fetch origin feature/angular-frontend && git reset --hard FETCH_HEAD
pkill -9 -f server.py
source /workspace/venv/bin/activate && export PYOPENGL_PLATFORM=egl && nohup python server.py > /workspace/server.log 2>&1 &
```


## Project Structure

```
sam-body4d/
├── server.py              — single entry point (UI + API on :7860)
├── start.sh               — pod auto-start
├── setup_runpod.sh        — first-time setup
├── static/                — pre-built Angular app
├── angular-frontend/      — Angular source (for development)
│   ├── src/app/
│   │   ├── services/      — ApiService, SessionService, FrameExtractorService
│   │   └── components/    — VideoUpload, FrameViewer, Controls, Results
│   └── proxy.conf.json    — dev proxy config
├── backend/
│   └── pipeline.py        — model loading + processing
├── models/                — SAM-3, SAM-3D-Body, Diffusion-VAS
├── utils/
├── configs/
└── scripts/
```
