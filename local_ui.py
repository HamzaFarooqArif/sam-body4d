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
        self._session_id = None

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

    def _base64_to_image(self, b64: str):
        import base64
        import io
        from PIL import Image
        return Image.open(io.BytesIO(base64.b64decode(b64)))

    def read_frame_at(self, path: str, idx: int):
        # If we have a session, get frame from pod
        if self._session_id:
            import requests
            r = requests.post(f"{self.api_url}/get_frame", data={
                "session_id": self._session_id,
                "frame_idx": idx,
            }, timeout=30)
            if r.status_code == 200:
                return self._base64_to_image(r.json()["frame"])
        # Fallback to local read
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
        """Upload video to pod and create a session."""
        import requests
        print(f"[RemotePipeline] Uploading video to pod...")
        with open(video_path, 'rb') as f:
            r = requests.post(
                f"{self.api_url}/init_video",
                files={"video": (os.path.basename(video_path), f, "video/mp4")},
                timeout=120,
            )
        if r.status_code != 200:
            raise RuntimeError(f"Failed to init video: {r.status_code} — {r.text}")

        data = r.json()
        self._session_id = data["session_id"]
        print(f"[RemotePipeline] Session created: {self._session_id}")

        return {
            'inference_state': None,
            'video_fps': data["fps"],
            'total_frames': data["total_frames"],
            'clicks': {},
            'id': 1,
            'objects': {},
            'masks': {},
            'out_obj_ids': [],
            'batch_size': self.batch_size,
            'detection_resolution': self.detection_resolution,
            'completion_resolution': self.completion_resolution,
            '_video_path': video_path,
            '_width': data["width"],
            '_height': data["height"],
        }

    def add_point(self, runtime, video_path, frame_idx, x, y, point_type, width, height):
        """Send click to pod, get real mask overlay back."""
        import requests
        if not self._session_id:
            return None, runtime

        r = requests.post(f"{self.api_url}/add_point", data={
            "session_id": self._session_id,
            "frame_idx": int(frame_idx),
            "x": int(x),
            "y": int(y),
            "point_type": point_type.lower(),
            "width": int(width),
            "height": int(height),
        }, timeout=30)

        if r.status_code != 200:
            print(f"[RemotePipeline] add_point error: {r.status_code} — {r.text}")
            return None, runtime

        painted = self._base64_to_image(r.json()["image"])

        # Keep local state in sync
        try:
            clicks = runtime['clicks'][frame_idx]
            clicks.append((x, y, point_type))
        except KeyError:
            clicks = [(x, y, point_type)]
        runtime['clicks'][frame_idx] = clicks
        if runtime['id'] not in runtime['out_obj_ids']:
            runtime['out_obj_ids'].append(runtime['id'])

        return painted, runtime

    def add_target(self, runtime):
        """Finalize target on the pod."""
        import requests
        if not self._session_id or not runtime['clicks']:
            return runtime

        r = requests.post(f"{self.api_url}/add_target", data={
            "session_id": self._session_id,
        }, timeout=30)

        if r.status_code == 200:
            runtime['objects'][runtime['id']] = runtime['clicks']
            runtime['id'] = r.json().get("current_id", runtime['id'] + 1)
            runtime['clicks'] = {}

        return runtime

    def generate_masks(self, runtime, output_dir):
        """Tell pod to run SAM-3 mask propagation."""
        import requests
        if not self._session_id:
            raise RuntimeError("No session")

        print(f"[RemotePipeline] Generating masks on pod...")
        r = requests.post(f"{self.api_url}/session_generate_masks", data={
            "session_id": self._session_id,
        }, timeout=600)

        if r.status_code != 200:
            raise RuntimeError(f"API error: {r.status_code} — {r.text}")

        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "mask_video.mp4")
        with open(out_path, 'wb') as f:
            f.write(r.content)

        print(f"[RemotePipeline] Mask video saved to {out_path}")
        return out_path

    def generate_4d(self, runtime, output_dir):
        """Tell pod to run 4D reconstruction."""
        import requests
        import zipfile

        if not self._session_id:
            raise RuntimeError("No session")

        print(f"[RemotePipeline] Generating 4D on pod...")
        r = requests.post(f"{self.api_url}/session_generate_4d", data={
            "session_id": self._session_id,
        }, timeout=1200)

        if r.status_code != 200:
            raise RuntimeError(f"API error: {r.status_code} — {r.text}")

        os.makedirs(output_dir, exist_ok=True)
        zip_path = os.path.join(output_dir, "results.zip")
        with open(zip_path, 'wb') as f:
            f.write(r.content)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(output_dir)

        result_video = os.path.join(output_dir, "rendered_video.mp4")
        if os.path.exists(result_video):
            print(f"[RemotePipeline] 4D video saved to {result_video}")
            return result_video

        for f in os.listdir(output_dir):
            if f.endswith('.mp4') and '4d' in f.lower():
                return os.path.join(output_dir, f)
        return result_video

    def process_video_auto(self, video_path: str, output_dir: str = None):
        if output_dir is None:
            output_dir = os.path.join("outputs", f"remote_{os.getpid()}")
        runtime = self.init_video_state(video_path)
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