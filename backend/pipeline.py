"""
Backend pipeline — loads models and processes videos.
Extracted from app.py. No UI logic here.
"""

import os
import sys
import time
import uuid
import glob
import random
from datetime import datetime

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from tqdm import tqdm
from omegaconf import OmegaConf

# Ensure model paths are importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, 'models', 'sam_3d_body'))
sys.path.append(os.path.join(ROOT, 'models', 'diffusion_vas'))

from utils import (
    mask_painter, images_to_mp4, DAVIS_PALETTE, jpg_folder_to_mp4,
    is_super_long_or_wide, keep_largest_component, is_skinny_mask,
    bbox_from_mask, gpu_profile, resize_mask_with_unique_label,
)
from models.sam_3d_body.sam_3d_body import load_sam_3d_body, SAM3DBodyEstimator
from models.sam_3d_body.notebook.utils import process_image_with_mask, save_mesh_results
from models.sam_3d_body.tools.vis_utils import visualize_sample_together, visualize_sample
from models.diffusion_vas.demo import (
    init_amodal_segmentation_model, init_rgb_model, init_depth_model,
    load_and_transform_masks, load_and_transform_rgbs, rgb_to_depth,
)

from typing import List, Sequence


def _gen_id():
    t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    u = uuid.uuid4().hex[:8]
    return f"{t}_{u}"


def _setup_device():
    if torch.cuda.is_available():
        device = torch.device("cuda")
        if torch.cuda.get_device_properties(0).major >= 8:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    print(f"using device: {device}")
    return device


def _build_sam3(cfg):
    from models.sam3.sam3.model_builder import build_sam3_video_model
    sam3_model = build_sam3_video_model(checkpoint_path=cfg.sam3['ckpt_path'])
    predictor = sam3_model.tracker
    predictor.backbone = sam3_model.detector.backbone
    return sam3_model, predictor


def _build_sam3_3d_body(cfg):
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    mhr_path = cfg.sam_3d_body['mhr_path']
    fov_path = cfg.sam_3d_body['fov_path']
    model, model_cfg = load_sam_3d_body(
        cfg.sam_3d_body['ckpt_path'], device=device, mhr_path=mhr_path
    )
    human_detector, human_segmentor, fov_estimator = None, None, None
    from models.sam_3d_body.tools.build_fov_estimator import FOVEstimator
    fov_estimator = FOVEstimator(name='moge2', device=device, path=fov_path)

    estimator = SAM3DBodyEstimator(
        sam_3d_body_model=model,
        model_cfg=model_cfg,
        human_detector=human_detector,
        human_segmentor=human_segmentor,
        fov_estimator=fov_estimator,
    )
    return estimator


def _build_diffusion_vas(cfg):
    model_path_mask = cfg.completion['model_path_mask']
    model_path_rgb = cfg.completion['model_path_rgb']
    depth_encoder = cfg.completion['depth_encoder']
    model_path_depth = cfg.completion['model_path_depth']
    max_occ_len = min(cfg.completion['max_occ_len'], cfg.sam_3d_body['batch_size'])
    generator = torch.manual_seed(23)
    pipeline_mask = init_amodal_segmentation_model(model_path_mask)
    pipeline_rgb = init_rgb_model(model_path_rgb)
    depth_model = init_depth_model(model_path_depth, depth_encoder)
    return pipeline_mask, pipeline_rgb, depth_model, max_occ_len, generator


def cap_consecutive_ones_by_iou(
    flag: Sequence[int],
    iou: Sequence[float],
    max_keep: int = 3,
) -> List[int]:
    n = len(flag)
    if len(iou) != n:
        raise ValueError(f"len(flag)={n} != len(iou)={len(iou)}")
    out = [1 if flag[i] == 0 else 0 for i in range(n)]
    i = 0
    while i < n:
        if flag[i] != 1:
            i += 1
            continue
        j = i
        while j < n and flag[j] == 1:
            j += 1
        run_idx = list(range(i, j))
        if len(run_idx) <= max_keep:
            for k in run_idx:
                out[k] = 1
        else:
            top = sorted(run_idx, key=lambda k: (-float(iou[k]), k))[:max_keep]
            for k in top:
                out[k] = 1
        i = j
    return out


