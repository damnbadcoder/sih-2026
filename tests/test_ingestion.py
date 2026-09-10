"""
Unit and integration tests for the Text Ingestion & Pre-LLM Preparation Pipeline.
"""

import unittest
from pathlib import Path
from pipelines.ingest import TextIngestionPipeline
from pipelines.schema import ExtractedSourceContext


class TestTextIngestionPipeline(unittest.TestCase):

    def setUp(self):
        self.pipeline = TextIngestionPipeline(output_dir="tests/test_outputs")
        self.samples_dir = Path("tests/samples")

    def test_markdown_advisory_ingestion(self):
        md_file = self.samples_dir / "sample_advisory.md"
        context: ExtractedSourceContext = self.pipeline.process_file(str(md_file), save_outputs=True)

        # Assert document metadata
        self.assertEqual(context.metadata.file_name, "sample_advisory.md")
        self.assertEqual(context.metadata.file_type, "markdown")
        self.assertGreater(context.metadata.word_count, 100)

        # Assert CVE indicators
        self.assertIn("CVE-2024-38077", context.iocs.cves)
        self.assertIn("CVE-2023-36884", context.iocs.cves)
        self.assertIn("CVE-2024-21410", context.iocs.cves)

        # Assert MITRE ATT&CK techniques
        self.assertIn("T1190", context.iocs.mitre_attack_ids)
        self.assertIn("T1059.001", context.iocs.mitre_attack_ids)

        # Assert IP addresses
        self.assertIn("198.51.100.42", context.iocs.ipv4_addresses)
        self.assertIn("203.0.113.195", context.iocs.ipv4_addresses)

        # Assert Table extraction
        self.assertGreaterEqual(len(context.tables), 1)
        first_table = context.tables[0]
        self.assertIn("CVE Identifier", first_table.headers)
        self.assertEqual(first_table.row_count, 3)

        # Assert Threat Intel
        self.assertIn("APT29", context.threat_intel.threat_actors)
        self.assertIn("CRITICAL", context.threat_intel.severity_keywords)
        self.assertIn(9.8, context.threat_intel.cvss_scores)

        # Assert LLM Bundle
        self.assertTrue(len(context.llm_bundle.system_grounding_header) > 0)
        self.assertTrue(len(context.llm_bundle.formatted_context_for_prompt) > 0)
        self.assertGreaterEqual(len(context.llm_bundle.semantic_chunks), 1)

    def test_pdf_ingestion(self):
        pdf_file = self.samples_dir / "sample_cve_report.pdf"
        if pdf_file.exists():
            context = self.pipeline.process_file(str(pdf_file), save_outputs=True)
            self.assertEqual(context.metadata.file_type, "pdf")
            self.assertIn("CVE-2024-38077", context.iocs.cves)
            self.assertIn("198.51.100.120", context.iocs.ipv4_addresses)
            self.assertIn("Volt Typhoon", context.threat_intel.threat_actors)

    def test_docx_ingestion(self):
        docx_file = self.samples_dir / "sample_ransomware_brief.docx"
        if docx_file.exists():
            context = self.pipeline.process_file(str(docx_file), save_outputs=True)
            self.assertEqual(context.metadata.file_type, "docx")
            self.assertIn("CVE-2024-37085", context.iocs.cves)
            self.assertIn("203.0.113.50", context.iocs.ipv4_addresses)
            self.assertIn("LockBit 3.0", context.threat_intel.threat_actors)
            self.assertGreaterEqual(len(context.tables), 1)

    def test_qwen_enrichment(self):
        md_file = self.samples_dir / "sample_advisory.md"
        src, enriched = self.pipeline.process_and_enrich(str(md_file), save_outputs=True)
        
        self.assertIsNotNone(enriched)
        self.assertTrue(len(enriched.title) > 0)
        self.assertIn("APT29", enriched.title)
        self.assertTrue(len(enriched.minto_pyramid.situation) > 0)
        self.assertTrue(len(enriched.minto_pyramid.solution) > 0)
        self.assertTrue(len(enriched.locked_numerical_facts) > 0)
        self.assertIn("3,200 enterprise servers", enriched.locked_numerical_facts)
        self.assertGreaterEqual(len(enriched.actionable_mitigations), 1)
        
        # Verify markdown serialization
        md_content = enriched.to_markdown()
        self.assertIn("## 1. Executive Narrative", md_content)
        self.assertIn("## 2. Minto Pyramid Briefing Structure", md_content)


if __name__ == "__main__":
    unittest.main()
