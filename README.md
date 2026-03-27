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
- **HTTP port**: `7860`

### Deploy

1. Create a RunPod GPU pod with the requirements above
2. SSH into the pod
3. Run:

```bash
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/master/setup_runpod.sh | bash
```

4. Open HTTP port `7860` from RunPod to access the Gradio Web UI

That's it. The script automatically:
- Installs system dependencies and Python 3.12
- Detects your CUDA version and installs matching PyTorch
- Clones this repo and installs all dependencies
- Downloads all model checkpoints (~15 GB):
  - SAM-3 (from `jetjodh/sam3`)
  - SAM-3D-Body (from `jetjodh/sam-3d-body-dinov3`)
  - MoGe-2 (from `Ruicheng/moge-2-vitl-normal`)
  - Diffusion-VAS (from `kaihuac/diffusion-vas-*`)
  - Depth Anything V2
- Generates config and launches Gradio on port 7860

### Re-running after pod restart

If your volume disk still has the checkpoints from a previous run, the script skips downloads and just launches — takes under 2 minutes.

```bash
curl -sL https://raw.githubusercontent.com/HamzaFarooqArif/sam-body4d/master/setup_runpod.sh | bash
```


## Updating Code

To customize the app, edit code locally and push to this repo:

```bash
git clone https://github.com/HamzaFarooqArif/sam-body4d.git
cd sam-body4d
# make your changes...
git add . && git commit -m "your changes" && git push
```

On the pod, pull the latest and restart:

```bash
cd /workspace/sam-body4d && git pull
# restart the app
```

No need to re-download models or reinstall dependencies.


## Local Installation

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
