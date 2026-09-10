"""
Temporal Multimodal Alignment Engine.
Synchronizes visual keyframes with spoken audio transcript intervals [T_start, T_end].
Ensures each scene encapsulates what was VISIBLE on screen alongside what was SPOKEN.
"""

from typing import List, Dict, Any, Tuple
from pipelines.video_pipeline.schema import (
    KeyframeInfo,
    AudioSegment,
    VisualContent,
    AlignedScene,
    VisualType,
)
from pipelines.text_pipeline.extractors.ioc_extractor import IOCExtractor


def format_timestamp(seconds: float) -> str:
    """Formats floating-point seconds into MM:SS format."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


class TemporalMultimodalAligner:
    """Aligns video keyframes and audio transcript into temporally synchronized scene units."""

    def __init__(self):
        self.ioc_extractor = IOCExtractor()

    def align(
        self,
        keyframes: List[KeyframeInfo],
        visual_contents: List[VisualContent],
        audio_segments: List[AudioSegment],
        video_duration: float
    ) -> List[AlignedScene]:
        """
        Builds aligned multimodal scenes.

        Args:
            keyframes: List of unique keyframe metadata objects.
            visual_contents: Matching list of VisualContent objects.
            audio_segments: Timestamped speech segments from audio track.
            video_duration: Total video length in seconds.

        Returns:
            List of AlignedScene objects.
        """
        if not keyframes:
            # If no keyframes extracted, create a single scene wrapping the entire audio
            full_audio = " ".join(s.text for s in audio_segments)
            dummy_kf = KeyframeInfo(
                frame_index=0,
                timestamp_seconds=0.0,
                image_path="",
                perceptual_hash="none",
                visual_type=VisualType.OTHER
            )
            dummy_visual = VisualContent(
                visual_type=VisualType.OTHER,
                raw_ocr_text="",
                structured_content="*(No visual keyframes captured)*",
                visual_narrative="Audio briefing"
            )
            return [AlignedScene(
                scene_id=1,
                start_seconds=0.0,
                end_seconds=round(video_duration, 2),
                timestamp_display=f"00:00 - {format_timestamp(video_duration)}",
                keyframe=dummy_kf,
                visual=dummy_visual,
                spoken_transcript=full_audio,
                scene_iocs=[]
            )]

        aligned_scenes: List[AlignedScene] = []
        n_frames = len(keyframes)

        for idx, (kf, visual) in enumerate(zip(keyframes, visual_contents), start=1):
            # Calculate scene boundaries
            if idx == 1:
                start_sec = 0.0
            else:
                prev_kf = keyframes[idx - 2]
                start_sec = (prev_kf.timestamp_seconds + kf.timestamp_seconds) / 2.0

            if idx == n_frames:
                end_sec = video_duration
            else:
                next_kf = keyframes[idx]
                end_sec = (kf.timestamp_seconds + next_kf.timestamp_seconds) / 2.0

            start_sec = round(max(0.0, start_sec), 2)
            end_sec = round(max(start_sec, min(video_duration, end_sec)), 2)

            # Match overlapping audio segments within this time interval
            spoken_words: List[str] = []
            for seg in audio_segments:
                # Check for temporal overlap
                if (seg.end_seconds >= start_sec) and (seg.start_seconds <= end_sec):
                    spoken_words.append(seg.text.strip())

            spoken_transcript = " ".join(spoken_words).strip()
            time_display = f"{format_timestamp(start_sec)} - {format_timestamp(end_sec)}"

            # Aggregate IOCs from both visual OCR and spoken text
            combined_text = f"{visual.raw_ocr_text} {spoken_transcript}"
            scene_iocs_obj = self.ioc_extractor.extract_iocs(combined_text)
            scene_iocs: List[str] = sorted(list(set(
                scene_iocs_obj.cves +
                scene_iocs_obj.ipv4_addresses +
                scene_iocs_obj.sha256_hashes +
                scene_iocs_obj.domains
            )))

            aligned_scenes.append(AlignedScene(
                scene_id=idx,
                start_seconds=start_sec,
                end_seconds=end_sec,
                timestamp_display=time_display,
                keyframe=kf,
                visual=visual,
                spoken_transcript=spoken_transcript or "*(Silence or ambient audio)*",
                scene_iocs=scene_iocs
            ))

        return aligned_scenes
