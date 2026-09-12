"""
Unit and integration tests for the Text Ingestion & Pre-LLM Preparation Pipeline.
"""

import unittest
from pathlib import Path
from pipelines.text_pipeline.ingest import TextIngestionPipeline
from pipelines.text_pipeline.schema import ExtractedSourceContext


class TestTextIngestionPipeline(unittest.TestCase):

    def setUp(self):
        self.tests_dir = Path(__file__).parent.resolve()
        self.output_dir = self.tests_dir / "test_outputs"
        self.pipeline = TextIngestionPipeline(output_dir=str(self.output_dir))
        self.samples_dir = self.tests_dir / "samples"

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

    def test_ransomware_pdf_ingestion(self):
        pdf_file = self.samples_dir / "RANSOMWARE_Report_Final.pdf"
        if pdf_file.exists():
            context = self.pipeline.process_file(str(pdf_file), save_outputs=True)
            self.assertEqual(context.metadata.file_type, "pdf")
            self.assertEqual(context.metadata.file_name, "RANSOMWARE_Report_Final.pdf")
            self.assertIn("CVE-2021-40539", context.iocs.cves)
            self.assertIn("CVE-2019-19781", context.iocs.cves)
            self.assertIn("Lockbit", context.threat_intel.threat_actors)
            self.assertIn("ALPHV", context.threat_intel.threat_actors)
            self.assertIn("Active Directory", context.threat_intel.affected_systems)
            self.assertGreater(context.metadata.word_count, 500)

    def test_docx_ingestion(self):
        docx_file = self.samples_dir / "sample_ransomware_brief.docx"
        if docx_file.exists():
            context = self.pipeline.process_file(str(docx_file), save_outputs=True)
            self.assertEqual(context.metadata.file_type, "docx")
            self.assertIn("CVE-2024-37085", context.iocs.cves)
            self.assertIn("203.0.113.50", context.iocs.ipv4_addresses)
            self.assertIn("LockBit 3.0", context.threat_intel.threat_actors)
            self.assertGreaterEqual(len(context.tables), 1)

    def test_plain_text_incident_triage(self):
        txt_file = self.samples_dir / "sample_incident_triage.txt"
        if txt_file.exists():
            context = self.pipeline.process_file(str(txt_file), save_outputs=True)
            self.assertEqual(context.metadata.file_type, "text")
            self.assertIn("CVE-2024-21410", context.iocs.cves)
            self.assertIn("198.51.100.89", context.iocs.ipv4_addresses)
            self.assertIn("8f434346648f6b96df89dda901c5176b10e6d0ceec3e4a14e310b73399b358b0", context.iocs.sha256_hashes)
            self.assertIn("bad-relay-dns.net", context.iocs.domains)
            self.assertIn("Microsoft Exchange Server", context.threat_intel.affected_systems)
            self.assertIn("HIGH", context.threat_intel.severity_keywords)

    def test_interpreter_enrichment(self):
        md_file = self.samples_dir / "sample_advisory.md"
        src, enriched = self.pipeline.process_and_enrich(str(md_file), save_outputs=True)
        
        self.assertIsNotNone(enriched)
        self.assertTrue(len(enriched.title) > 0)
        self.assertIn("APT29", enriched.title)
        self.assertTrue(len(enriched.minto_pyramid.situation) > 0)
        self.assertTrue(len(enriched.minto_pyramid.solution) > 0)
        self.assertTrue(len(enriched.locked_numerical_facts) > 0)
        self.assertTrue(any("3,200" in fact for fact in enriched.locked_numerical_facts))
        self.assertGreaterEqual(len(enriched.actionable_mitigations), 1)
        
        # Verify markdown serialization
        md_content = enriched.to_markdown()
        self.assertIn("## 1. Executive Narrative", md_content)
        self.assertIn("## 2. Minto Pyramid Briefing Structure", md_content)

        # Verify intermediate files were cleaned up and final enriched files exist
        intermediate_md = self.output_dir / "sample_advisory_normalized.md"
        intermediate_json = self.output_dir / "sample_advisory_metadata.json"
        final_enriched_md = self.output_dir / "sample_advisory_enriched_context.md"
        final_enriched_json = self.output_dir / "sample_advisory_enriched_context.json"

        self.assertFalse(intermediate_md.exists(), "Intermediate normalized markdown should be removed")
        self.assertFalse(intermediate_json.exists(), "Intermediate metadata json should be removed")
        self.assertTrue(final_enriched_md.exists(), "Enriched markdown file should exist")
        self.assertTrue(final_enriched_json.exists(), "Enriched json file should exist")

    def test_base_pipeline_and_bytes_processing(self):
        """Verifies BasePipeline contract implementation and byte-level document processing."""
        from pipelines.text_pipeline import TextPipeline, ingest_text
        pipeline = TextPipeline(output_dir=str(self.output_dir))
        sample_doc = b"# Threat Intel Alert\n\nAdversary deployed CVE-2024-38077 targeting 198.51.100.42.\n"
        res = pipeline.process(sample_doc, filename="memory_advisory.md", save_outputs=False)
        self.assertEqual(res.metadata.file_name, "memory_advisory.md")
        self.assertIn("CVE-2024-38077", res.iocs.cves)
        self.assertIn("198.51.100.42", res.iocs.ipv4_addresses)

        # Procedural helper check
        res2 = ingest_text(sample_doc, filename="memory_advisory2.md", save_outputs=False)
        self.assertEqual(res2.metadata.file_name, "memory_advisory2.md")


if __name__ == "__main__":
    unittest.main()
