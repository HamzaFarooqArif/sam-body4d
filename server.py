"""
server.py — Single entry point for RunPod pod.

Loads models once, serves:
  - Gradio Web UI on port 7860 (for users)
  - FastAPI API on port 8000 (for local_ui.py development)

Usage:
  python server.py
  python server.py --config /path/to/body4d.yaml
"""

import os
import sys
import argparse
import shutil
import tempfile
import zipfile
from datetime import datetime
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ["GRADIO_TEMP_DIR"] = os.path.join(ROOT, "gradio_tmp")
sys.path.append(os.path.join(ROOT, 'models', 'sam_3d_body'))
sys.path.append(os.path.join(ROOT, 'models', 'diffusion_vas'))

import uvicorn
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse

from backend.pipeline import Pipeline
from frontend.ui import build_ui


def _gen_id():
    t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    u = uuid.uuid4().hex[:8]
    return f"{t}_{u}"


def create_app(config_path: str = None):
    # ---- Load pipeline (models into GPU) ----
    print("Loading models...")
    pipeline = Pipeline(config_path)
    print("Models loaded. Starting server...")

    # ---- FastAPI (API on port 8000) ----
    api = FastAPI(title="SAM-Body4D API")

    @api.get("/health")
    def health():
        return {"status": "ready"}

    @api.post("/process")
    async def process_video(video: UploadFile = File(...)):
        """
        End-to-end processing: upload video -> get results zip.
        Returns a zip file containing rendered video + meshes.
        """
        # Save uploaded video to temp file
        suffix = os.path.splitext(video.filename)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await video.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            output_dir = os.path.join(ROOT, "outputs", _gen_id())
            results = pipeline.process_video_auto(tmp_path, output_dir)

            # Create zip of results
            zip_path = f"{output_dir}/results.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                if results.get('result_video') and os.path.exists(results['result_video']):
                    zf.write(results['result_video'], "rendered_video.mp4")
                if results.get('mask_video') and os.path.exists(results['mask_video']):
                    zf.write(results['mask_video'], "mask_video.mp4")
                mesh_dir = results.get('mesh_dir', '')
                if os.path.isdir(mesh_dir):
                    for dirpath, dirnames, filenames in os.walk(mesh_dir):
                        for f in filenames:
                            full = os.path.join(dirpath, f)
                            arcname = os.path.join("meshes", os.path.relpath(full, mesh_dir))
                            zf.write(full, arcname)

            return FileResponse(zip_path, media_type="application/zip", filename="sam_body4d_results.zip")

        finally:
            os.unlink(tmp_path)

    @api.post("/generate_masks")
    async def generate_masks_endpoint(video: UploadFile = File(...)):
        """Run only mask generation (SAM-3 segmentation)."""
        suffix = os.path.splitext(video.filename)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await video.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            output_dir = os.path.join(ROOT, "outputs", _gen_id())
            os.makedirs(output_dir, exist_ok=True)

            # Auto-detect and init
            import numpy as np
            image = pipeline.read_frame_at(tmp_path, 0)
            width, height = image.size
            runtime = pipeline.init_video_state(tmp_path)

            for idx in range(10, 100):
                frame = np.array(pipeline.read_frame_at(tmp_path, idx))
                outputs = pipeline.sam3_3d_body_model.process_one_image(frame, bbox_thr=0.6)
                if len(outputs) > 0:
                    break

            for obj_id, output in enumerate(outputs):
                xmin, ymin, xmax, ymax = output['bbox']
                rel_box = np.array([[xmin / width, ymin / height, xmax / width, ymax / height]], dtype=np.float32)
                _, runtime['out_obj_ids'], _, _ = pipeline.predictor.add_new_points_or_box(
                    inference_state=runtime['inference_state'],
                    frame_idx=idx,
                    obj_id=obj_id + 1,
                    box=rel_box,
                )

            mask_video = pipeline.generate_masks(runtime, output_dir)
            return FileResponse(mask_video, media_type="video/mp4", filename="mask_video.mp4")

        finally:
            os.unlink(tmp_path)

    # ---- Gradio UI (on port 7860 via same process) ----
    demo = build_ui(pipeline)

    return api, demo


def main():
    parser = argparse.ArgumentParser(description="SAM-Body4D Server")
    parser.add_argument("--config", type=str, default=None, help="Path to body4d.yaml")
    parser.add_argument("--ui-port", type=int, default=7860, help="Gradio UI port")
    parser.add_argument("--api-port", type=int, default=8000, help="API port")
    args = parser.parse_args()

    api, demo = create_app(args.config)

    # Start Gradio in a separate thread
    import threading
    gradio_thread = threading.Thread(
        target=lambda: demo.launch(
            server_name="0.0.0.0",
            server_port=args.ui_port,
            share=False,
            prevent_thread_lock=True,
        ),
        daemon=True,
    )
    gradio_thread.start()
    print(f"Gradio UI starting on port {args.ui_port}...")

    # Start FastAPI (blocks main thread)
    print(f"API starting on port {args.api_port}...")
    uvicorn.run(api, host="0.0.0.0", port=args.api_port)


if __name__ == "__main__":
    main()