class Pipeline:
    """Loads all models and provides processing methods."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(ROOT, "configs", "body4d.yaml")

        _setup_device()

        self.config = OmegaConf.load(config_path)
        self.sam3_model, self.predictor = _build_sam3(self.config)
        self.sam3_3d_body_model = _build_sam3_3d_body(self.config)

        if self.config.completion.get('enable', False):
            self.pipeline_mask, self.pipeline_rgb, self.depth_model, self.max_occ_len, self.generator = _build_diffusion_vas(self.config)
        else:
            self.pipeline_mask = self.pipeline_rgb = self.depth_model = None
            self.max_occ_len = None
            self.generator = None

        self.batch_size = self.config.sam_3d_body.get('batch_size', 1)
        self.detection_resolution = self.config.completion.get('detection_resolution', [256, 512])
        self.completion_resolution = self.config.completion.get('completion_resolution', [512, 1024])

        print("[Pipeline] All models loaded.")

    def read_frame_at(self, path: str, idx: int):
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame)

    def read_video_metadata(self, path: str):
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        return fps, total

    def init_video_state(self, video_path: str):
        """Initialize SAM-3 inference state for a video. Returns runtime dict."""
        fps, total = self.read_video_metadata(video_path)
        inference_state = self.predictor.init_state(video_path=video_path)
        self.predictor.clear_all_points_in_video(inference_state)
        return {
            'inference_state': inference_state,
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
        """Add an annotation point and return mask overlay."""
        frame = self.read_frame_at(video_path, int(frame_idx))
        if frame is None:
            return None, runtime

        try:
            clicks = runtime['clicks'][frame_idx]
            clicks.append((x, y, point_type))
        except KeyError:
            clicks = [(x, y, point_type)]

        pts = []
        lbs = []
        for (px, py, t) in clicks:
            pts.append([int(px), int(py)])
            lbs.append(1 if t.lower() == "positive" else 0)
        input_point = np.array(pts, dtype=np.int32)
        input_label = np.array(lbs, dtype=np.int32)

        runtime['clicks'][frame_idx] = clicks

        rel_points = [[px / width, py / height] for px, py in input_point]
        points_tensor = torch.tensor(rel_points, dtype=torch.float32)
        points_labels_tensor = torch.tensor(input_label, dtype=torch.int32)

        _, runtime['out_obj_ids'], low_res_masks, video_res_masks = self.predictor.add_new_points_or_box(
            inference_state=runtime['inference_state'],
            frame_idx=frame_idx,
            obj_id=runtime['id'],
            points=points_tensor,
            labels=points_labels_tensor,
        )
        mask_np = (video_res_masks[-1, 0].detach().cpu().numpy() > 0)
        mask = (mask_np > 0).astype(np.uint8) * 255

        painted_image = mask_painter(np.array(frame, dtype=np.uint8), mask, mask_color=4 + runtime['id'])
        runtime['masks'][runtime['id']] = {frame_idx: mask}

        for k, v in runtime['masks'].items():
            if k == runtime['id']:
                continue
            if frame_idx in v:
                painted_image = mask_painter(painted_image, v[frame_idx], mask_color=4 + k)

        return Image.fromarray(painted_image), runtime

    def add_target(self, runtime):
        """Finalize current clicks as a target and advance to next ID."""
        if not runtime['clicks']:
            return runtime
        runtime['objects'][runtime['id']] = runtime['clicks']
        runtime['id'] += 1
        runtime['clicks'] = {}
        return runtime

    def generate_masks(self, runtime, output_dir, progress_cb=None):
        """Run SAM-3 propagation across all frames. Save masks and images."""
        os.makedirs(os.path.join(output_dir, 'images'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'masks'), exist_ok=True)

        # Phase 1: SAM-3 propagation (0% - 70%)
        total_est = runtime.get('total_frames', 100)
        video_segments = {}
        for frame_idx, obj_ids, low_res_masks, video_res_masks, obj_scores, iou_scores in self.predictor.propagate_in_video(
            runtime['inference_state'],
            start_frame_idx=0,
            max_frame_num_to_track=1800,
            reverse=False,
            propagate_preflight=True,
        ):
            video_segments[frame_idx] = {
                out_obj_id: (video_res_masks[i] > 0.0).cpu().numpy()
                for i, out_obj_id in enumerate(runtime['out_obj_ids'])
            }
            if progress_cb:
                progress_cb(0.7 * (frame_idx + 1) / total_est)

        # Phase 2: Save frames (70% - 100%)
        out_h = runtime['inference_state']['video_height']
        out_w = runtime['inference_state']['video_width']
        img_to_video = []

        IMAGE_PATH = os.path.join(output_dir, 'images')
        MASKS_PATH = os.path.join(output_dir, 'masks')

        total_frames = len(video_segments)
        for out_frame_idx in range(total_frames):
            if progress_cb:
                progress_cb(0.7 + 0.3 * out_frame_idx / total_frames)
            img = runtime['inference_state']['images'][out_frame_idx].detach().float().cpu()
            img = (img + 1) / 2
            img = img.clamp(0, 1)
            img = F.interpolate(
                img.unsqueeze(0), size=(out_h, out_w),
                mode="bilinear", align_corners=False,
            ).squeeze(0)
            img = img.permute(1, 2, 0)
            img = (img.numpy() * 255).astype("uint8")
            img_pil = Image.fromarray(img).convert('RGB')
            msk = np.zeros_like(img[:, :, 0])
            for out_obj_id, out_mask in video_segments[out_frame_idx].items():
                mask = (out_mask[0] > 0).astype(np.uint8) * 255
                img = mask_painter(img, mask, mask_color=4 + out_obj_id)
                msk[mask == 255] = out_obj_id
            img_to_video.append(img)

            msk_pil = Image.fromarray(msk).convert('P')
            msk_pil.putpalette(DAVIS_PALETTE)
            img_pil.save(os.path.join(IMAGE_PATH, f"{out_frame_idx:08d}.jpg"))
            msk_pil.save(os.path.join(MASKS_PATH, f"{out_frame_idx:08d}.png"))

        out_video_path = os.path.join(output_dir, f"video_mask_{time.time():.0f}.mp4")
        images_to_mp4(img_to_video, out_video_path, fps=runtime['video_fps'])
        return out_video_path

    def _mask_completion_and_iou_init(self, pred_amodal_masks, pred_res, obj_id, batch_masks, i, W, H, output_dir):
        obj_ratio_dict_obj_id = None
        iou_dict_obj_id = None
        occ_dict_obj_id = None
        idx_dict_obj_id = None
        idx_path_obj_id = None

        pred_amodal_masks_com = [np.array(img.resize((pred_res[1], pred_res[0]))) for img in pred_amodal_masks]
        pred_amodal_masks_com = np.array(pred_amodal_masks_com).astype('uint8')
        pred_amodal_masks_com = (pred_amodal_masks_com.sum(axis=-1) > 600).astype('uint8')
        pred_amodal_masks_com = [keep_largest_component(pamc) for pamc in pred_amodal_masks_com]

        pred_amodal_masks = [np.array(img.resize((W, H))) for img in pred_amodal_masks]
        pred_amodal_masks = np.array(pred_amodal_masks).astype('uint8')
        pred_amodal_masks = (pred_amodal_masks.sum(axis=-1) > 600).astype('uint8')
        pred_amodal_masks = [keep_largest_component(pamc) for pamc in pred_amodal_masks]

        masks = [(np.array(Image.open(bm).convert('P')) == obj_id).astype('uint8') for bm in batch_masks]
        ious = []
        masks_margin_shrink = [bm.copy() for bm in masks]
        mask_H, mask_W = masks_margin_shrink[0].shape
        occlusion_threshold = 0.55

        for bi, (a, b) in enumerate(zip(masks, pred_amodal_masks)):
            zero_mask_cp = np.zeros_like(masks_margin_shrink[bi])
            zero_mask_cp[masks_margin_shrink[bi] == 1] = 255
            mask_binary_cp = zero_mask_cp.astype(np.uint8)
            mask_binary_cp[:int(mask_H * 0.05), :] = 0
            mask_binary_cp[-int(mask_H * 0.05):, :] = 0
            mask_binary_cp[:, :int(mask_W * 0.05)] = 0
            mask_binary_cp[:, -int(mask_W * 0.05):] = 0
            if mask_binary_cp.max() == 0:
                ious.append(occlusion_threshold)
                continue
            area_a = (a > 0).sum()
            area_b = (b > 0).sum()
            if area_a == 0 and area_b == 0:
                ious.append(occlusion_threshold)
            elif area_a > area_b:
                ious.append(occlusion_threshold)
            else:
                inter = np.logical_and(a > 0, b > 0).sum()
                uni = np.logical_or(a > 0, b > 0).sum()
                ious.append(inter / (uni + 1e-6))

            if i == 0 and bi == 0:
                if ious[0] < occlusion_threshold:
                    obj_ratio_dict_obj_id = bbox_from_mask(b)
                else:
                    obj_ratio_dict_obj_id = bbox_from_mask(a)

        for pi, pamc in enumerate(pred_amodal_masks_com):
            if masks[pi].sum() > pred_amodal_masks[pi].sum():
                ious[pi] = occlusion_threshold
                pred_amodal_masks_com[pi] = resize_mask_with_unique_label(masks[pi], pred_res[0], pred_res[1], obj_id)
            elif is_super_long_or_wide(pred_amodal_masks[pi], obj_id):
                ious[pi] = occlusion_threshold
                pred_amodal_masks_com[pi] = resize_mask_with_unique_label(masks[pi], pred_res[0], pred_res[1], obj_id)
            elif is_skinny_mask(pred_amodal_masks[pi]):
                ious[pi] = occlusion_threshold
                pred_amodal_masks_com[pi] = resize_mask_with_unique_label(masks[pi], pred_res[0], pred_res[1], obj_id)

        iou_dict_obj_id = [float(x) for x in ious]
        arr = iou_dict_obj_id[:]
        for isb in range(1, len(arr) - 1):
            if arr[isb] == occlusion_threshold and arr[isb - 1] < occlusion_threshold and arr[isb + 1] < occlusion_threshold:
                arr[isb] = 0.0
        iou_dict_obj_id = arr
        occ_dict_obj_id = [1 if ix >= occlusion_threshold else 0 for ix in iou_dict_obj_id]

        start, end = (idxs := [ix for ix, x in enumerate(iou_dict_obj_id) if x < occlusion_threshold]) and (idxs[0], idxs[-1]) or (None, None)

        if start is not None and end is not None:
            start = max(0, start - 2)
            end = min(len(pred_amodal_masks), end + 2)
            idx_dict_obj_id = (start, end)
            completion_path = ''.join(random.choices('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
            completion_image_path = f'{output_dir}/completion/{completion_path}/images'
            completion_masks_path = f'{output_dir}/completion/{completion_path}/masks'
            os.makedirs(completion_image_path, exist_ok=True)
            os.makedirs(completion_masks_path, exist_ok=True)
            idx_path_obj_id = {'images': completion_image_path, 'masks': completion_masks_path}

        return obj_ratio_dict_obj_id, iou_dict_obj_id, occ_dict_obj_id, idx_dict_obj_id, idx_path_obj_id

    def _mask_completion_and_iou_final(self, pred_amodal_masks, pred_res, obj_id, batch_masks, W, H, iou_dict_obj_id, occ_dict_obj_id, idx_path_obj_id, keep_idx):
        keep_id = [io for io, vo in enumerate(keep_idx) if vo == 1]
        batch_masks_ = [batch_masks[io] for io in keep_id]

        zero_com = np.zeros_like(np.array(pred_amodal_masks[0].resize((pred_res[1], pred_res[0])))[:, :, 0])
        pred_amodal_masks_com = [np.array(img.resize((pred_res[1], pred_res[0]))) for img in pred_amodal_masks]
        pred_amodal_masks_com = np.array(pred_amodal_masks_com).astype('uint8')
        pred_amodal_masks_com = (pred_amodal_masks_com.sum(axis=-1) > 600).astype('uint8')
        pred_amodal_masks_com = [keep_largest_component(pamc) for pamc in pred_amodal_masks_com]

        pred_amodal_masks = [np.array(img.resize((W, H))) for img in pred_amodal_masks]
        pred_amodal_masks = np.array(pred_amodal_masks).astype('uint8')
        pred_amodal_masks = (pred_amodal_masks.sum(axis=-1) > 600).astype('uint8')
        pred_amodal_masks = [keep_largest_component(pamc) for pamc in pred_amodal_masks]

        masks = [(np.array(Image.open(bm).convert('P')) == obj_id).astype('uint8') for bm in batch_masks_]
        ious = []
        masks_margin_shrink = [bm.copy() for bm in masks]
        mask_H, mask_W = masks_margin_shrink[0].shape
        occlusion_threshold = 0.65

        for bi, (a, b) in enumerate(zip(masks, pred_amodal_masks)):
            zero_mask_cp = np.zeros_like(masks_margin_shrink[bi])
            zero_mask_cp[masks_margin_shrink[bi] == 1] = 255
            mask_binary_cp = zero_mask_cp.astype(np.uint8)
            mask_binary_cp[:int(mask_H * 0.05), :] = 0
            mask_binary_cp[-int(mask_H * 0.05):, :] = 0
            mask_binary_cp[:, :int(mask_W * 0.05)] = 0
            mask_binary_cp[:, -int(mask_W * 0.05):] = 0
            if mask_binary_cp.max() == 0:
                ious.append(occlusion_threshold)
                continue
            area_a = (a > 0).sum()
            area_b = (b > 0).sum()
            if area_a == 0 and area_b == 0:
                ious.append(occlusion_threshold)
            elif area_a > area_b:
                ious.append(occlusion_threshold)
            else:
                inter = np.logical_and(a > 0, b > 0).sum()
                uni = np.logical_or(a > 0, b > 0).sum()
                ious.append(inter / (uni + 1e-6))

        for pi, pamc in enumerate(pred_amodal_masks_com):
            if masks[pi].sum() > pred_amodal_masks[pi].sum():
                ious[pi] = occlusion_threshold
                pred_amodal_masks_com[pi] = resize_mask_with_unique_label(masks[pi], pred_res[0], pred_res[1], obj_id)
            elif is_super_long_or_wide(pred_amodal_masks[pi], obj_id):
                ious[pi] = occlusion_threshold
                pred_amodal_masks_com[pi] = resize_mask_with_unique_label(masks[pi], pred_res[0], pred_res[1], obj_id)
            elif is_skinny_mask(pred_amodal_masks[pi]):
                ious[pi] = occlusion_threshold
                pred_amodal_masks_com[pi] = resize_mask_with_unique_label(masks[pi], pred_res[0], pred_res[1], obj_id)

        iou_dict_obj_id_ = [float(x) for x in ious]
        arr = iou_dict_obj_id_[:]
        for isb in range(1, len(arr) - 1):
            if arr[isb] == occlusion_threshold and arr[isb - 1] < occlusion_threshold and arr[isb + 1] < occlusion_threshold:
                arr[isb] = 0.0
        iou_dict_obj_id_ = arr
        occ_dict_obj_id_ = [1 if ix >= occlusion_threshold else 0 for ix in iou_dict_obj_id_]

        completion_masks_path = idx_path_obj_id['masks']
        current_id = 0
        final_pred_amodal_masks_com = []
        for ki, keep_id_val in enumerate(keep_idx):
            if keep_id_val == 0:
                final_pred_amodal_masks_com.append(zero_com)
                continue
            occ_dict_obj_id[ki] = occ_dict_obj_id_[current_id]
            iou_dict_obj_id[ki] = iou_dict_obj_id_[current_id]
            if occ_dict_obj_id_[current_id] == 1:
                current_id += 1
                final_pred_amodal_masks_com.append(zero_com)
                continue
            final_pred_amodal_masks_com.append(pred_amodal_masks_com[current_id])
            mask_idx_ = pred_amodal_masks[current_id].copy()
            mask_idx_[mask_idx_ > 0] = obj_id
            mask_idx_ = Image.fromarray(mask_idx_).convert('P')
            mask_idx_.putpalette(DAVIS_PALETTE)
            mask_idx_.save(os.path.join(completion_masks_path, f"{ki:08d}.png"))
            current_id += 1

        return iou_dict_obj_id, occ_dict_obj_id, final_pred_amodal_masks_com

    def generate_4d(self, runtime, output_dir, progress_cb=None):
        """Run occlusion recovery + 3D mesh recovery. Returns path to rendered video."""
        IMAGE_PATH = os.path.join(output_dir, 'images')
        MASKS_PATH = os.path.join(output_dir, 'masks')

        image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.tiff", "*.webp"]
        images_list = sorted([img for ext in image_extensions for img in glob.glob(os.path.join(IMAGE_PATH, ext))])
        masks_list = sorted([img for ext in image_extensions for img in glob.glob(os.path.join(MASKS_PATH, ext))])

        os.makedirs(f"{output_dir}/rendered_frames", exist_ok=True)
        for obj_id in runtime['out_obj_ids']:
            os.makedirs(f"{output_dir}/mesh_4d_individual/{obj_id}", exist_ok=True)
            os.makedirs(f"{output_dir}/focal_4d_individual/{obj_id}", exist_ok=True)
            os.makedirs(f"{output_dir}/rendered_frames_individual/{obj_id}", exist_ok=True)

        batch_size = runtime['batch_size']
        n = len(images_list)

        pred_res = runtime['detection_resolution']
        pred_res_hi = runtime['completion_resolution']
        w, h = Image.open(images_list[0]).size
        pred_res = pred_res if h < w else pred_res[::-1]
        pred_res_hi = pred_res_hi if h < w else pred_res_hi[::-1]

        modal_pixels_list = []
        if self.pipeline_mask is not None:
            for obj_id in runtime['out_obj_ids']:
                modal_pixels, ori_shape = load_and_transform_masks(output_dir + "/masks", resolution=pred_res, obj_id=obj_id)
                modal_pixels_list.append(modal_pixels)
            rgb_pixels, _, raw_rgb_pixels = load_and_transform_rgbs(output_dir + "/images", resolution=pred_res)
            depth_pixels = rgb_to_depth(rgb_pixels, self.depth_model)

        mhr_shape_scale_dict = {}
        obj_ratio_dict = {}

        print("Running FOV estimator ...")
        input_image = np.array(Image.open(images_list[0])).astype('uint8')
        cam_int = self.sam3_3d_body_model.fov_estimator.get_cam_intrinsics(input_image)

        total_batches = max(1, (n + batch_size - 1) // batch_size)
        batch_idx = 0
        for i in tqdm(range(0, n, batch_size)):
            # Each batch has 4 stages: occlusion(25%), completion(25%), mesh(40%), render(10%)
            batch_base = batch_idx / total_batches
            batch_step = 1.0 / total_batches
            if progress_cb:
                progress_cb(batch_base)
            batch_idx += 1
            batch_images = images_list[i:i + batch_size]
            batch_masks = masks_list[i:i + batch_size]
            W, H = Image.open(batch_masks[0]).size

            idx_dict = {}
            idx_path = {}
            occ_dict = {}
            iou_dict = {}

            if len(modal_pixels_list) > 0:
                print("detect occlusions ...")
                if progress_cb:
                    progress_cb(batch_base + batch_step * 0.05)
                for (modal_pixels, obj_id) in zip(modal_pixels_list, runtime['out_obj_ids']):
                    pred_amodal_masks = self.pipeline_mask(
                        modal_pixels[:, i:i + batch_size, :, :, :],
                        depth_pixels[:, i:i + batch_size, :, :, :],
                        height=pred_res[0], width=pred_res[1],
                        num_frames=modal_pixels[:, i:i + batch_size, :, :, :].shape[1],
                        decode_chunk_size=8, motion_bucket_id=127, fps=8,
                        noise_aug_strength=0.02, min_guidance_scale=1.5, max_guidance_scale=1.5,
                        generator=self.generator,
                    ).frames[0]

                    result = self._mask_completion_and_iou_init(
                        pred_amodal_masks, pred_res, obj_id, batch_masks, i, W, H, output_dir
                    )
                    obj_ratio_dict_obj_id, iou_dict_obj_id, occ_dict_obj_id, idx_dict_obj_id, idx_path_obj_id = result

                    if obj_ratio_dict_obj_id is not None:
                        obj_ratio_dict[obj_id] = obj_ratio_dict_obj_id
                    if iou_dict_obj_id is not None:
                        iou_dict[obj_id] = iou_dict_obj_id
                    if occ_dict_obj_id is not None:
                        occ_dict[obj_id] = occ_dict_obj_id
                    if idx_dict_obj_id is not None:
                        idx_dict[obj_id] = idx_dict_obj_id
                    if idx_path_obj_id is not None:
                        idx_path[obj_id] = idx_path_obj_id

                for obj_id, (start, end) in idx_dict.items():
                    completion_image_path = idx_path[obj_id]['images']
                    modal_pixels_current, ori_shape = load_and_transform_masks(output_dir + "/masks", resolution=pred_res_hi, obj_id=obj_id)
                    rgb_pixels_current, _, raw_rgb_pixels_current = load_and_transform_rgbs(output_dir + "/images", resolution=pred_res_hi)
                    depth_pixels_hi = rgb_to_depth(rgb_pixels_current, self.depth_model)
                    modal_pixels_current = modal_pixels_current[:, i:i + batch_size, :, :, :][:, start:end]
                    rgb_pixels_current = rgb_pixels_current[:, i:i + batch_size, :, :, :][:, start:end]
                    modal_obj_mask = (modal_pixels_current > 0).float()
                    modal_background = 1 - modal_obj_mask
                    rgb_pixels_current = (rgb_pixels_current + 1) / 2
                    modal_rgb_pixels = rgb_pixels_current * modal_obj_mask + modal_background
                    modal_rgb_pixels = modal_rgb_pixels * 2 - 1

                    keep_idx = cap_consecutive_ones_by_iou(occ_dict[obj_id][start:end], iou_dict[obj_id][start:end])
                    mask_idx = torch.tensor(keep_idx, device=modal_rgb_pixels.device).bool()

                    pred_amodal_masks_ = self.pipeline_mask(
                        modal_pixels_current[:, mask_idx],
                        depth_pixels_hi[:, i:i + batch_size, :, :, :][:, start:end][:, mask_idx],
                        height=pred_res_hi[0], width=pred_res_hi[1],
                        num_frames=sum(keep_idx),
                        decode_chunk_size=8, motion_bucket_id=127, fps=8,
                        noise_aug_strength=0.02, min_guidance_scale=1.5, max_guidance_scale=1.5,
                        generator=self.generator,
                    ).frames[0]

                    iou_dict_obj_id, occ_dict_obj_id, pred_amodal_masks_com = self._mask_completion_and_iou_final(
                        pred_amodal_masks_, pred_res_hi, obj_id, batch_masks, W, H,
                        iou_dict[obj_id], occ_dict[obj_id], idx_path[obj_id],
                        [0] * start + keep_idx + [0] * (len(occ_dict[obj_id]) - end),
                    )
                    if iou_dict_obj_id is not None:
                        iou_dict[obj_id] = iou_dict_obj_id
                    if occ_dict_obj_id is not None:
                        occ_dict[obj_id] = occ_dict_obj_id

                    print("content completion by diffusion-vas ...")
                    if progress_cb:
                        progress_cb(batch_base + batch_step * 0.35)
                    keep_idx = cap_consecutive_ones_by_iou(occ_dict[obj_id][start:end], iou_dict[obj_id][start:end])
                    mask_idx = torch.tensor(keep_idx, device=modal_rgb_pixels.device).bool()
                    pred_amodal_masks_current = pred_amodal_masks_com[start:end]
                    pred_amodal_masks_current = [xxx for xxx, mmm in zip(pred_amodal_masks_current, keep_idx) if mmm == 1]
                    modal_mask_union = (modal_pixels_current[:, mask_idx][0, :, 0, :, :].cpu().numpy() > 0).astype('uint8')
                    pred_amodal_masks_current = np.logical_or(pred_amodal_masks_current, modal_mask_union).astype('uint8')
                    pred_amodal_masks_tensor = torch.from_numpy(
                        np.where(pred_amodal_masks_current == 0, -1, 1)
                    ).float().unsqueeze(0).unsqueeze(2).repeat(1, 1, 3, 1, 1)

                    pred_amodal_rgb = self.pipeline_rgb(
                        modal_rgb_pixels[:, mask_idx],
                        pred_amodal_masks_tensor,
                        height=pred_res_hi[0], width=pred_res_hi[1],
                        num_frames=sum(keep_idx),
                        decode_chunk_size=8, motion_bucket_id=127, fps=8,
                        noise_aug_strength=0.02, min_guidance_scale=1.5, max_guidance_scale=1.5,
                        generator=self.generator,
                    ).frames[0]

                    pred_i = 0
                    save_i = start - 1
                    for keep_i, occ_i in zip(keep_idx, occ_dict[obj_id][start:end]):
                        save_i += 1
                        if occ_i == 1:
                            if keep_i == 1:
                                pred_i += 1
                            continue
                        if keep_i == 1:
                            rgb_i = np.array(pred_amodal_rgb[pred_i]).astype('uint8')
                            rgb_i = cv2.resize(rgb_i, (ori_shape[1], ori_shape[0]), interpolation=cv2.INTER_LINEAR)
                            cv2.imwrite(os.path.join(completion_image_path, f"{save_i:08d}.jpg"), cv2.cvtColor(rgb_i, cv2.COLOR_RGB2BGR))
                            pred_i += 1
            else:
                for obj_id in runtime['out_obj_ids']:
                    occ_dict[obj_id] = [1] * len(batch_masks)

            if progress_cb:
                progress_cb(batch_base + batch_step * 0.55)
            mask_outputs, id_batch, empty_frame_list = process_image_with_mask(
                self.sam3_3d_body_model, batch_images, batch_masks,
                idx_path, idx_dict, mhr_shape_scale_dict, occ_dict,
                cam_int=cam_int, iou_dict=iou_dict, predictor=self.predictor,
            )
            if progress_cb:
                progress_cb(batch_base + batch_step * 0.90)

            num_empty_ids = 0
            for frame_id in range(len(batch_images)):
                image_path = batch_images[frame_id]
                if frame_id in empty_frame_list:
                    mask_output = None
                    id_current = None
                    num_empty_ids += 1
                else:
                    mask_output = mask_outputs[frame_id - num_empty_ids]
                    id_current = id_batch[frame_id - num_empty_ids]
                img = cv2.imread(image_path)
                rend_img = visualize_sample_together(img, mask_output, self.sam3_3d_body_model.faces, id_current)
                cv2.imwrite(
                    f"{output_dir}/rendered_frames/{os.path.basename(image_path)[:-4]}.jpg",
                    rend_img.astype(np.uint8),
                )
                rend_img_list = visualize_sample(img, mask_output, self.sam3_3d_body_model.faces, id_current)
                for ri, rend_img in enumerate(rend_img_list):
                    cv2.imwrite(
                        f"{output_dir}/rendered_frames_individual/{ri + 1}/{os.path.basename(image_path)[:-4]}_{ri + 1}.jpg",
                        rend_img.astype(np.uint8),
                    )
                save_mesh_results(
                    outputs=mask_output,
                    faces=self.sam3_3d_body_model.faces,
                    save_dir=f"{output_dir}/mesh_4d_individual",
                    focal_dir=f"{output_dir}/focal_4d_individual",
                    image_path=image_path,
                    id_current=id_current,
                )

        out_4d_path = os.path.join(output_dir, f"4d_{time.time():.0f}.mp4")
        jpg_folder_to_mp4(f"{output_dir}/rendered_frames", out_4d_path, fps=runtime['video_fps'])
        return out_4d_path

    def process_video_auto(self, video_path: str, output_dir: str = None):
        """
        End-to-end: video in -> results out.
        Auto-detects humans, runs segmentation, runs 4D reconstruction.
        Returns dict with paths to outputs.
        """
        if output_dir is None:
            output_dir = os.path.join(self.config.runtime['output_dir'], _gen_id())
        os.makedirs(output_dir, exist_ok=True)

        # Auto-detect humans
        image = self.read_frame_at(video_path, 0)
        width, height = image.size
        starting_frame_idx = 0
        for idx in range(10, 100):
            frame = np.array(self.read_frame_at(video_path, idx))
            outputs = self.sam3_3d_body_model.process_one_image(frame, bbox_thr=0.6)
            if len(outputs) > 0:
                starting_frame_idx = idx
                break

        runtime = self.init_video_state(video_path)

        for obj_id, output in enumerate(outputs):
            xmin, ymin, xmax, ymax = output['bbox']
            rel_box = np.array([[xmin / width, ymin / height, xmax / width, ymax / height]], dtype=np.float32)
            _, runtime['out_obj_ids'], _, _ = self.predictor.add_new_points_or_box(
                inference_state=runtime['inference_state'],
                frame_idx=starting_frame_idx,
                obj_id=obj_id + 1,
                box=rel_box,
            )

        mask_video = self.generate_masks(runtime, output_dir)

        with torch.autocast("cuda", enabled=False):
            result_video = self.generate_4d(runtime, output_dir)

        return {
            'mask_video': mask_video,
            'result_video': result_video,
            'output_dir': output_dir,
            'mesh_dir': f"{output_dir}/mesh_4d_individual",
        }