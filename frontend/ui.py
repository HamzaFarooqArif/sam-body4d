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
            return None, "00:00 / 00:00"
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
        return frame, f"{cur_text} / {end_text}"

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

    def toggle_upload(open_state):
        new_state = not open_state
        label = "Upload Video (click to close)" if new_state else "Upload Video (click to open)"
        return new_state, gr.update(visible=new_state), gr.update(value=label)

    def on_mask_generation(video_path):
        if video_path is None or runtime_holder['runtime'] is None:
            raise gr.Error("No video loaded.")
        runtime_holder['job_label'] = "Mask generation"
        runtime_holder['job_start_time'] = _time.time()

        # If pipeline supports job tracking, use it
        if has_job_progress:
            runtime_holder['job_id'] = 'starting'
        result = pipeline.generate_masks(runtime_holder['runtime'], runtime_holder['output_dir'])
        runtime_holder['job_id'] = None
        runtime_holder['job_label'] = None
        return result, "**Status:** Mask generation complete! &#9989;"

    def on_4d_generation(video_path):
        if video_path is None or runtime_holder['runtime'] is None:
            raise gr.Error("No video loaded.")
        runtime_holder['job_label'] = "4D generation"
        runtime_holder['job_start_time'] = _time.time()

        if has_job_progress:
            runtime_holder['job_id'] = 'starting'
        result = pipeline.generate_4d(runtime_holder['runtime'], runtime_holder['output_dir'])
        runtime_holder['job_id'] = None
        runtime_holder['job_label'] = None
        return result, "**Status:** 4D generation complete! &#9989;"

    def poll_status():
        """Called by Timer every 2 seconds to update status text."""
        job_label = runtime_holder.get('job_label')
        if not job_label:
            return gr.update()

        elapsed = _time.time() - (runtime_holder.get('job_start_time') or _time.time())
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        # Try to get real progress from pipeline
        pct = None
        if has_job_progress:
            pct = pipeline.get_job_progress()

        if pct is not None and pct > 0:
            bar_fill = int(pct / 5)  # 20 chars max
            bar_empty = 20 - bar_fill
            bar = "█" * bar_fill + "░" * bar_empty
            return f"**Status:** {job_label}... {pct}% ({time_str})\n\n`{bar}` {pct}%"
        else:
            dots = "." * (int(elapsed) % 4 + 1)
            return f"**Status:** {job_label}{dots} ({time_str})"

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
                toggle_upload_btn = gr.Button("Upload Video (click to open)", size="sm", variant="secondary")
                upload_panel = gr.Row(visible=False)
                with upload_panel:
                    upload = gr.File(label="Video File", file_count="single")
                frame_slider = gr.Slider(minimum=0, maximum=0, value=0, step=1, label="Frame Index")
                time_text = gr.Text("00:00 / 00:00", label="Time")
                point_radio = gr.Radio(choices=["Positive", "Negative"], value="Positive", label="Point Type", interactive=True)
                targets_box = gr.CheckboxGroup(label="Targets", choices=[], value=[])
                add_target_btn = gr.Button("Add Target")

            with gr.Column(scale=1):
                status_text = gr.Markdown("**Status:** Ready", elem_id="status-text")
                result_display = gr.Video(label="Segmentation Result")
                with gr.Row():
                    mask_gen_btn = gr.Button("Mask Generation")
                    gen4d_btn = gr.Button("4D Generation")
                fourd_display = gr.Video(label="4D Result")

        # ---- Timer for live status polling ----
        timer = gr.Timer(2)
        timer.tick(fn=poll_status, outputs=[status_text])

        # ---- Event bindings ----
        toggle_upload_btn.click(fn=toggle_upload, inputs=[upload_open_state], outputs=[upload_open_state, upload_panel, toggle_upload_btn])
        upload.change(fn=on_upload, inputs=[upload], outputs=[video_state, fps_state, current_frame, frame_slider, time_text])
        examples_gallery.select(fn=on_example_select, inputs=None, outputs=[video_state, fps_state, current_frame, frame_slider, time_text])
        frame_slider.change(fn=update_frame, inputs=[frame_slider, video_state, fps_state], outputs=[current_frame, time_text])
        point_radio.change(fn=lambda v: v.lower(), inputs=[point_radio], outputs=[point_type_state])
        current_frame.select(fn=on_click, inputs=[point_type_state, video_state, frame_slider], outputs=[current_frame])
        add_target_btn.click(fn=add_target, inputs=[targets_state, selected_targets_state], outputs=[targets_state, selected_targets_state, targets_box])
        mask_gen_btn.click(fn=on_mask_generation, inputs=[video_state], outputs=[result_display, status_text])
        gen4d_btn.click(fn=on_4d_generation, inputs=[video_state], outputs=[fourd_display, status_text])

    return demo
