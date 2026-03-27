"""Generate body4d.yaml config with correct checkpoint paths for Docker."""

import os

CKPT_ROOT = os.environ.get("CKPT_ROOT", "/app/checkpoints")
CODE_DIR = os.environ.get("CODE_DIR", "/app/code")
CONFIG_PATH = os.path.join(CODE_DIR, "configs", "body4d.yaml")

config = f"""# ============================================================================
# Configuration for SAM-Body4D (Docker / RunPod)
# Auto-generated — do not edit manually
# ============================================================================

paths:
  ckpt_root: "{CKPT_ROOT}"

sam3:
  ckpt_path: ${{paths.ckpt_root}}/sam3/sam3.pt

sam_3d_body:
  ckpt_path: ${{paths.ckpt_root}}/sam-3d-body-dinov3/model.ckpt
  mhr_path: ${{paths.ckpt_root}}/sam-3d-body-dinov3/assets/mhr_model.pt
  fov_path: ${{paths.ckpt_root}}/moge-2-vitl-normal/model.pt
  batch_size: 64
  detector_path: ""
  segmentor_path: ""

runtime:
  output_dir: {CODE_DIR}/outputs

completion:
  enable: true
  detection_resolution: [256, 512]
  completion_resolution: [512, 1024]
  model_path_mask: ${{paths.ckpt_root}}/diffusion-vas-amodal-segmentation
  model_path_rgb:  ${{paths.ckpt_root}}/diffusion-vas-content-completion
  model_path_depth: ${{paths.ckpt_root}}/depth_anything_v2_vitl.pth
  depth_encoder: vitl
  max_occ_len: 25
"""

os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
with open(CONFIG_PATH, "w") as f:
    f.write(config)

print(f"[OK] Config written to {CONFIG_PATH}")
print(f"     Checkpoint root: {CKPT_ROOT}")
