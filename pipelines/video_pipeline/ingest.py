"""
Master Multimodal Video Ingestion & Intelligence Transformation Pipeline.
Processes technical cybersecurity videos (threat briefings, vulnerability demos, terminal captures)
into an aligned, structured, context-rich JSON payload and Markdown summary.
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import cv2
from dotenv import load_dotenv

load_dotenv()

from pipelines.video_pipeline.schema import (
    VideoMetadata,
    ExtractedVideoContext,
    ExtractedVideoIOCs,
    AlignedScene,
    VideoEnrichedGroundingContext,
    VideoMintoPyramid,
    VisualType,
)
from pipelines.video_pipeline.extractors.audio_extractor import VideoAudioExtractor
from pipelines.video_pipeline.extractors.scene_detector import VideoSceneDetector
from pipelines.video_pipeline.extractors.visual_classifier import KeyframeVisualClassifier
from pipelines.video_pipeline.extractors.specialized_extractors import SpecializedContentExtractor
from pipelines.video_pipeline.extractors.temporal_aligner import TemporalMultimodalAligner
from pipelines.text_pipeline.interpreters.interpreter import GroqInterpreter
from pipelines.text_pipeline.extractors.ioc_extractor import IOCExtractor


def calculate_sha256(file_path: str) -> str:
    """Computes SHA-256 checksum of an input file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


