"""
local_ui.py — Run on your PC for development.

Modes:
  python local_ui.py --mock              # Fake data, no GPU, free
  python local_ui.py --api https://pod:8000  # Real results via pod API

"""

import os
import sys
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ["GRADIO_TEMP_DIR"] = os.path.join(ROOT, "gradio_tmp")
sys.path.append(ROOT)


class RemotePipeline:
    """
    Wraps the pod's API into the same interface as Pipeline/MockPipeline.
    Sends video to pod, gets real results back.
    """

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip('/')
        self.batch_size = 64
        self.detection_resolution = [256, 512]
        self.completion_resolution = [512, 1024]

        # Check connection
        import requests
        try:
            r = requests.get(f"{self.api_url}/health", timeout=10)
            if r.status_code == 200:
                print(f"[RemotePipeline] Connected to {self.api_url}")
            else:
                print(f"[RemotePipeline] Warning: API returned status {r.status_code}")
        except Exception as e:
            print(f"[RemotePipeline] Warning: Cannot reach {self.api_url} — {e}")
            print("  Make sure the pod is running server.py")

    def read_frame_at(self, path: str, idx: int):
        import cv2
        from PIL import Image
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

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
            '_video_path': video_path,
        }

    def add_point(self, runtime, video_path, frame_idx, x, y, point_type, width, height):
        """Local point annotation (visual only, no model call needed)."""
        import cv2
        import numpy as np
        from PIL import Image

        frame = self.read_frame_at(video_path, int(frame_idx))
        if frame is None:
            return None, runtime

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
        """Send video to pod API for mask generation."""
        import requests
        video_path = runtime.get('_video_path', '')
        if not video_path or not os.path.exists(video_path):
            raise RuntimeError("No video loaded")

        print(f"[RemotePipeline] Sending video to {self.api_url}/generate_masks ...")
        with open(video_path, 'rb') as f:
            r = requests.post(
                f"{self.api_url}/generate_masks",
                files={"video": (os.path.basename(video_path), f, "video/mp4")},
                timeout=600,
            )

        if r.status_code != 200:
            raise RuntimeError(f"API error: {r.status_code} — {r.text}")

        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "mask_video.mp4")
        with open(out_path, 'wb') as f:
            f.write(r.content)

        print(f"[RemotePipeline] Mask video saved to {out_path}")
        return out_path

    def generate_4d(self, runtime, output_dir):
        """Send video to pod API for full processing."""
        import requests
        import zipfile
        import tempfile

        video_path = runtime.get('_video_path', '')
        if not video_path or not os.path.exists(video_path):
            raise RuntimeError("No video loaded")

        print(f"[RemotePipeline] Sending video to {self.api_url}/process ...")
        with open(video_path, 'rb') as f:
            r = requests.post(
                f"{self.api_url}/process",
                files={"video": (os.path.basename(video_path), f, "video/mp4")},
                timeout=1200,
            )

        if r.status_code != 200:
            raise RuntimeError(f"API error: {r.status_code} — {r.text}")

        os.makedirs(output_dir, exist_ok=True)

        # Save and extract zip
        zip_path = os.path.join(output_dir, "results.zip")
        with open(zip_path, 'wb') as f:
            f.write(r.content)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(output_dir)

        result_video = os.path.join(output_dir, "rendered_video.mp4")
        if os.path.exists(result_video):
            print(f"[RemotePipeline] 4D video saved to {result_video}")
            return result_video

        # Fallback: return any mp4 found
        for f in os.listdir(output_dir):
            if f.endswith('.mp4') and '4d' in f.lower():
                return os.path.join(output_dir, f)
        return result_video

    def process_video_auto(self, video_path: str, output_dir: str = None):
        if output_dir is None:
            output_dir = os.path.join("outputs", f"remote_{os.getpid()}")
        runtime = self.init_video_state(video_path)
        runtime['_video_path'] = video_path
        result_video = self.generate_4d(runtime, output_dir)
        return {
            'result_video': result_video,
            'output_dir': output_dir,
        }


def main():
    parser = argparse.ArgumentParser(description="SAM-Body4D Local UI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--mock", action="store_true", help="Use mock pipeline (fake data, no GPU)")
    group.add_argument("--api", type=str, help="Pod API URL (e.g., https://pod:8000)")
    parser.add_argument("--port", type=int, default=7860, help="Local Gradio port")
    args = parser.parse_args()

    if args.mock:
        from backend.mock import MockPipeline
        pipeline = MockPipeline()
    else:
        pipeline = RemotePipeline(args.api)

    from frontend.ui import build_ui
    demo = build_ui(pipeline)
    demo.launch(server_name="127.0.0.1", server_port=args.port)


if __name__ == "__main__":
    main()