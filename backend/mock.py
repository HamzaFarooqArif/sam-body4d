"""
Mock pipeline — returns fake data instantly. No GPU needed.
Same interface as Pipeline so frontend code works unchanged.
"""

import os
import time
import uuid
import numpy as np
from PIL import Image
from datetime import datetime


def _gen_id():
    t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    u = uuid.uuid4().hex[:8]
    return f"{t}_{u}"


class MockPipeline:
    """Drop-in replacement for Pipeline that returns dummy data."""

    def __init__(self, config_path: str = None):
        print("[MockPipeline] Initialized (no models loaded, no GPU needed)")
        self.batch_size = 64
        self.detection_resolution = [256, 512]
        self.completion_resolution = [512, 1024]

    def read_frame_at(self, path: str, idx: int):
        import cv2
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame)

    def read_video_metadata(self, path: str):
        import cv2
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        return fps, total

    def init_video_state(self, video_path: str):
        fps, total = self.read_video_metadata(video_path)
        return {
            'inference_state': None,
            'video_fps': fps,
            'total_frames': total,
            'clicks': {},
            'id': 1,
            'objects': {},
            'masks': {},
            'out_obj_ids': [],
            'batch_size': self.batch_size,
            'detection_resolution': self.detection_resolution,
            'completion_resolution': self.completion_resolution,
        }

    def add_point(self, runtime, video_path, frame_idx, x, y, point_type, width, height):
        """Return frame with a simple circle drawn at click point."""
        frame = self.read_frame_at(video_path, int(frame_idx))
        if frame is None:
            return None, runtime

        import cv2
        img = np.array(frame)
        color = (0, 255, 0) if point_type.lower() == "positive" else (255, 0, 0)
        cv2.circle(img, (int(x), int(y)), 10, color, -1)

        try:
            clicks = runtime['clicks'][frame_idx]
            clicks.append((x, y, point_type))
        except KeyError:
            clicks = [(x, y, point_type)]
        runtime['clicks'][frame_idx] = clicks

        if runtime['id'] not in runtime['out_obj_ids']:
            runtime['out_obj_ids'].append(runtime['id'])

        return Image.fromarray(img), runtime

    def add_target(self, runtime):
        if not runtime['clicks']:
            return runtime
        runtime['objects'][runtime['id']] = runtime['clicks']
        runtime['id'] += 1
        runtime['clicks'] = {}
        return runtime

    def generate_masks(self, runtime, output_dir):
        """Return a copy of the input video as fake mask output."""
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'images'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'masks'), exist_ok=True)

        # Create a simple placeholder video
        out_path = os.path.join(output_dir, f"video_mask_mock_{time.time():.0f}.mp4")

        import cv2
        cap = cv2.VideoCapture(runtime.get('_video_path', ''))
        if not cap.isOpened():
            # Create a blank video
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(out_path, fourcc, 30, (640, 480))
            for i in range(30):
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, f"MOCK Frame {i}", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                writer.write(frame)
            writer.release()
        else:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
            frame_idx = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                cv2.putText(frame, f"MOCK MASK - Frame {frame_idx}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                writer.write(frame)

                # Save frames for generate_4d mock
                img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                img_pil.save(os.path.join(output_dir, 'images', f"{frame_idx:08d}.jpg"))
                mask_pil = Image.fromarray(np.ones((h, w), dtype=np.uint8))
                mask_pil.save(os.path.join(output_dir, 'masks', f"{frame_idx:08d}.png"))

                frame_idx += 1
            cap.release()
            writer.release()

        print(f"[MockPipeline] generate_masks -> {out_path}")
        return out_path

    def generate_4d(self, runtime, output_dir):
        """Return a placeholder video as fake 4D output."""
        out_path = os.path.join(output_dir, f"4d_mock_{time.time():.0f}.mp4")

        import cv2
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = runtime.get('video_fps', 30)
        writer = cv2.VideoWriter(out_path, fourcc, fps, (640, 480))
        for i in range(60):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "MOCK 4D OUTPUT", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
            cv2.putText(frame, f"Frame {i}", (50, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
            writer.write(frame)
        writer.release()

        print(f"[MockPipeline] generate_4d -> {out_path}")
        return out_path

    def process_video_auto(self, video_path: str, output_dir: str = None):
        if output_dir is None:
            output_dir = os.path.join("outputs", _gen_id())
        os.makedirs(output_dir, exist_ok=True)

        runtime = self.init_video_state(video_path)
        runtime['_video_path'] = video_path
        runtime['out_obj_ids'] = [1]

        mask_video = self.generate_masks(runtime, output_dir)
        result_video = self.generate_4d(runtime, output_dir)

        return {
            'mask_video': mask_video,
            'result_video': result_video,
            'output_dir': output_dir,
            'mesh_dir': f"{output_dir}/mesh_4d_individual",
        }