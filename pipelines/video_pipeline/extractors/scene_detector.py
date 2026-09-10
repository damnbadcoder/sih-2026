"""
Intelligent Keyframe Extraction & Perceptual Hash Deduplication.
Uses PySceneDetect with ContentDetector (threshold ~27.0) to detect scene transitions,
samples settled keyframes, and deduplicates redundant slides/terminal frames using perceptual hashing.
"""

import os
from pathlib import Path
from typing import List, Tuple, Optional
import cv2
from PIL import Image
import imagehash

try:
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector
    SCENEDETECT_AVAILABLE = True
except ImportError:
    SCENEDETECT_AVAILABLE = False

from pipelines.video_pipeline.schema import KeyframeInfo, VisualType


class VideoSceneDetector:
    """Detects scene cuts, extracts settled keyframes, and deduplicates static frames using pHash."""

    def __init__(
        self,
        content_threshold: float = 27.0,
        hamming_distance_threshold: int = 7,
        min_scene_len_seconds: float = 1.5
    ):
        self.content_threshold = content_threshold
        self.hamming_distance_threshold = hamming_distance_threshold
        self.min_scene_len_seconds = min_scene_len_seconds

    def extract_keyframes(
        self,
        video_path: str,
        output_dir: str
    ) -> List[KeyframeInfo]:
        """
        Detects scene transitions, extracts settled keyframes, and deduplicates visually similar frames.

        Args:
            video_path: Path to video file.
            output_dir: Directory to save deduplicated keyframe images.

        Returns:
            List of KeyframeInfo objects for unique, settled keyframes.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        keyframe_dir = Path(output_dir) / "keyframes"
        keyframe_dir.mkdir(parents=True, exist_ok=True)

        # 1. Detect Scene Cut Intervals [(start_time, end_time), ...]
        scene_cuts = self._detect_scenes(video_path)

        # 2. Open Video Capture to sample settled keyframe near end of each scene
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video with OpenCV: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_seconds = total_frames / fps if fps > 0 else 0

        # If no cuts were detected (e.g. single continuous slide or terminal recording),
        # create fallback segment checkpoints
        if not scene_cuts:
            interval = 10.0  # every 10s if completely static
            num_points = max(1, int(duration_seconds // interval))
            scene_cuts = [
                (i * interval, min(duration_seconds, (i + 1) * interval))
                for i in range(num_points)
            ]

        unique_keyframes: List[KeyframeInfo] = []
        seen_hashes: List[Tuple[imagehash.ImageHash, str]] = []
        frame_counter = 1

        for start_sec, end_sec in scene_cuts:
            # Sample near settled state (80% into the scene duration to allow transitions/rendering to settle)
            scene_duration = end_sec - start_sec
            if scene_duration < self.min_scene_len_seconds and unique_keyframes:
                continue

            sample_sec = start_sec + (scene_duration * 0.8)
            target_frame_num = int(sample_sec * fps)
            target_frame_num = min(target_frame_num, total_frames - 1)

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_num)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # Convert BGR to RGB for PIL & perceptual hashing
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)

            # Compute Perceptual Hash (pHash)
            curr_hash = imagehash.phash(pil_image)

            # Check Hamming distance against previously saved keyframes
            is_duplicate = False
            for prev_hash, _ in seen_hashes:
                if (curr_hash - prev_hash) <= self.hamming_distance_threshold:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            # Save unique keyframe to disk
            img_filename = f"keyframe_{frame_counter:03d}_{int(sample_sec)}s.png"
            img_path = keyframe_dir / img_filename
            cv2.imwrite(str(img_path), frame)

            seen_hashes.append((curr_hash, str(img_path)))

            unique_keyframes.append(KeyframeInfo(
                frame_index=target_frame_num,
                timestamp_seconds=round(sample_sec, 2),
                image_path=str(img_path),
                perceptual_hash=str(curr_hash),
                visual_type=VisualType.OTHER
            ))
            frame_counter += 1

        cap.release()
        return unique_keyframes

    def _detect_scenes(self, video_path: str) -> List[Tuple[float, float]]:
        """Uses PySceneDetect ContentDetector to locate cuts."""
        if not SCENEDETECT_AVAILABLE:
            return self._fallback_scene_detection(video_path)

        try:
            video = open_video(video_path)
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=self.content_threshold))
            scene_manager.detect_scenes(video)
            scene_list = scene_manager.get_scene_list()

            cuts: List[Tuple[float, float]] = []
            for scene in scene_list:
                start_sec = getattr(scene[0], "seconds", None)
                if start_sec is None:
                    start_sec = scene[0].get_seconds()
                end_sec = getattr(scene[1], "seconds", None)
                if end_sec is None:
                    end_sec = scene[1].get_seconds()
                cuts.append((float(start_sec), float(end_sec)))
            return cuts
        except Exception:
            return self._fallback_scene_detection(video_path)

    def _fallback_scene_detection(self, video_path: str) -> List[Tuple[float, float]]:
        """Adaptive histogram difference fallback using OpenCV."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        cuts: List[Tuple[float, float]] = []
        prev_hist = None
        last_cut_sec = 0.0

        step = max(1, int(fps * 0.5))  # evaluate every 0.5s
        for fno in range(0, total_frames, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

            curr_sec = fno / fps
            if prev_hist is not None:
                diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                # Significant visual shift
                if diff < 0.65 and (curr_sec - last_cut_sec) >= self.min_scene_len_seconds:
                    cuts.append((last_cut_sec, curr_sec))
                    last_cut_sec = curr_sec

            prev_hist = hist

        if duration > last_cut_sec:
            cuts.append((last_cut_sec, duration))

        cap.release()
        return cuts
