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
import base64
import io
import tempfile
import zipfile
from datetime import datetime
import uuid

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ["GRADIO_TEMP_DIR"] = os.path.join(ROOT, "gradio_tmp")
sys.path.append(os.path.join(ROOT, 'models', 'sam_3d_body'))
sys.path.append(os.path.join(ROOT, 'models', 'diffusion_vas'))

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image

from backend.pipeline import Pipeline
from frontend.ui import build_ui


def _gen_id():
    t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    u = uuid.uuid4().hex[:8]
    return f"{t}_{u}"


def _image_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def create_app(config_path: str = None):
    # ---- Load pipeline (models into GPU) ----
    print("Loading models...")
    pipeline = Pipeline(config_path)
    print("Models loaded. Starting server...")

    # ---- Session state (per-video interactive sessions) ----
    sessions = {}  # session_id -> { runtime, output_dir, video_path }

    # ---- FastAPI (API on port 8000) ----
    api = FastAPI(title="SAM-Body4D API")

    @api.get("/health")
    def health():
        return {"status": "ready"}

    # ---- Interactive session endpoints ----

    @api.post("/init_video")
    async def init_video(video: UploadFile = File(...)):
        """Upload video and initialize SAM-3 state. Returns session_id."""
        suffix = os.path.splitext(video.filename)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=os.path.join(ROOT, "outputs")) as tmp:
            content = await video.read()
            tmp.write(content)
            tmp_path = tmp.name

        runtime = pipeline.init_video_state(tmp_path)
        output_dir = os.path.join(ROOT, "outputs", _gen_id())
        os.makedirs(output_dir, exist_ok=True)

        session_id = _gen_id()
        sessions[session_id] = {
            'runtime': runtime,
            'output_dir': output_dir,
            'video_path': tmp_path,
        }

        fps, total = pipeline.read_video_metadata(tmp_path)
        first_frame = pipeline.read_frame_at(tmp_path, 0)

        return JSONResponse({
            "session_id": session_id,
            "fps": fps,
            "total_frames": total,
            "first_frame": _image_to_base64(first_frame),
            "width": first_frame.size[0],
            "height": first_frame.size[1],
        })

    @api.post("/get_frame")
    async def get_frame(session_id: str = Form(...), frame_idx: int = Form(...)):
        """Get a specific frame from the session's video."""
        session = sessions.get(session_id)
        if not session:
            return JSONResponse({"error": "Invalid session_id"}, status_code=404)
        frame = pipeline.read_frame_at(session['video_path'], frame_idx)
        if frame is None:
            return JSONResponse({"error": f"Failed to read frame {frame_idx}"}, status_code=400)
        return JSONResponse({"frame": _image_to_base64(frame)})

    @api.post("/add_point")
    async def add_point(
        session_id: str = Form(...),
        frame_idx: int = Form(...),
        x: int = Form(...),
        y: int = Form(...),
        point_type: str = Form(...),
        width: int = Form(...),
        height: int = Form(...),
    ):
        """Add annotation point and return mask overlay image."""
        session = sessions.get(session_id)
        if not session:
            return JSONResponse({"error": "Invalid session_id"}, status_code=404)

        painted, session['runtime'] = pipeline.add_point(
            session['runtime'], session['video_path'],
            frame_idx, x, y, point_type, width, height,
        )

        if painted is None:
            return JSONResponse({"error": "Failed to process point"}, status_code=400)

        return JSONResponse({"image": _image_to_base64(painted)})

    @api.post("/add_target")
    async def add_target(session_id: str = Form(...)):
        """Finalize current clicks as a target."""
        session = sessions.get(session_id)
        if not session:
            return JSONResponse({"error": "Invalid session_id"}, status_code=404)
        session['runtime'] = pipeline.add_target(session['runtime'])
        return JSONResponse({"status": "ok", "current_id": session['runtime']['id']})

    @api.post("/session_generate_masks")
    async def session_generate_masks(session_id: str = Form(...)):
        """Run SAM-3 mask propagation for the session."""
        import torch
        session = sessions.get(session_id)
        if not session:
            return JSONResponse({"error": "Invalid session_id"}, status_code=404)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            mask_video = pipeline.generate_masks(session['runtime'], session['output_dir'])
        return FileResponse(mask_video, media_type="video/mp4", filename="mask_video.mp4")

    @api.post("/session_generate_4d")
    async def session_generate_4d(session_id: str = Form(...)):
        """Run 4D reconstruction for the session."""
        session = sessions.get(session_id)
        if not session:
            return JSONResponse({"error": "Invalid session_id"}, status_code=404)

        import torch
        with torch.autocast("cuda", enabled=False):
            result_video = pipeline.generate_4d(session['runtime'], session['output_dir'])

        # Zip results
        output_dir = session['output_dir']
        zip_path = f"{output_dir}/results.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(result_video):
                zf.write(result_video, "rendered_video.mp4")
            mesh_dir = f"{output_dir}/mesh_4d_individual"
            if os.path.isdir(mesh_dir):
                for dirpath, dirnames, filenames in os.walk(mesh_dir):
                    for f in filenames:
                        full = os.path.join(dirpath, f)
                        arcname = os.path.join("meshes", os.path.relpath(full, mesh_dir))
                        zf.write(full, arcname)

        return FileResponse(zip_path, media_type="application/zip", filename="sam_body4d_results.zip")

    @api.post("/delete_session")
    async def delete_session(session_id: str = Form(...)):
        """Clean up a session."""
        session = sessions.pop(session_id, None)
        if session and os.path.exists(session.get('video_path', '')):
            try:
                os.unlink(session['video_path'])
            except OSError:
                pass
        return JSONResponse({"status": "ok"})

    # ---- Async job system ----
    import threading
    jobs = {}  # job_id -> {status, progress, result_path, error}

    def _run_job(job_id, func, *args, **kwargs):
        """Run a function in a background thread, updating job status."""
        import torch
        try:
            jobs[job_id]['status'] = 'processing'
            # Ensure CUDA autocast context is available in this thread
            with torch.cuda.device(0):
                result = func(*args, **kwargs)
            jobs[job_id]['status'] = 'done'
            jobs[job_id]['result_path'] = result
        except Exception as e:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
            import traceback
            traceback.print_exc()

    @api.post("/session_generate_masks_async")
    async def session_generate_masks_async(session_id: str = Form(...)):
        """Start mask generation in background. Returns job_id."""
        session = sessions.get(session_id)
        if not session:
            return JSONResponse({"error": "Invalid session_id"}, status_code=404)

        job_id = _gen_id()
        jobs[job_id] = {'status': 'queued', 'progress': 0, 'result_path': None, 'error': None}

        import torch
        def run_masks():
            with torch.autocast("cuda", dtype=torch.bfloat16):
                return pipeline.generate_masks(session['runtime'], session['output_dir'])

        t = threading.Thread(target=_run_job, args=(job_id, run_masks), daemon=True)
        t.start()
        return JSONResponse({"job_id": job_id})

    @api.post("/session_generate_4d_async")
    async def session_generate_4d_async(session_id: str = Form(...)):
        """Start 4D reconstruction in background. Returns job_id."""
        session = sessions.get(session_id)
        if not session:
            return JSONResponse({"error": "Invalid session_id"}, status_code=404)

        job_id = _gen_id()
        jobs[job_id] = {'status': 'queued', 'progress': 0, 'result_path': None, 'error': None}

        def run_4d():
            import torch
            with torch.autocast("cuda", enabled=False):
                result_video = pipeline.generate_4d(session['runtime'], session['output_dir'])

            # Zip results
            output_dir = session['output_dir']
            zip_path = f"{output_dir}/results.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                if os.path.exists(result_video):
                    zf.write(result_video, "rendered_video.mp4")
                mesh_dir = f"{output_dir}/mesh_4d_individual"
                if os.path.isdir(mesh_dir):
                    for dirpath, dirnames, filenames in os.walk(mesh_dir):
                        for f in filenames:
                            full = os.path.join(dirpath, f)
                            arcname = os.path.join("meshes", os.path.relpath(full, mesh_dir))
                            zf.write(full, arcname)
            return zip_path

        t = threading.Thread(target=_run_job, args=(job_id, run_4d), daemon=True)
        t.start()
        return JSONResponse({"job_id": job_id})

    @api.get("/job/{job_id}")
    async def get_job_status(job_id: str):
        """Poll job status. Returns {status, progress, error}."""
        job = jobs.get(job_id)
        if not job:
            return JSONResponse({"error": "Invalid job_id"}, status_code=404)
        return JSONResponse({
            "status": job['status'],
            "progress": job.get('progress', 0),
            "error": job.get('error'),
        })

    @api.get("/job/{job_id}/result")
    async def get_job_result(job_id: str):
        """Download job result when done."""
        job = jobs.get(job_id)
        if not job:
            return JSONResponse({"error": "Invalid job_id"}, status_code=404)
        if job['status'] != 'done':
            return JSONResponse({"error": f"Job not done, status: {job['status']}"}, status_code=400)
        result_path = job['result_path']
        if not result_path or not os.path.exists(result_path):
            return JSONResponse({"error": "Result file not found"}, status_code=500)

        # Detect file type
        if result_path.endswith('.zip'):
            return FileResponse(result_path, media_type="application/zip", filename="results.zip")
        elif result_path.endswith('.mp4'):
            return FileResponse(result_path, media_type="video/mp4", filename="result.mp4")
        else:
            return FileResponse(result_path)

    # ---- One-shot endpoints (no session needed) ----

    @api.post("/process")
    async def process_video(video: UploadFile = File(...)):
        """End-to-end auto processing: upload video -> get results zip."""
        suffix = os.path.splitext(video.filename)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await video.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            output_dir = os.path.join(ROOT, "outputs", _gen_id())
            results = pipeline.process_video_auto(tmp_path, output_dir)

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

    print(f"API starting on port {args.api_port}...")
    uvicorn.run(api, host="0.0.0.0", port=args.api_port)


if __name__ == "__main__":
    main()
