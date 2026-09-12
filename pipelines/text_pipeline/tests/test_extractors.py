"""
Unit and integration tests for all individual extractor components in text_pipeline.
Tests:
1. PDFParser (sample_cve_report.pdf, RANSOMWARE_Report_Final.pdf)
2. DocxParser (sample_ransomware_brief.docx)
3. TextParser (Markdown, Plain Text, CSV, JSON, YAML, XML, EML, Logs)
4. IOCExtractor (CVEs, IPs, Hashes, Domains, URLs, MITRE ATT&CK, Threat Actors, Affected Systems, Severity, CVSS, Timelines)
5. OCRUtils (extract_text_from_image_bytes, clean_ocr_text, is_ocr_available)
6. TableUtils (extract_markdown_tables, format_matrix_to_markdown_table)
"""

import io
import unittest
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw

from pipelines.text_pipeline.extractors.pdf_parser import PDFParser
from pipelines.text_pipeline.extractors.docx_parser import DocxParser
from pipelines.text_pipeline.extractors.text_parser import TextParser
from pipelines.text_pipeline.extractors.ioc_extractor import IOCExtractor
from pipelines.text_pipeline.extractors.ocr_utils import (
    is_ocr_available,
    extract_text_from_image_bytes,
    clean_ocr_text
)
from pipelines.text_pipeline.extractors.table_utils import (
    extract_markdown_tables,
    format_matrix_to_markdown_table
)


