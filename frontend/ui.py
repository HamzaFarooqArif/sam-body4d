"""
Frontend — Gradio UI definition.
No model imports. Only knows about the pipeline interface.
"""

import os
import uuid
import time as _time
from datetime import datetime

import cv2
import gradio as gr
import numpy as np
from PIL import Image

from utils import draw_point_marker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXAMPLE_1 = os.path.join(ROOT, "assets", "examples", "example1.mp4")
EXAMPLE_2 = os.path.join(ROOT, "assets", "examples", "example2.mp4")
EXAMPLE_3 = os.path.join(ROOT, "assets", "examples", "example3.mp4")
SUPPORTED_EXTS = {".mp4"}


def _gen_id():
    t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    u = uuid.uuid4().hex[:8]
    return f"{t}_{u}"


def _get_thumb(path):
    if not os.path.exists(path):
        return None
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def build_ui(pipeline):
    """
    Build the Gradio UI. `pipeline` can be:
    - backend.pipeline.Pipeline (real models on GPU)
    - backend.mock.MockPipeline (fake data, no GPU)
    - A remote API wrapper (calls pod)
    """

    # Shared state
    runtime_holder = {
        'runtime': None,
        'output_dir': None,
        'video_path': None,
        'job_id': None,
        'job_label': None,
        'job_start_time': None,
    }

    # Thumbnails
    ex1_thumb = _get_thumb(EXAMPLE_1)
    ex2_thumb = _get_thumb(EXAMPLE_2)
    ex3_thumb = _get_thumb(EXAMPLE_3)

    # Check if pipeline has get_job_progress (RemotePipeline does)
    has_job_progress = hasattr(pipeline, 'get_job_progress')

    # ---- Handlers ----

    def prepare_video(path):
        if path is None:
            return None, 1.0, None, gr.update(minimum=0, maximum=0, value=0), "00:00 / 00:00"
        if not os.path.exists(path):
            raise gr.Error(f"Video not found: {path}")
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED_EXTS:
            raise gr.Error(f"Unsupported format {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTS))}")

        fps, total = pipeline.read_video_metadata(path)
        if fps <= 0 or total <= 0:
            raise gr.Error("Invalid video metadata.")

        first_frame = pipeline.read_frame_at(path, 0)
        if first_frame is None:
            raise gr.Error("Failed to read first frame.")

        runtime = pipeline.init_video_state(path)
        runtime['video_fps'] = fps
        output_dir = os.path.join(ROOT, "outputs", _gen_id())
        os.makedirs(output_dir, exist_ok=True)

        runtime_holder['runtime'] = runtime
        runtime_holder['output_dir'] = output_dir
        runtime_holder['video_path'] = path
        runtime_holder['job_id'] = None

        slider_cfg = gr.update(minimum=0, maximum=total - 1, value=0)
        dur = total / fps
        total_text = f"{int(dur // 60):02d}:{int(dur % 60):02d}"
        time_text = f"00:00 / {total_text}"

        return path, fps, first_frame, slider_cfg, time_text

    def on_upload(file_obj):
        if file_obj is None:
            return prepare_video(None)
        return prepare_video(file_obj.name)

    def on_example_select(evt: gr.SelectData):
        idx = evt.index
        if isinstance(idx, (list, tuple)):
            idx = idx[0]
        paths = [EXAMPLE_1, EXAMPLE_2, EXAMPLE_3]
        if idx >= len(paths):
            raise gr.Error("Unknown example index.")
        return prepare_video(paths[idx])

    def update_frame(idx, path, fps):
        if path is None:
            return gr.update(value=None, visible=True), gr.update(visible=False), "00:00 / 00:00"
        idx = int(idx)
        frame = pipeline.read_frame_at(path, idx)
        if frame is None:
            raise gr.Error(f"Failed to read frame {idx}.")

        cur_sec = idx / fps if fps > 0 else 0.0
        cur_text = f"{int(cur_sec // 60):02d}:{int(cur_sec % 60):02d}"
        cap = cv2.VideoCapture(path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        dur = total / fps if fps > 0 else 0.0
        end_text = f"{int(dur // 60):02d}:{int(dur % 60):02d}"
        return gr.update(value=frame, visible=True), gr.update(visible=False), f"{cur_text} / {end_text}"

    def on_click(evt: gr.SelectData, point_type, video_path, frame_idx):
        if video_path is None or runtime_holder['runtime'] is None:
            return None
        x, y = evt.index
        frame = pipeline.read_frame_at(video_path, int(frame_idx))
        if frame is None:
            raise gr.Error(f"Failed to read frame {frame_idx}.")
        width, height = frame.size

        painted, runtime_holder['runtime'] = pipeline.add_point(
            runtime_holder['runtime'], video_path, int(frame_idx),
            x, y, point_type.lower(), width, height,
        )
        if painted is not None:
            painted = draw_point_marker(painted, x, y, point_type.lower())
        return painted

    def add_target(targets, selected):
        if runtime_holder['runtime'] is None:
            return targets, selected, gr.update(choices=targets, value=selected)
        if not runtime_holder['runtime'].get('clicks', {}):
            return targets, selected, gr.update(choices=targets, value=selected)

        name = f"Target {len(targets) + 1}"
        targets = targets + [name]
        selected = selected + [name]
        runtime_holder['runtime'] = pipeline.add_target(runtime_holder['runtime'])
        return targets, selected, gr.update(choices=targets, value=selected)

    def on_preview_fps(video_path, pct):
        """Create a preview video using only the frames that would be processed."""
        if video_path is None:
            raise gr.Error("No video loaded.")

        import cv2 as _cv2
        cap = _cv2.VideoCapture(video_path)
        total = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(_cv2.CAP_PROP_FPS) or 30
        w = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))

        step = max(1, round(100 / pct)) if pct > 0 else 1
        selected_frames = list(range(0, total, step))

        preview_path = os.path.join(ROOT, "outputs", f"preview_{_gen_id()}.mp4")
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)

        # Collect frames
        frames = []
        prev_frame = None
        selected_set = set(selected_frames)
        for idx in range(total):
            cap.set(_cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                break
            if idx in selected_set:
                prev_frame = frame
            if prev_frame is not None:
                frames.append(prev_frame)
        cap.release()

        # Write with imageio (H.264, browser-compatible)
        import imageio.v2 as imageio
        writer = imageio.get_writer(preview_path, fps=fps, codec='libx264', quality=8)
        for frame in frames:
            writer.append_data(_cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB))
        writer.close()

        info = f"**Preview:** {len(selected_frames)} / {total} frames (every {step}) | Original FPS: {fps:.0f}"
        return gr.update(visible=False), gr.update(value=preview_path, visible=True), info

    def on_framerate_change(pct):
        rt = runtime_holder.get('runtime')
        if rt is None:
            return "**Frames to process:** — / — | **Estimated speedup:** 1x"
        total = rt.get('total_frames', 0)
        to_process = max(1, int(total * pct / 100))
        skip = max(1, round(100 / pct))
        speedup = f"{100 / pct:.1f}x" if pct > 0 else "—"
        return f"**Frames to process:** {to_process} / {total} (every {skip} frame{'s' if skip > 1 else ''}) | **Estimated speedup:** {speedup}"

    def toggle_upload(open_state):
        new_state = not open_state
        label = "Upload Video (click to close)" if new_state else "Upload Video (click to open)"
        return new_state, gr.update(visible=new_state), gr.update(value=label)

    def _progress_html(label, pct, time_str):
        """Generate HTML progress bar."""
        bar_width = max(0, min(pct, 100))
        return f"""
        <div style="padding: 40px 20px; text-align: center; background: #1a1a2e; border-radius: 8px; min-height: 200px; display: flex; flex-direction: column; justify-content: center; align-items: center;">
            <div style="font-size: 18px; color: #e0e0e0; margin-bottom: 16px;">{label}</div>
            <div style="width: 80%; background: #2a2a4a; border-radius: 10px; height: 24px; overflow: hidden; margin-bottom: 12px;">
                <div style="width: {bar_width}%; background: linear-gradient(90deg, #4a9eff, #7c3aed); height: 100%; border-radius: 10px; transition: width 0.5s ease;"></div>
            </div>
            <div style="font-size: 24px; font-weight: bold; color: #4a9eff;">{pct}%</div>
            <div style="font-size: 14px; color: #888; margin-top: 8px;">{time_str} elapsed</div>
        </div>
        """

    def _ready_html(label):
        return f"""
        <div style="padding: 40px 20px; text-align: center; background: #1a2e1a; border-radius: 8px; min-height: 60px; display: flex; justify-content: center; align-items: center;">
            <div style="font-size: 18px; color: #4ade80;">{label} complete!</div>
        </div>
        """

    def on_mask_generation(video_path, framerate_pct):
        if video_path is None or runtime_holder['runtime'] is None:
            raise gr.Error("No video loaded.")
        runtime_holder['job_label'] = "Mask generation"
        runtime_holder['job_start_time'] = _time.time()
        runtime_holder['job_target'] = 'mask'
        runtime_holder['_calibration'] = None
        runtime_holder['_last_pct'] = 0

        # Store framerate setting in runtime for pipeline to use
        runtime_holder['runtime']['frame_step'] = max(1, round(100 / framerate_pct)) if framerate_pct > 0 else 1

        if has_job_progress:
            runtime_holder['job_id'] = 'starting'
        result = pipeline.generate_masks(runtime_holder['runtime'], runtime_holder['output_dir'])
        runtime_holder['job_id'] = None
        runtime_holder['job_label'] = None
        runtime_holder['job_target'] = None
        return gr.update(visible=False), gr.update(value=result, visible=True)

    def on_4d_generation(video_path, framerate_pct):
        if video_path is None or runtime_holder['runtime'] is None:
            raise gr.Error("No video loaded.")
        runtime_holder['job_label'] = "4D generation"
        runtime_holder['job_start_time'] = _time.time()
        runtime_holder['job_target'] = '4d'
        runtime_holder['_calibration'] = None
        runtime_holder['_last_pct'] = 0

        runtime_holder['runtime']['frame_step'] = max(1, round(100 / framerate_pct)) if framerate_pct > 0 else 1

        if has_job_progress:
            runtime_holder['job_id'] = 'starting'
        result = pipeline.generate_4d(runtime_holder['runtime'], runtime_holder['output_dir'])
        runtime_holder['job_id'] = None
        runtime_holder['job_label'] = None
        runtime_holder['job_target'] = None
        return gr.update(visible=False), gr.update(value=result, visible=True)

    def on_mask_start(video_path):
        if video_path is None or runtime_holder['runtime'] is None:
            raise gr.Error("No video loaded.")
        html = _progress_html("Mask generation", 0, "0s")
        # outputs: mask_progress, result_display — only touch mask area
        return gr.update(value=html, visible=True), gr.update(visible=False)

    def on_4d_start(video_path):
        if video_path is None or runtime_holder['runtime'] is None:
            raise gr.Error("No video loaded.")
        html = _progress_html("4D generation (~6 min)", 0, "0s")
        # outputs: fourd_progress, fourd_display — only touch 4D area
        return gr.update(value=html, visible=True), gr.update(visible=False)

    def poll_progress():
        """Called by Timer every 2 seconds to update progress display."""
        job_label = runtime_holder.get('job_label')
        if not job_label:
            return gr.update()

        elapsed = _time.time() - (runtime_holder.get('job_start_time') or _time.time())
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        # Get real progress from pipeline
        real_pct = 0
        if has_job_progress:
            real_pct = pipeline.get_job_progress() or 0

        # Adaptive speed estimation
        # After first real progress update, calibrate estimated total time
        cal = runtime_holder.get('_calibration')
        if real_pct > 0 and real_pct < 100:
            if cal is None:
                # First real progress received — calibrate
                # If we're at real_pct% after elapsed seconds,
                # estimate total = elapsed / (real_pct/100)
                est_total = elapsed / (real_pct / 100.0)
                runtime_holder['_calibration'] = {
                    'est_total': est_total,
                    'last_real_pct': real_pct,
                    'last_real_time': elapsed,
                }
            elif real_pct > cal['last_real_pct']:
                # New real progress — recalibrate
                est_total = elapsed / (real_pct / 100.0)
                cal['est_total'] = est_total
                cal['last_real_pct'] = real_pct
                cal['last_real_time'] = elapsed

        if cal and cal.get('est_total', 0) > 0:
            # Interpolate smoothly based on calibrated speed
            time_pct = min(95, int(100 * elapsed / cal['est_total']))
            pct = max(real_pct, time_pct)
        elif real_pct > 0:
            pct = real_pct
        else:
            # No data yet — show indeterminate
            dots = "." * (int(elapsed) % 4 + 1)
            return _progress_html(f"{job_label}{dots}", 0, time_str)

        # Never go backwards
        prev = runtime_holder.get('_last_pct', 0)
        pct = max(pct, prev)
        runtime_holder['_last_pct'] = pct

        return _progress_html(job_label, pct, time_str)

    # ---- Layout ----

    with gr.Blocks(title="SAM-Body4D") as demo:
        video_state = gr.State(None)
        fps_state = gr.State(1.0)
        point_type_state = gr.State("positive")
        targets_state = gr.State([])
        selected_targets_state = gr.State([])
        upload_open_state = gr.State(False)

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Example Videos")
                examples_gallery = gr.Gallery(
                    value=[
                        (ex1_thumb, "Example 1"),
                        (ex2_thumb, "Example 2"),
                        (ex3_thumb, "Example 3"),
                    ],
                    show_label=False, columns=3, height=160,
                )
                current_frame = gr.Image(
                    label="Current Frame (click to annotate)",
                    interactive=True, sources=[],
                )
                preview_video = gr.Video(label="Frame Rate Preview (click frame to go back to annotation)", visible=False)
                toggle_upload_btn = gr.Button("Upload Video (click to open)", size="sm", variant="secondary")
                upload_panel = gr.Row(visible=False)
                with upload_panel:
                    upload = gr.File(label="Video File", file_count="single")
                with gr.Row():
                    framerate_slider = gr.Slider(minimum=10, maximum=100, value=100, step=5, label="Processing Frame Rate (%)", info="100% = all frames, 50% = every 2nd frame", scale=3)
                    preview_fps_btn = gr.Button("Preview", size="sm", scale=1)
                framerate_info = gr.Markdown("**Frames to process:** — / — | **Estimated speedup:** 1x")
                frame_slider = gr.Slider(minimum=0, maximum=0, value=0, step=1, label="Frame Index")
                time_text = gr.Text("00:00 / 00:00", label="Time")
                point_radio = gr.Radio(choices=["Positive", "Negative"], value="Positive", label="Point Type", interactive=True)
                targets_box = gr.CheckboxGroup(label="Targets", choices=[], value=[])
                add_target_btn = gr.Button("Add Target")

            with gr.Column(scale=1):
                mask_progress = gr.HTML(visible=False)
                result_display = gr.Video(label="Segmentation Result")
                with gr.Row():
                    mask_gen_btn = gr.Button("Mask Generation")
                    gen4d_btn = gr.Button("4D Generation")
                fourd_progress = gr.HTML(visible=False)
                fourd_display = gr.Video(label="4D Result")

        # ---- Timer for live progress ----
        def poll_both():
            target = runtime_holder.get('job_target')
            update = poll_progress()
            if target == 'mask':
                return update, gr.update()
            elif target == '4d':
                return gr.update(), update
            else:
                return gr.update(), gr.update()

        timer = gr.Timer(2)
        timer.tick(fn=poll_both, outputs=[mask_progress, fourd_progress])

        # ---- Event bindings ----
        toggle_upload_btn.click(fn=toggle_upload, inputs=[upload_open_state], outputs=[upload_open_state, upload_panel, toggle_upload_btn])
        upload.change(fn=on_upload, inputs=[upload], outputs=[video_state, fps_state, current_frame, frame_slider, time_text])
        examples_gallery.select(fn=on_example_select, inputs=None, outputs=[video_state, fps_state, current_frame, frame_slider, time_text])
        framerate_slider.change(fn=on_framerate_change, inputs=[framerate_slider], outputs=[framerate_info])
        preview_fps_btn.click(fn=on_preview_fps, inputs=[video_state, framerate_slider], outputs=[current_frame, preview_video, framerate_info])
        frame_slider.change(fn=update_frame, inputs=[frame_slider, video_state, fps_state], outputs=[current_frame, preview_video, time_text])
        point_radio.change(fn=lambda v: v.lower(), inputs=[point_radio], outputs=[point_type_state])
        current_frame.select(fn=on_click, inputs=[point_type_state, video_state, frame_slider], outputs=[current_frame])
        add_target_btn.click(fn=add_target, inputs=[targets_state, selected_targets_state], outputs=[targets_state, selected_targets_state, targets_box])
        mask_gen_btn.click(
            fn=on_mask_start, inputs=[video_state], outputs=[mask_progress, result_display]
        ).then(
            fn=on_mask_generation, inputs=[video_state, framerate_slider], outputs=[mask_progress, result_display]
        )
        gen4d_btn.click(
            fn=on_4d_start, inputs=[video_state], outputs=[fourd_progress, fourd_display]
        ).then(
            fn=on_4d_generation, inputs=[video_state, framerate_slider], outputs=[fourd_progress, fourd_display]
        )

    return demo
