"""
Universal Text and Unstructured File Parser.
Supports Markdown, Plain Text, Logs, CSV/TSV, JSON, YAML, XML, HTML, and EML email files.
"""

import os
import csv
import json
import email
from email import policy
import xml.etree.ElementTree as ET
from io import StringIO
from typing import Tuple, List, Any
import yaml

from pipelines.text_pipeline.schema import TableData
from pipelines.text_pipeline.extractors.table_utils import (
    extract_markdown_tables,
    format_matrix_to_markdown_table
)


class TextParser:
    """Parses arbitrary text and semi-structured file streams into structured Markdown."""

    def parse(self, file_path: str) -> Tuple[str, List[TableData]]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        raw_text = self._read_file_with_fallback(file_path)

        if ext in {".md", ".markdown"}:
            tables = extract_markdown_tables(raw_text)
            return raw_text.strip(), tables

        elif ext in {".csv", ".tsv"}:
            return self._parse_delimited(raw_text, delimiter="," if ext == ".csv" else "\t")

        elif ext == ".json":
            return self._parse_json(raw_text)

        elif ext in {".yaml", ".yml"}:
            return self._parse_yaml(raw_text)

        elif ext in {".xml", ".html", ".htm"}:
            return self._parse_xml_or_html(raw_text)

        elif ext in {".eml", ".msg"}:
            return self._parse_email(raw_text)

        elif ext in {".log", ".txt", ".ini", ".conf", ".cfg"}:
            return self._parse_plain_or_log(raw_text, ext)

        else:
            tables = extract_markdown_tables(raw_text)
            return raw_text.strip(), tables

    def _read_file_with_fallback(self, file_path: str) -> str:
        """Reads file contents using standard encodings with lossy fallback."""
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "utf-16"]:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _parse_delimited(self, content: str, delimiter: str = ",") -> Tuple[str, List[TableData]]:
        reader = csv.reader(StringIO(content), delimiter=delimiter)
        all_rows = [row for row in reader if any(cell.strip() for cell in row)]
        if not all_rows:
            return "", []

        headers = all_rows[0]
        data_rows = all_rows[1:] if len(all_rows) > 1 else []
        table_md = format_matrix_to_markdown_table(headers, data_rows)

        table_data = TableData(
            table_index=1,
            headers=headers,
            rows=data_rows,
            markdown_representation=table_md,
            row_count=len(data_rows),
            column_count=len(headers)
        )
        return table_md, [table_data]

    def _parse_json(self, content: str) -> Tuple[str, List[TableData]]:
        try:
            data = json.loads(content)
            pretty_json = json.dumps(data, indent=2)
            markdown = f"```json\n{pretty_json}\n```"

            tables: List[TableData] = []
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                headers = list(data[0].keys())
                rows = [
                    [str(item.get(h, "")) for h in headers]
                    for item in data if isinstance(item, dict)
                ]
                if headers and rows:
                    table_md = format_matrix_to_markdown_table(headers, rows)
                    tables.append(TableData(
                        table_index=1,
                        headers=headers,
                        rows=rows,
                        markdown_representation=table_md,
                        row_count=len(rows),
                        column_count=len(headers)
                    ))
                    markdown = f"{table_md}\n\n{markdown}"

            return markdown, tables
        except json.JSONDecodeError:
            return f"```\n{content.strip()}\n```", []

    def _parse_yaml(self, content: str) -> Tuple[str, List[TableData]]:
        try:
            parsed = yaml.safe_load(content)
            pretty_yaml = yaml.dump(parsed, sort_keys=False, default_flow_style=False)
            return f"```yaml\n{pretty_yaml}\n```", []
        except yaml.YAMLError:
            return f"```text\n{content.strip()}\n```", []

    def _parse_xml_or_html(self, content: str) -> Tuple[str, List[TableData]]:
        tables = extract_markdown_tables(content)
        try:
            root = ET.fromstring(content)
            clean_xml = ET.tostring(root, encoding="unicode", method="xml")
            return f"```xml\n{clean_xml.strip()}\n```", tables
        except ET.ParseError:
            return content.strip(), tables

    def _parse_email(self, content: str) -> Tuple[str, List[TableData]]:
        msg = email.message_from_string(content, policy=policy.default)
        headers = [
            f"- **From:** {msg.get('from', 'N/A')}",
            f"- **To:** {msg.get('to', 'N/A')}",
            f"- **Date:** {msg.get('date', 'N/A')}",
            f"- **Subject:** {msg.get('subject', 'N/A')}"
        ]
        header_block = "### 📧 Email Metadata\n" + "\n".join(headers)

        body_parts = []
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    body_parts.append(part.get_content())
                elif content_type == "text/html":
                    body_parts.append(part.get_content())
        else:
            body_parts.append(msg.get_content())

        full_body = "\n\n".join(body_parts).strip()
        tables = extract_markdown_tables(full_body)
        return f"{header_block}\n\n### ✉️ Message Content\n\n{full_body}", tables

    def _parse_plain_or_log(self, content: str, ext: str) -> Tuple[str, List[TableData]]:
        clean_text = content.strip()
        tables = extract_markdown_tables(clean_text)
        if ext == ".log":
            markdown = f"### 🪵 Ingested Log Telemetry\n\n```text\n{clean_text}\n```"
        else:
            markdown = clean_text
        return markdown, tables