"""
Unit and Integration Tests for the Multimodal Video Ingestion & Intelligence Pipeline.
"""

import unittest
from pathlib import Path
from pipelines.video_pipeline.ingest import VideoIngestionPipeline
from pipelines.video_pipeline.schema import ExtractedVideoContext, VisualType


class TestVideoIngestionPipeline(unittest.TestCase):

    def setUp(self):
        self.tests_dir = Path(__file__).parent.resolve()
        self.output_dir = self.tests_dir / "test_outputs"
        self.samples_dir = self.tests_dir / "samples"
        self.pipeline = VideoIngestionPipeline(output_dir=str(self.output_dir))
        self.video_file = self.samples_dir / "sample_threat_briefing.mp4"

    def test_video_metadata_and_scene_detection(self):
        """Verifies technical telemetry, scene cuts, keyframe deduplication, and OCR."""
        self.assertTrue(self.video_file.exists(), "Sample video file must exist")

        context: ExtractedVideoContext = self.pipeline.process_video(
            str(self.video_file),
            output_dir=str(self.output_dir),
            save_outputs=True
        )

        # 1. Assert Metadata
        self.assertEqual(context.metadata.file_name, "sample_threat_briefing.mp4")
        self.assertAlmostEqual(context.metadata.duration_seconds, 6.0, delta=1.0)
        self.assertEqual(context.metadata.resolution, "1280x720")
        self.assertTrue(context.metadata.has_audio)

        # 2. Assert Scene Cuts & Keyframes
        self.assertGreaterEqual(len(context.scenes), 1)
        
        # Check visual types extracted
        scene_types = [s.visual.visual_type for s in context.scenes]
        self.assertTrue(
            any(t in (VisualType.SLIDE, VisualType.TERMINAL) for t in scene_types),
            f"Expected SLIDE or TERMINAL in scene types, got {scene_types}"
        )

        # 3. Assert IOC Extraction from video keyframe text
        self.assertIn("CVE-2024-38077", context.iocs.cves)
        self.assertIn("198.51.100.42", context.iocs.ipv4_addresses)
        self.assertIn("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", context.iocs.sha256_hashes)

        # 4. Assert Temporal Multimodal Alignment
        for scene in context.scenes:
            self.assertGreaterEqual(scene.end_seconds, scene.start_seconds)
            self.assertTrue(len(scene.timestamp_display) > 0)
            self.assertIsNotNone(scene.visual.structured_content)

        # 5. Assert File Outputs
        md_file = self.output_dir / "sample_threat_briefing_video_context.md"
        json_file = self.output_dir / "sample_threat_briefing_video_context.json"
        self.assertTrue(md_file.exists())
        self.assertTrue(json_file.exists())

    def test_video_enrichment_and_intermediate_cleanup(self):
        """Verifies Groq semantic enrichment and automatic deletion of intermediate files."""
        src, enriched = self.pipeline.process_and_enrich(
            str(self.video_file),
            output_dir=str(self.output_dir),
            save_outputs=True
        )

        self.assertIsNotNone(enriched)
        self.assertTrue(len(enriched.title) > 0)
        self.assertTrue(len(enriched.minto_pyramid.situation) > 0)
        self.assertTrue(len(enriched.minto_pyramid.solution) > 0)

        # Verify Markdown rendering
        md_report = enriched.to_markdown()
        self.assertIn("## 1. Executive Narrative", md_report)
        self.assertIn("## 2. Minto Pyramid Briefing Structure", md_report)

        # Verify intermediate files were deleted and final enriched files exist
        intermediate_md = self.output_dir / "sample_threat_briefing_video_context.md"
        intermediate_json = self.output_dir / "sample_threat_briefing_video_context.json"
        final_enriched_md = self.output_dir / "sample_threat_briefing_video_enriched_context.md"
        final_enriched_json = self.output_dir / "sample_threat_briefing_video_enriched_context.json"

        self.assertFalse(intermediate_md.exists(), "Intermediate video markdown should be deleted")
        self.assertFalse(intermediate_json.exists(), "Intermediate video json should be deleted")
        self.assertTrue(final_enriched_md.exists(), "Final video enriched markdown must exist")
        self.assertTrue(final_enriched_json.exists(), "Final video enriched json must exist")

    def test_multiscene_apt29_complex_video(self):
        """Verifies processing of 4-scene video featuring Slide, Diagram, Terminal, and audio speech."""
        apt29_file = self.samples_dir / "sample_apt29_investigation.mp4"
        self.assertTrue(apt29_file.exists(), "APT29 sample video must exist")

        context: ExtractedVideoContext = self.pipeline.process_video(
            str(apt29_file),
            output_dir=str(self.output_dir),
            save_outputs=True
        )

        # 1. Metadata Verification
        self.assertEqual(context.metadata.file_name, "sample_apt29_investigation.mp4")
        self.assertAlmostEqual(context.metadata.duration_seconds, 16.0, delta=1.0)
        self.assertEqual(context.metadata.resolution, "1280x720")
        self.assertTrue(context.metadata.has_audio)

        # 2. Scene Triage & Classification (Slide, Diagram, Terminal)
        self.assertEqual(len(context.scenes), 4)
        scene_types = [s.visual.visual_type for s in context.scenes]
        self.assertIn(VisualType.SLIDE, scene_types)
        self.assertIn(VisualType.DIAGRAM, scene_types)
        self.assertIn(VisualType.TERMINAL, scene_types)

        # 3. Specialized Extractor Outputs
        diagram_scenes = [s for s in context.scenes if s.visual.visual_type == VisualType.DIAGRAM]
        self.assertTrue(len(diagram_scenes) > 0)
        self.assertIsNotNone(diagram_scenes[0].visual.mermaid_diagram)
        self.assertIn("```mermaid", diagram_scenes[0].visual.mermaid_diagram)

        terminal_scenes = [s for s in context.scenes if s.visual.visual_type == VisualType.TERMINAL]
        self.assertTrue(len(terminal_scenes) > 0)
        self.assertIsNotNone(terminal_scenes[0].visual.code_snippet)

        # 4. Indicators of Compromise
        self.assertIn("CVE-2023-38831", context.iocs.cves)
        self.assertIn("CVE-2024-21413", context.iocs.cves)
        self.assertIn("203.0.113.195", context.iocs.ipv4_addresses)
        self.assertIn("apt29-c2.net", context.iocs.domains)
        self.assertIn("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", context.iocs.sha256_hashes)

        # 5. Audio Speech Alignment
        self.assertIn("Front", context.full_audio_transcript)

        # 6. Aligned Markdown Output
        md_file = self.output_dir / "sample_apt29_investigation_video_context.md"
        json_file = self.output_dir / "sample_apt29_investigation_video_context.json"
        self.assertTrue(md_file.exists())
        self.assertTrue(json_file.exists())


if __name__ == "__main__":
    unittest.main()