class VideoIngestionPipeline:
    """Unified multimodal video ingestion, scene triage, and temporal alignment pipeline."""

    SUPPORTED_EXTENSIONS = {
        ".mp4": "mp4",
        ".mkv": "mkv",
        ".avi": "avi",
        ".mov": "mov",
        ".webm": "webm",
        ".flv": "flv",
    }

    def __init__(self, output_dir: str = "ingestion_outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.audio_extractor = VideoAudioExtractor()
        self.scene_detector = VideoSceneDetector()
        self.visual_classifier = KeyframeVisualClassifier()
        self.specialized_extractor = SpecializedContentExtractor()
        self.temporal_aligner = TemporalMultimodalAligner()
        self.ioc_extractor = IOCExtractor()
        self.interpreter = GroqInterpreter()

    def process_video(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
        save_outputs: bool = True
    ) -> ExtractedVideoContext:
        """
        Ingests and transforms a video into an aligned ExtractedVideoContext.

        Args:
            video_path: Path to target video file.
            output_dir: Custom destination directory.
            save_outputs: Whether to write markdown and json files to disk.

        Returns:
            ExtractedVideoContext: Complete Pydantic contract object.
        """
        path = Path(video_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Video file does not exist: {video_path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported video format '{ext}'. Supported formats: {list(self.SUPPORTED_EXTENSIONS.keys())}"
            )

        target_dir = Path(output_dir) if output_dir else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = path.stem

        # 1. Video Technical Telemetry
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open video stream: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = round(total_frames / fps, 2) if fps > 0 else 0.0
        cap.release()

        file_size = path.stat().st_size
        checksum = calculate_sha256(str(path))

        # 2. Audio Extraction & Whisper Transcription with Timestamps
        audio_wav = self.audio_extractor.extract_audio(str(path))
        has_audio = audio_wav is not None
        full_transcript = ""
        audio_segments = []

        if has_audio:
            try:
                full_transcript, audio_segments = self.audio_extractor.transcribe(audio_wav)
            finally:
                if os.path.exists(audio_wav):
                    try:
                        os.unlink(audio_wav)
                    except OSError:
                        pass

        metadata = VideoMetadata(
            file_name=path.name,
            file_path=str(path),
            file_size_bytes=file_size,
            sha256_checksum=checksum,
            duration_seconds=duration,
            fps=round(fps, 2),
            resolution=f"{width}x{height}",
            total_frames=total_frames,
            has_audio=has_audio
        )

        # 3. Scene Cut Detection & Settled Keyframe Extraction with pHash Deduplication
        keyframes = self.scene_detector.extract_keyframes(str(path), output_dir=str(target_dir))

        # 4. Multi-Modal Visual Classification & Triage + Specialized Extraction
        visual_contents = []
        for kf in keyframes:
            # Classify into SLIDE, TERMINAL, DIAGRAM, or OTHER
            v_type = self.visual_classifier.classify(kf.image_path)
            kf.visual_type = v_type

            # Specialized extraction per category
            content = self.specialized_extractor.process_keyframe(kf.image_path, v_type)
            visual_contents.append(content)

        # 5. Temporal Multi-Modal Alignment (Visual Keyframes + Audio Timestamps)
        aligned_scenes = self.temporal_aligner.align(
            keyframes=keyframes,
            visual_contents=visual_contents,
            audio_segments=audio_segments,
            video_duration=duration
        )

        # 6. Global IOC Extraction & Aggregation
        all_text_corpus = full_transcript + " " + " ".join(v.raw_ocr_text for v in visual_contents)
        iocs_raw = self.ioc_extractor.extract_iocs(all_text_corpus)
        video_iocs = ExtractedVideoIOCs(
            cves=iocs_raw.cves,
            ipv4_addresses=iocs_raw.ipv4_addresses,
            ipv6_addresses=iocs_raw.ipv6_addresses,
            sha256_hashes=iocs_raw.sha256_hashes,
            md5_hashes=iocs_raw.md5_hashes,
            domains=iocs_raw.domains,
            urls=iocs_raw.urls,
            mitre_attack_ids=iocs_raw.mitre_attack_ids,
            total_iocs_found=iocs_raw.total_iocs_found
        )

        # 7. Generate Aligned Multimodal Markdown Document
        clean_markdown = self._generate_markdown_report(metadata, aligned_scenes, video_iocs, full_transcript)

        # 8. Assemble Context Bundle
        video_context = ExtractedVideoContext(
            metadata=metadata,
            scenes=aligned_scenes,
            full_audio_transcript=full_transcript,
            iocs=video_iocs,
            clean_markdown=clean_markdown
        )

        # 9. Save Dual-Payload Output
        if save_outputs:
            md_out = target_dir / f"{stem}_video_context.md"
            json_out = target_dir / f"{stem}_video_context.json"

            with open(md_out, "w", encoding="utf-8") as f:
                f.write(clean_markdown)

            with open(json_out, "w", encoding="utf-8") as f:
                json.dump(video_context.to_dict(), f, indent=2, ensure_ascii=False)

        return video_context

    def process_and_enrich(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
        save_outputs: bool = True
    ) -> Tuple[ExtractedVideoContext, VideoEnrichedGroundingContext]:
        """
        Runs both Video Ingestion and Semantic Grounding Enrichment via Groq.
        Cleans up temporary intermediate Phase 1 files upon completion.
        """
        target_dir = Path(output_dir) if output_dir else self.output_dir
        source_context = self.process_video(video_path, output_dir=str(target_dir), save_outputs=save_outputs)

        enriched_context = self._enrich_video_context(source_context)

        if save_outputs:
            stem = Path(video_path).stem
            md_path = target_dir / f"{stem}_video_enriched_context.md"
            json_path = target_dir / f"{stem}_video_enriched_context.json"

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(enriched_context.to_markdown())

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(enriched_context.to_dict(), f, indent=2, ensure_ascii=False)

            # Clean up intermediate Phase 1 files
            for temp_file in [target_dir / f"{stem}_video_context.md", target_dir / f"{stem}_video_context.json"]:
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass

        return source_context, enriched_context

    def _enrich_video_context(self, context: ExtractedVideoContext) -> VideoEnrichedGroundingContext:
        """Invokes Groq LLM to produce VideoEnrichedGroundingContext."""
        prompt = (
            f"Analyze the following multimodal video intelligence briefing:\n\n"
            f"VIDEO FILE: {context.metadata.file_name} ({context.metadata.duration_seconds}s)\n"
            f"IDENTIFIED IOCs: CVEs: {context.iocs.cves}, IPs: {context.iocs.ipv4_addresses}, Hashes: {context.iocs.sha256_hashes}\n\n"
            f"FULL MULTIMODAL TRANSCRIPT & SCENES:\n{context.clean_markdown}\n\n"
            f"Respond with a valid JSON object matching:\n"
            f"{{\n"
            f'  "title": "Title of the video briefing",\n'
            f'  "executive_overview": "Comprehensive executive summary of the video",\n'
            f'  "minto_pyramid": {{\n'
            f'    "situation": "Operational context",\n'
            f'    "complication": "Threat or exploit demonstrated",\n'
            f'    "solution": "Mitigation steps shown",\n'
            f'    "business_impact_and_risk": "Impact on enterprise systems"\n'
            f'  }},\n'
            f'  "technical_root_cause": "Technical mechanics explained in the video",\n'
            f'  "timeline_of_events": ["Event 1", "Event 2"],\n'
            f'  "locked_numerical_facts": ["Exact stat 1", "Duration: {context.metadata.duration_seconds}s"],\n'
            f'  "actionable_mitigations": ["Mitigation 1", "Mitigation 2"]\n'
            f"}}"
        )

        try:
            if self.interpreter.llm:
                from langchain_core.messages import SystemMessage, HumanMessage
                resp = self.interpreter.llm.invoke([
                    SystemMessage(content="You are a Lead Cyber Intelligence Officer. Output ONLY valid JSON."),
                    HumanMessage(content=prompt)
                ])
                parsed = self.interpreter._extract_json_from_response(resp.content)
                parsed["interpreted_by_model"] = self.interpreter.model_name
                if "indicators_of_compromise" not in parsed or not parsed["indicators_of_compromise"]:
                    parsed["indicators_of_compromise"] = context.iocs.model_dump()
                return VideoEnrichedGroundingContext.model_validate(parsed)
        except Exception:
            pass

        # Heuristic fallback if LLM offline
        cves_str = ", ".join(context.iocs.cves) if context.iocs.cves else "Cyber Threats"
        return VideoEnrichedGroundingContext(
            title=f"Video Intelligence Briefing: {cves_str} ({context.metadata.file_name})",
            executive_overview=f"Multimodal intelligence analysis of {context.metadata.file_name} spanning {context.metadata.duration_seconds} seconds across {len(context.scenes)} scenes.",
            minto_pyramid=VideoMintoPyramid(
                situation="Enterprise infrastructure monitored during security briefing.",
                complication=f"Vulnerability demonstration involving {cves_str}.",
                solution="Apply patches and block identified indicators of compromise.",
                business_impact_and_risk="Risk of lateral movement and operational downtime."
            ),
            technical_root_cause=f"Exploitation of vulnerabilities demonstrated in video session.",
            timeline_of_events=[f"Scene {s.scene_id} [{s.timestamp_display}]: {s.visual.visual_narrative}" for s in context.scenes[:5]],
            locked_numerical_facts=[f"Video duration: {context.metadata.duration_seconds} seconds", f"Detected {len(context.scenes)} distinct visual scenes"],
            actionable_mitigations=["Deploy vendor security updates", "Monitor perimeter logs for identified C2 IPs"],
            indicators_of_compromise=context.iocs,
            interpreted_by_model="heuristic-video-anchor"
        )

    def _generate_markdown_report(
        self,
        meta: VideoMetadata,
        scenes: List[AlignedScene],
        iocs: ExtractedVideoIOCs,
        full_transcript: str
    ) -> str:
        """Constructs an authoritative, chronological multimodal Markdown intelligence report."""
        md = [
            f"# 🎥 Multimodal Video Intelligence: {meta.file_name}",
            f"\n*Duration: {meta.duration_seconds}s | Resolution: {meta.resolution} @ {meta.fps} FPS | SHA256: `{meta.sha256_checksum[:16]}...`*\n",
            "## 1. Technical Telemetry & Extracted Indicators",
            f"- **Total Visual Scenes:** {len(scenes)}",
            f"- **Extracted CVEs:** {', '.join(iocs.cves) if iocs.cves else 'None detected'}",
            f"- **IPv4 Addresses:** {', '.join(iocs.ipv4_addresses) if iocs.ipv4_addresses else 'None detected'}",
            f"- **SHA256 Signatures:** {', '.join(iocs.sha256_hashes) if iocs.sha256_hashes else 'None detected'}",
            f"- **Malicious Domains / URLs:** {', '.join(iocs.domains + iocs.urls) if (iocs.domains or iocs.urls) else 'None detected'}\n",
            "## 2. Temporally Aligned Multimodal Scene Timeline\n"
        ]

        for s in scenes:
            md.append(f"### ⏱️ Scene {s.scene_id} [{s.timestamp_display}] - Visual: `{s.visual.visual_type.value}`")
            md.append(f"**Spoken Narration:** \"{s.spoken_transcript}\"\n")
            md.append(s.visual.structured_content + "\n")
            if s.scene_iocs:
                md.append(f"📌 **Scene Indicators:** `{', '.join(s.scene_iocs)}`\n")
            md.append("---")

        if full_transcript:
            md.append("\n## 3. Full Continuous Audio Transcript\n")
            md.append(f"> {full_transcript}\n")

        return "\n".join(md)


def main():
    """Command-line interface for the multimodal video pipeline."""
    parser = argparse.ArgumentParser(description="Multimodal Video Ingestion & Intelligence Pipeline")
    parser.add_argument("--input", "-i", required=True, help="Path to video file (.mp4, .mkv, .avi, etc.)")
    parser.add_argument("--output-dir", "-o", default="ingestion_outputs", help="Output directory")
    parser.add_argument("--enrich", "-e", action="store_true", help="Run semantic grounding enrichment via Groq")
    parser.add_argument("--print-summary", "-s", action="store_true", help="Print summary to stdout")

    args = parser.parse_args()
    pipeline = VideoIngestionPipeline(output_dir=args.output_dir)

    target = Path(args.input)
    if not target.exists():
        print(f"Error: Video file '{args.input}' does not exist.", file=sys.stderr)
        sys.exit(1)

    stem = target.stem
    print(f"[*] Processing video: {args.input} (Enrichment: {'ENABLED' if args.enrich else 'DISABLED'})...")

    if args.enrich:
        ctx, enriched = pipeline.process_and_enrich(str(target), output_dir=args.output_dir, save_outputs=True)
        print(f"    [+] Saved enriched Markdown:   {args.output_dir}/{stem}_video_enriched_context.md")
        print(f"    [+] Saved enriched JSON:       {args.output_dir}/{stem}_video_enriched_context.json")
        print(f"    [i] Cleaned up temporary Phase 1 intermediate files.")
    else:
        ctx = pipeline.process_video(str(target), output_dir=args.output_dir, save_outputs=True)
        enriched = None
        print(f"    [+] Saved aligned Markdown:    {args.output_dir}/{stem}_video_context.md")
        print(f"    [+] Saved aligned JSON:        {args.output_dir}/{stem}_video_context.json")

    if args.print_summary:
        print("\n" + "=" * 65)
        print(f"VIDEO INGESTION SUMMARY: {ctx.metadata.file_name}")
        print("=" * 65)
        print(f"Duration: {ctx.metadata.duration_seconds}s | Resolution: {ctx.metadata.resolution} | Scenes: {len(ctx.scenes)}")
        print(f"CVEs: {ctx.iocs.cves}")
        print(f"IPs: {ctx.iocs.ipv4_addresses}")
        print(f"Hashes: {ctx.iocs.sha256_hashes}")
        if enriched:
            print("\n--- ENRICHED GROUNDING ANCHOR ---")
            print(f"Title: {enriched.title}")
            print(f"Minto Situation: {enriched.minto_pyramid.situation}")
            print(f"Minto Solution:  {enriched.minto_pyramid.solution}")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