class TestExtractors(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tests_dir = Path(__file__).parent.resolve()
        cls.samples_dir = cls.tests_dir / "samples"
        cls.pdf_parser = PDFParser()
        cls.docx_parser = DocxParser()
        cls.text_parser = TextParser()
        cls.ioc_extractor = IOCExtractor()

    # =========================================================================
    # 1. PDF Parser Tests
    # =========================================================================
    def test_pdf_parser_sample_cve_report(self):
        cve_pdf = self.samples_dir / "sample_cve_report.pdf"
        if not cve_pdf.exists():
            self.skipTest("sample_cve_report.pdf not found")
        
        markdown, tables = self.pdf_parser.parse(str(cve_pdf))
        self.assertIsInstance(markdown, str)
        self.assertGreater(len(markdown), 100)
        self.assertIn("CVE-2024-38077", markdown)
        self.assertIn("Volt Typhoon", markdown)

    def test_pdf_parser_ransomware_final_report(self):
        ransom_pdf = self.samples_dir / "RANSOMWARE_Report_Final.pdf"
        if not ransom_pdf.exists():
            self.skipTest("RANSOMWARE_Report_Final.pdf not found")

        markdown, tables = self.pdf_parser.parse(str(ransom_pdf))
        self.assertIsInstance(markdown, str)
        self.assertGreater(len(markdown), 1000)
        self.assertIn("RANSOMWARE", markdown)
        self.assertIn("Lockbit", markdown)
        self.assertGreaterEqual(len(tables), 1)

    # =========================================================================
    # 2. DOCX Parser Tests
    # =========================================================================
    def test_docx_parser(self):
        docx_file = self.samples_dir / "sample_ransomware_brief.docx"
        if not docx_file.exists():
            self.skipTest("sample_ransomware_brief.docx not found")

        markdown, tables = self.docx_parser.parse(str(docx_file))
        self.assertIsInstance(markdown, str)
        self.assertIn("LockBit", markdown)
        self.assertIn("CVE-2024-37085", markdown)
        self.assertGreaterEqual(len(tables), 1)
        self.assertTrue(any("Indicator" in h for h in tables[0].headers))

    # =========================================================================
    # 3. Text Parser Tests across all formats
    # =========================================================================
    def test_text_parser_markdown(self):
        md_file = self.samples_dir / "sample_advisory.md"
        markdown, tables = self.text_parser.parse(str(md_file))
        self.assertIn("CVE-2024-38077", markdown)
        self.assertGreaterEqual(len(tables), 1)

    def test_text_parser_plain_text(self):
        txt_file = self.samples_dir / "sample_incident_triage.txt"
        markdown, tables = self.text_parser.parse(str(txt_file))
        self.assertIn("CVE-2024-21410", markdown)
        self.assertIn("bad-relay-dns.net", markdown)

    def test_text_parser_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as f:
            f.write("CVE_ID,Severity,Status\nCVE-2024-1111,CRITICAL,Active\nCVE-2024-2222,HIGH,Mitigated\n")
            f_path = f.name

        try:
            markdown, tables = self.text_parser.parse(f_path)
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0].headers, ["CVE_ID", "Severity", "Status"])
            self.assertEqual(tables[0].row_count, 2)
            self.assertIn("CVE-2024-1111", markdown)
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_text_parser_json(self):
        sample_json_data = [
            {"host": "192.168.1.50", "role": "Domain Controller", "status": "Compromised"},
            {"host": "192.168.1.51", "role": "File Server", "status": "Encrypted"}
        ]
        import json
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump(sample_json_data, f)
            f_path = f.name

        try:
            markdown, tables = self.text_parser.parse(f_path)
            self.assertIn("```json", markdown)
            self.assertEqual(len(tables), 1)
            self.assertIn("Domain Controller", markdown)
            self.assertEqual(tables[0].headers, ["host", "role", "status"])
            self.assertEqual(tables[0].row_count, 2)
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_text_parser_yaml(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False, encoding="utf-8") as f:
            f.write("campaign:\n  actor: APT29\n  target: Critical Infrastructure\n  cve: CVE-2024-38077\n")
            f_path = f.name

        try:
            markdown, tables = self.text_parser.parse(f_path)
            self.assertIn("```yaml", markdown)
            self.assertIn("APT29", markdown)
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_text_parser_xml(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False, encoding="utf-8") as f:
            f.write("<threat><indicator>198.51.100.1</indicator><cve>CVE-2023-1234</cve></threat>")
            f_path = f.name

        try:
            markdown, tables = self.text_parser.parse(f_path)
            self.assertIn("```xml", markdown)
            self.assertIn("198.51.100.1", markdown)
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_text_parser_email(self):
        raw_email = (
            "From: security@agency.gov\n"
            "To: admin@infra.gov\n"
            "Date: Fri, 11 Sep 2026 10:00:00 +0000\n"
            "Subject: Urgent Ransomware Threat Advisory\n"
            "Content-Type: text/plain\n\n"
            "Please isolate host 10.0.0.5 immediately due to Lockbit activity.\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".eml", mode="w", delete=False, encoding="utf-8") as f:
            f.write(raw_email)
            f_path = f.name

        try:
            markdown, tables = self.text_parser.parse(f_path)
            self.assertIn("### 📧 Email Metadata", markdown)
            self.assertIn("security@agency.gov", markdown)
            self.assertIn("Urgent Ransomware Threat Advisory", markdown)
            self.assertIn("Lockbit", markdown)
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_text_parser_log(self):
        raw_log = "2026-09-11 12:00:00 [ALERT] Unauthorized access attempt from 198.51.100.42 to Port 3389\n"
        with tempfile.NamedTemporaryFile(suffix=".log", mode="w", delete=False, encoding="utf-8") as f:
            f.write(raw_log)
            f_path = f.name

        try:
            markdown, tables = self.text_parser.parse(f_path)
            self.assertIn("### 🪵 Ingested Log Telemetry", markdown)
            self.assertIn("198.51.100.42", markdown)
        finally:
            Path(f_path).unlink(missing_ok=True)

    # =========================================================================
    # 4. Deterministic IOC Extractor Tests
    # =========================================================================
    def test_ioc_extractor_comprehensive(self):
        test_content = """
        INCIDENT BRIEF - SEVERITY: CRITICAL
        CVSS Base Score: 9.8
        Date: 2026-09-11
        Threat Actor: APT29 collaborating with LockBit 3.0 and ALPHV ransomware gangs.
        Targeting Windows Server 2022 and Citrix Application Delivery Controller and Active Directory.
        Initial entry achieved via exploit of CVE-2024-38077 and unpatched asCVE-2019-19781.
        Techniques observed: T1190, T1059.001, and T1133.
        Involved IPs: 198.51.100.42, 203.0.113.195, and invalid 999.999.999.999, 0.0.0.0.
        IPv6: 2001:0db8:85a3:0000:0000:8a2e:0370:7334.
        C2 Domains: malicious-c2[.]net, hxxps://bad-payload.org/drop.exe, cert-in.org.in.
        Malicious hash: 8f434346648f6b96df89dda901c5176b10e6d0ceec3e4a14e310b73399b358b0.
        """
        iocs = self.ioc_extractor.extract_iocs(test_content)
        threat_intel = self.ioc_extractor.extract_threat_summary(test_content)

        # Assert CVEs
        self.assertIn("CVE-2024-38077", iocs.cves)
        self.assertIn("CVE-2019-19781", iocs.cves)

        # Assert MITRE ATT&CK
        self.assertIn("T1190", iocs.mitre_attack_ids)
        self.assertIn("T1059.001", iocs.mitre_attack_ids)
        self.assertIn("T1133", iocs.mitre_attack_ids)

        # Assert IPs
        self.assertIn("198.51.100.42", iocs.ipv4_addresses)
        self.assertIn("203.0.113.195", iocs.ipv4_addresses)
        self.assertNotIn("999.999.999.999", iocs.ipv4_addresses)
        self.assertNotIn("0.0.0.0", iocs.ipv4_addresses)
        self.assertIn("2001:0db8:85a3:0000:0000:8a2e:0370:7334", iocs.ipv6_addresses)

        # Assert Hashes
        self.assertIn(
            "8f434346648f6b96df89dda901c5176b10e6d0ceec3e4a14e310b73399b358b0",
            iocs.sha256_hashes
        )

        # Assert Domains & URLs (Refanged)
        self.assertIn("malicious-c2.net", iocs.domains)
        self.assertIn("https://bad-payload.org/drop.exe", iocs.urls)

        # Assert Threat Summary
        self.assertIn("CRITICAL", threat_intel.severity_keywords)
        self.assertIn(9.8, threat_intel.cvss_scores)
        self.assertIn("LockBit 3.0", threat_intel.threat_actors)
        self.assertIn("ALPHV", threat_intel.threat_actors)
        self.assertIn("APT29", threat_intel.threat_actors)
        self.assertIn("Citrix Application Delivery Controller", threat_intel.affected_systems)
        self.assertIn("Active Directory", threat_intel.affected_systems)

    # =========================================================================
    # 5. OCR Utilities Tests
    # =========================================================================
    def test_ocr_availability_and_clean_text(self):
        self.assertTrue(is_ocr_available())
        
        dirty_ocr = "Line 1\n\n\n~~~~~~~====----- Line 2 \n\n"
        cleaned = clean_ocr_text(dirty_ocr)
        self.assertIn("Line 1", cleaned)
        self.assertIn("Line 2", cleaned)
        self.assertNotIn("~~~~~~~", cleaned)

    def test_ocr_image_text_extraction(self):
        if not is_ocr_available():
            self.skipTest("OCR is not available in environment")

        # Generate a high-contrast synthetic image containing crisp text
        img = Image.new("RGB", (400, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        test_phrase = "SECURITY ALERT 911"
        draw.text((20, 35), test_phrase, fill=(0, 0, 0))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        extracted_text = extract_text_from_image_bytes(img_bytes)
        self.assertTrue(len(extracted_text) > 0)
        self.assertTrue(any(word in extracted_text for word in ["SECURITY", "ALERT", "911"]))

    # =========================================================================
    # 6. Table Utilities Tests
    # =========================================================================
    def test_table_utils_formatting_and_extraction(self):
        headers = ["Host", "IP", "Status"]
        rows = [
            ["WebServer-01", "10.0.1.10", "Offline"],
            ["Database-01", "10.0.1.20", "Active"]
        ]
        formatted_md = format_matrix_to_markdown_table(headers, rows)
        self.assertIn("| Host", formatted_md)
        self.assertIn("| WebServer-01", formatted_md)

        # Now extract the table back from markdown
        parsed_tables = extract_markdown_tables(formatted_md)
        self.assertEqual(len(parsed_tables), 1)
        t = parsed_tables[0]
        self.assertEqual(t.headers, headers)
        self.assertEqual(t.row_count, 2)
        self.assertEqual(t.column_count, 3)
        self.assertEqual(t.rows[0], ["WebServer-01", "10.0.1.10", "Offline"])


if __name__ == "__main__":
    unittest.main()
